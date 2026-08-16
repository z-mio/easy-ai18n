from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

try:
    from rich.console import Console
    from rich.markup import escape
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
    from rich.text import Text
except ImportError as _import_error:
    from .errors import BuildDependencyError

    raise BuildDependencyError() from _import_error


# ── Child task descriptions ─────────────────────────────────────


def _child_desc(
    locale: str,
    index: int,
    total: int,
    *,
    ok: bool = False,
    failed: bool = False,
    retrying: bool = False,
) -> str:
    """Build a tree-indented child description (``├─`` branches, ``└─`` last).

    Visually distinguishes the parent task (Total) from per-locale
    child tasks.
    """
    branch = "└─" if index == total else "├─"
    if retrying:
        name = f"[yellow]✗ {locale} failed, retrying...[/yellow]"
    elif failed:
        name = f"[red]✗ {locale} failed[/red]"
    elif ok:
        name = f"[green]✓ {locale}[/green]"
    else:
        name = locale
    return f"  {branch} {name}"


def _make_summary(locale_totals: dict[str, int]) -> str:
    """Build the degraded-mode summary: one total line + one line per locale."""
    lines = [f"Translating {sum(locale_totals.values())} items:"]
    n = len(locale_totals)
    for i, (locale, count) in enumerate(locale_totals.items(), start=1):
        lines.append(f"{_child_desc(locale, i, n)} ({count})")
    return "\n".join(lines)


# ── Degraded output: final report ───────────────────────────────


class LineReporter:
    """Non-terminal fallback: a summary line, then a final report.

    rich's ``Live`` only paints intermediate frames on a real terminal;
    on IDE run panels / pipes / redirects there is no live redraw, so
    we degrade to:
      1. print the summary on enter (what is being done, per locale);
      2. stay quiet while running (no spam; loguru logs continue);
      3. on exit, print each task's final state (✓/✗ + counts) in
         ``add_task`` order — parent first, children indented.
    The interface mirrors a subset of rich ``Progress`` so callers can
    use either interchangeably.
    """

    def __init__(
        self,
        console: Console,
        *,
        summary: str | None = None,
        interval: float | None = None,
    ) -> None:
        self.console = console
        self.summary = summary
        self.interval = interval or None  # both 0 and None mean disabled
        self.tasks: dict[Any, dict[str, Any]] = {}
        self._order: list[str] = []
        self._count = 0
        self._last_report = 0.0

    def __enter__(self) -> LineReporter:
        if self.summary:
            self.console.print(self.summary, style="dim")
        return self

    def add_task(self, description: str, total: object = None) -> str:
        task_id = f"task-{self._count}"
        self._count += 1
        self.tasks[task_id] = {"description": description, "total": total, "completed": 0, "final": None}
        self._order.append(task_id)
        return task_id

    def advance(self, task_id: object, n: int = 1) -> None:
        self.tasks[task_id]["completed"] += n
        if self.interval is not None:
            self._maybe_report()

    def _maybe_report(self) -> None:
        """Print one parent-progress line at a fixed time interval.

        Event-driven: checked on every ``advance``; nothing is printed
        while progress is stalled. Only fires when the parent task
        (first ``add_task``) has a total.
        """
        if not self._order:
            return
        interval = self.interval
        if interval is None:
            return
        parent = self.tasks[self._order[0]]
        completed = parent["completed"]
        total = parent["total"]
        if not total or completed <= 0:
            return
        now = monotonic()
        if now - self._last_report < interval:
            return
        self._last_report = now
        percent = int(completed * 100 / total)
        self.console.print(f"Progress: {completed}/{total} ({percent}%)", style="dim")

    def update(self, task_id: object, **fields: Any) -> None:
        if "description" in fields:
            self.tasks[task_id]["final"] = fields["description"]
        # Same semantics as rich: completed=None means "do not update"
        if fields.get("completed") is not None:
            self.tasks[task_id]["completed"] = fields["completed"]

    def remove_task(self, task_id: object) -> None:
        pass

    def __exit__(self, *exc: object) -> None:
        for task_id in self._order:
            task = self.tasks[task_id]
            final = task["final"]
            if final is None:
                continue
            # Pad by plain-text width so the count column aligns
            # (markup tags do not count toward width)
            pad = max(0, 18 - len(Text.from_markup(str(final)).plain))
            self.console.print(f"{final}{' ' * pad}  {task['completed']}/{task['total']}")


# ── Public handle ───────────────────────────────────────────────


@dataclass
class ProgressHandle:
    """The only progress interface ``_builder`` depends on.

    All three modes (live / reporter / neither) are transparent to the
    caller: advancing, retry hints, success, failure, finishing and
    error reporting behave identically.
    """

    live: Progress | None = None
    reporter: LineReporter | None = None
    console: Console | None = None
    parent: Any = None
    children: dict[str, Any] = field(default_factory=dict)
    locale_order: list[str] = field(default_factory=list)
    locale_totals: dict[str, int] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    _child_completed: dict[str, int] = field(default_factory=dict)

    def _desc(self, locale: str, **kw: bool) -> str:
        return _child_desc(locale, self.locale_order.index(locale) + 1, len(self.locale_order), **kw)

    def advance(self, locale: str, n: int) -> None:
        """One chunk finished: advance both the child and the parent task."""
        self._child_completed[locale] = self._child_completed.get(locale, 0) + n
        if self.live is not None:
            self.live.advance(self.children[locale], n)
            self.live.advance(self.parent, n)
        elif self.reporter is not None:
            self.reporter.advance(self.children[locale], n)
            self.reporter.advance(self.parent, n)

    def retrying(self, locale: str) -> None:
        """Translation failed; a retry is in progress."""
        desc = self._desc(locale, retrying=True)
        if self.live is not None:
            self.live.update(self.children[locale], description=desc)
        elif self.reporter is not None:
            self.reporter.update(self.children[locale], description=desc)

    def succeed(self, locale: str, *, completed: int | None = None) -> None:
        """Translation succeeded (including after a retry).

        ``completed`` is only needed when progress was skipped (e.g. a
        silent retry succeeded): the child task is topped up and the
        parent task advances by the difference, avoiding double counts.
        """
        desc = self._desc(locale, ok=True)
        extra = 0
        if completed is not None:
            extra = max(0, completed - self._child_completed.get(locale, 0))
            self._child_completed[locale] = completed
        if self.live is not None:
            self.live.update(self.children[locale], description=desc, completed=completed)
            if extra:
                self.live.advance(self.parent, extra)
        elif self.reporter is not None:
            self.reporter.update(self.children[locale], description=desc, completed=completed)
            if extra:
                self.reporter.advance(self.parent, extra)

    def fail(self, locale: str) -> None:
        """Translation finally failed: red child task, record the locale."""
        self.failed.append(locale)
        desc = self._desc(locale, failed=True)
        if self.live is not None:
            self.live.update(self.children[locale], description=desc)
        elif self.reporter is not None:
            self.reporter.update(self.children[locale], description=desc)

    def finish(self, ok: bool) -> None:
        """Finish the parent task: green on success, red on failure.

        On failure the progress stays at the actual completed count;
        it is never pulled up to the total.
        """
        if ok:
            desc = "[green]✓ all done[/green]"
        else:
            desc = f"[red]✗ build failed ({', '.join(self.failed)})[/red]"
        if self.live is not None:
            self.live.update(self.parent, description=desc)
        elif self.reporter is not None:
            self.reporter.update(self.parent, description=desc)

    def report_errors(self, errors: dict[str, str]) -> None:
        """Print an error-details block (after the bar/report has exited)."""
        if not errors or self.console is None:
            return
        self.console.print("\n[bold red]Errors:[/bold red]")
        for locale, message in errors.items():
            # escape: [...] inside error messages must not be eaten as markup
            self.console.print(f"  [red]{locale}[/red]: {escape(message)}")


# ── Factory ─────────────────────────────────────────────────────


# How often (seconds) a progress line is printed in degraded mode
_PROGRESS_INTERVAL = 3.0


@asynccontextmanager
async def translation_progress(
    locale_totals: dict[str, int],
    *,
    show_progress: bool,
) -> AsyncIterator[ProgressHandle]:
    """Set up the progress UI for ``locale_totals`` (locale -> item count).

    Display order follows the insertion order of ``locale_totals``.
    Automatic degradation:
    - ``show_progress=False`` / total of 0 → no-op
    - non-terminal / dumb terminal → ``LineReporter``
    - real terminal → rich ``Progress``
    """
    total = sum(locale_totals.values())
    if not show_progress or total == 0:
        yield ProgressHandle(locale_order=list(locale_totals), locale_totals=locale_totals)
        return

    console = Console(stderr=True)  # force_terminal defaults to None = auto-detect
    if not console.is_terminal or console.is_dumb_terminal:
        reporter = LineReporter(console, summary=_make_summary(locale_totals), interval=_PROGRESS_INTERVAL)
        with reporter:
            parent = reporter.add_task("Total", total=total)
            children: dict[str, Any] = {}
            n = len(locale_totals)
            for i, (locale, count) in enumerate(locale_totals.items(), start=1):
                children[locale] = reporter.add_task(_child_desc(locale, i, n), total=count)
            yield ProgressHandle(
                reporter=reporter,
                console=console,
                parent=parent,
                children=children,
                locale_order=list(locale_totals),
                locale_totals=locale_totals,
            )
        return

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    )
    with progress:
        progress_parent = progress.add_task("Total", total=total)
        progress_children: dict[str, Any] = {}
        n = len(locale_totals)
        for i, (locale, count) in enumerate(locale_totals.items(), start=1):
            progress_children[locale] = progress.add_task(_child_desc(locale, i, n), total=count)
        yield ProgressHandle(
            live=progress,
            console=console,
            parent=progress_parent,
            children=progress_children,
            locale_order=list(locale_totals),
            locale_totals=locale_totals,
        )
