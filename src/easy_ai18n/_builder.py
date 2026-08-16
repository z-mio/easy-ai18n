from __future__ import annotations

import ast
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from loguru import logger

from ._loader import Loader
from ._parser import ASTParser
from ._progress import ProgressHandle, translation_progress
from ._types import TextId, TextMap
from .errors import TranslationError
from .translators import BaseTranslator, GoogleTranslator


@dataclass(frozen=True, slots=True)
class SourceEntry:
    """A translatable source string, decoupled from AST objects.

    Built during extraction and carried through the build pipeline.
    Unlike the parser's ``StringData``, no AST ``call_node`` is kept,
    so entries stay cheap to hold and compare.
    """

    id: TextId
    """The content-addressed ID of ``text``."""

    text: str
    """The template text, with ``{variable}`` placeholders intact."""

    placeholders: tuple[str, ...]
    """The placeholder tokens in first-occurrence order."""


@dataclass(frozen=True, slots=True)
class Changes:
    """What a build must do, expressed as pure set differences.

    Attributes:
        to_translate: Locale to the ordered entries whose ID is missing
            from that locale's YAML file.
        stale: Locale to the IDs present in the YAML file but absent
            from the source tree (to be removed).
    """

    to_translate: dict[str, tuple[SourceEntry, ...]]
    stale: dict[str, frozenset[TextId]]

    @property
    def is_empty(self) -> bool:
        """True when nothing needs translating and nothing needs removing."""
        return not self.to_translate and not any(self.stale.values())


@dataclass(frozen=True, slots=True)
class _LocaleOutcome:
    """Result of translating one locale: the texts, or the final error."""

    result: TextMap | None
    error: str | None


# Placeholder masking: translators receive ``\uE000<i>\uE001`` instead of
# the real ``{variable}`` tokens, so a variable name can never collide
# with the marker (the old ``{{i}}`` scheme could be corrupted by a
# literal ``{{0}}`` in the source) and translation cannot mangle it.
# The markers are restored after translation.
_MASK_START = "\ue000"
_MASK_END = "\ue001"


def _mask(text: str, placeholders: tuple[str, ...]) -> str:
    for i, placeholder in enumerate(placeholders):
        text = text.replace(placeholder, f"{_MASK_START}{i}{_MASK_END}")
    return text


def _restore(text: str, placeholders: tuple[str, ...]) -> str:
    for i, placeholder in enumerate(placeholders):
        text = text.replace(f"{_MASK_START}{i}{_MASK_END}", placeholder)
    return text


class Builder:
    def __init__(
        self,
        *,
        sep: str,
        func_names: list[str],
        locales_dir: Path,
        to_locales: list[str],
        source_locale: str,
        project_root: Path | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        translator: BaseTranslator | None = None,
        show_progress: bool = True,
        concurrent_locales: bool = True,
        max_retries: int = 2,
    ):
        """Set up the translation build pipeline.

        Args:
            sep: The separator between text parts.
            func_names: The names of translation functions to
                recognize during AST parsing.
            locales_dir: The directory for YAML translation files.
            to_locales: The target language codes to translate to.
            source_locale: The source language of the translatable
                strings.
            project_root: The project root directory. Defaults to the
                current working directory.
            include: File or directory patterns to include. A path is
                included when it equals, descends from, or glob-matches
                a pattern.
            exclude: File or directory patterns to exclude. Directories
                matching an exclude pattern are pruned from the walk.
            translator: The translator instance. Defaults to
                ``GoogleTranslator``.
            show_progress: Whether to display progress.  ``False`` stays
                silent. Defaults to ``True``.
            concurrent_locales: Whether to translate all locales in
                parallel. ``True`` (default) is faster but issues more
                API calls at once; set to ``False`` for rate-limited
                free APIs.
            max_retries: How many extra attempts a locale gets after a
                translation failure. Defaults to ``2``.
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.locales_dir = Path(locales_dir)
        self.include = include or []
        self.exclude = exclude or []
        self.default_exclude = [".venv", "venv", ".git", ".idea"]
        self.func_names = func_names
        self.sep = sep
        self.to_locales = [i.lower() for i in to_locales]
        self.source_locale = source_locale
        self.translator: BaseTranslator = GoogleTranslator() if translator is None else translator
        self.show_progress = show_progress
        self.concurrent_locales = concurrent_locales
        self.max_retries = max(0, max_retries)

        self.project_files = self.load_file()
        self._locales = Loader(self.locales_dir).load_locales_file(self.to_locales)
        self._entries: dict[TextId, SourceEntry] | None = None

    # ── Orchestration ────────────────────────────────────────────

    async def run(self) -> None:
        """Build only when something changed; skip the network otherwise."""
        changes = self.compute_changes()
        if changes.is_empty:
            logger.info("Content unchanged, skipping build")
            return
        await self._build(changes)

    async def build(self, save_to_file: bool = True) -> bool:
        """Build the translation dictionaries.

        Args:
            save_to_file: Whether to persist the results to YAML files.

        Returns:
            ``True`` when every target locale was translated.
        """
        changes = self.compute_changes()
        return await self._build(changes, save_to_file=save_to_file)

    async def _build(self, changes: Changes, *, save_to_file: bool = True) -> bool:
        """Translate the gaps in ``changes`` and persist the merged result."""
        locale_totals = {locale: len(entries) for locale, entries in changes.to_translate.items()}
        locales = self._locales_clean(changes)
        errors: dict[str, str] = {}

        async with translation_progress(locale_totals, show_progress=self.show_progress) as handle:
            if self.concurrent_locales:
                outcomes = await asyncio.gather(
                    *(
                        self._translate_with_retries(locale, entries, handle)
                        for locale, entries in changes.to_translate.items()
                    )
                )
            else:
                outcomes = [
                    await self._translate_with_retries(locale, entries, handle)
                    for locale, entries in changes.to_translate.items()
                ]

            for locale, outcome in zip(changes.to_translate, outcomes, strict=True):
                if outcome.result is None:
                    errors[locale] = outcome.error or "unknown error"
                    continue
                current = locales.get(locale, {})
                locales[locale] = {**current, **outcome.result}
            handle.finish(ok=not errors)

        handle.report_errors(errors)

        if save_to_file:
            for locale in self.to_locales:
                merged = locales[locale]
                if merged != self._locales.get(locale):
                    self.save_to_yaml(merged, locale)
        # The in-memory view must reflect what was just built, or the
        # next compute_changes (e.g. a second ``run``) would re-translate
        # everything it already persisted.
        self._locales = locales
        return not errors

    # ── Diffing ──────────────────────────────────────────────────

    def compute_changes(self) -> Changes:
        """Diff source entries against the existing translations.

        Extraction is memoized, so repeated calls (``run`` followed by
        ``build``, repeated ``is_changed`` checks) never re-parse.

        Returns:
            The set differences to apply, as a ``Changes``.
        """
        entries = self.extract_entries()
        entry_ids = set(entries)
        to_translate: dict[str, tuple[SourceEntry, ...]] = {}
        stale: dict[str, frozenset[TextId]] = {}
        for locale in self.to_locales:
            current = self._locales.get(locale)
            if current is None:
                to_translate[locale] = tuple(entries[i] for i in sorted(entries))
                continue
            missing = entry_ids - set(current)
            if missing:
                to_translate[locale] = tuple(entries[i] for i in sorted(missing))
            gone = set(current) - entry_ids
            if gone:
                stale[locale] = frozenset(gone)
        return Changes(to_translate=to_translate, stale=stale)

    def _locales_clean(self, changes: Changes) -> dict[str, TextMap]:
        """Existing translations restricted to the target locales, stale IDs removed.

        Copy-on-write: untouched locales keep sharing their original
        dictionaries; only locales being modified are copied.
        """
        locales: dict[str, TextMap] = {}
        for locale in self.to_locales:
            current = self._locales.get(locale)
            if current is None:
                locales[locale] = {}
            else:
                stale_ids = changes.stale.get(locale)
                locales[locale] = {k: v for k, v in current.items() if k not in stale_ids} if stale_ids else current
        return locales

    def is_changed(self) -> bool:
        """Check whether the translation data has changed."""
        return not self.compute_changes().is_empty

    # ── Translation ──────────────────────────────────────────────

    async def _translate_with_retries(
        self,
        locale: str,
        entries: tuple[SourceEntry, ...],
        handle: ProgressHandle,
    ) -> _LocaleOutcome:
        """Translate one locale, retrying silently up to ``max_retries`` times.

        The first attempt reports progress through ``handle``; retries
        run against a no-op handle so progress is never double-counted,
        and the child task is topped up on success.
        """
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                result = await self._translate_locale(locale, entries, handle if attempt == 0 else ProgressHandle())
            except Exception as e:
                last_error = e
                if isinstance(e, TranslationError):
                    logger.error(f"Translation to {locale} failed (attempt {attempt + 1}/{attempts}): {e}")
                else:
                    logger.exception(
                        f"Unexpected error translating to {locale} (attempt {attempt + 1}/{attempts}): {e}"
                    )
                if attempt < attempts - 1:
                    handle.retrying(locale)
                continue
            handle.succeed(locale, completed=len(entries) if attempt > 0 else None)
            return _LocaleOutcome(result=result, error=None)
        handle.fail(locale)
        return _LocaleOutcome(result=None, error=str(last_error) if last_error else "unknown error")

    async def _translate_locale(
        self,
        locale: str,
        entries: tuple[SourceEntry, ...],
        handle: ProgressHandle,
    ) -> TextMap:
        """Mask variables, translate, then restore them."""
        texts: TextMap = {entry.id: _mask(entry.text, entry.placeholders) for entry in entries}
        translated = await self.translator.translate(
            texts,
            locale,
            on_progress=lambda n: handle.advance(locale, n),
        )
        for entry in entries:
            translated[entry.id] = _restore(translated[entry.id], entry.placeholders)
        return translated

    # ── Extraction ───────────────────────────────────────────────

    def extract_entries(self) -> dict[TextId, SourceEntry]:
        """Extract every source entry, parsing each file at most once."""
        if self._entries is None:
            entries: dict[TextId, SourceEntry] = {}
            for file in self.project_files:
                for entry in self._parse_file(file):
                    entries[entry.id] = entry
            self._entries = entries
        return self._entries

    def _parse_file(self, file: Path) -> list[SourceEntry]:
        """Read and parse one file into source entries (AST objects dropped)."""
        source = file.read_text(encoding="utf-8")
        module = ast.parse(source)
        parser = ASTParser(sep=self.sep, func_names=self.func_names)
        entries: list[SourceEntry] = []
        for string_data in parser.extract_all(node=module, source_path=file, source=source):
            text = str(string_data.string)
            if not text:
                continue
            entries.append(SourceEntry(id=string_data.string.id, text=text, placeholders=tuple(string_data.variables)))
        return entries

    # ── Scanning and persistence ─────────────────────────────────

    def load_file(self) -> list[Path]:
        """Discover the project's Python files.

        Exclude patterns prune directories from the walk; include
        patterns filter files.  One matching rule serves both: a path
        matches when it equals a pattern, descends from it, or
        glob-matches it.
        """
        include = [Path(p) for p in self.include]
        exclude = [Path(p) for p in self.default_exclude + self.exclude]
        project_files: list[Path] = []
        for root, dirs, names in self.project_root.walk():
            root_rel = Path(root).relative_to(self.project_root)
            dirs[:] = [d for d in dirs if not self._matches(root_rel / d, exclude)]
            for name in names:
                if not name.endswith(".py"):
                    continue
                rel = root_rel / name
                if include and not self._matches(rel, include):
                    continue
                project_files.append(Path(root) / name)
        return project_files

    @staticmethod
    def _matches(rel: Path, patterns: list[Path]) -> bool:
        """True when ``rel`` equals, descends from, or glob-matches a pattern."""
        for pattern in patterns:
            if rel == pattern or rel.is_relative_to(pattern) or rel.match(str(pattern)):
                return True
        return False

    def save_to_yaml(self, texts: TextMap, locale: str) -> None:
        """Atomically write one locale's dictionary to YAML.

        The file is written to a temporary sibling and renamed into
        place, so an interrupted build never leaves a truncated file.
        """
        self.locales_dir.mkdir(parents=True, exist_ok=True)
        target = self.locales_dir / f"{locale}.yaml"
        tmp = target.with_name(f".{target.stem}.{os.getpid()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                yaml.dump(texts, f, allow_unicode=True, sort_keys=True)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
