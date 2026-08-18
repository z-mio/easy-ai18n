# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.1] - 2026-08-17

### Fixed

- `build()` now automatically removes the source locale from `to_locales` and logs a warning

## [1.2.0] - 2026-08-17

### Added

- LLM translators rebuilt on [pydantic-ai](https://github.com/pydantic/pydantic-ai): `LLMBulkTranslator` (translates
  multiple texts at once) and `LLMItemTranslator` (one text at a time), both accepting a custom `Agent` for local models
  or other providers
- Progress display with percentage and per-locale key change statistics after build
- Concurrent translation across locales with per-locale retry (`concurrent_locales`, `max_retries`)
- `Text` / `TextId` / `TextMap` types for safe text handling
- `UnsupportedSyntaxError` raised when `await` is used inside f-strings, with file/line/source context
- Faster YAML loading via `CSafeLoader` with data validation
- Multilingual README (English / 简体中文 / 日本語)

### Changed

- Translators migrated from `instructor`/OpenAI SDK to pydantic-ai; `googletrans`, `instructor` and `tqdm` became
  optional lazily loaded dependencies (install `easy-ai18n[builder]`)
- English Google-style docstrings across the codebase
- Exception hierarchy refactored under a common `EasyAI18nError` base class
- Strict mypy checks enabled (`disallow_untyped_defs`, `no_implicit_optional`, `warn_return_any`)

### Performance

- Call-site precompilation via `co_positions` with LRU caching for much faster AST parsing and evaluation
- Short-circuit fast path when the source locale is pre-selected, skipping frame parsing and hashing

### Removed

- `enabled_locales` parameter and `get_by_text` method
- `max_concurrency` parameter (concurrency handling moved into the translator base class)
- `tenacity` and `dotenv` dependencies

### Fixed

- None-value checks, parser `KeyError`, build failure status reporting, and async task timeout cancellation

## [1.1.2] - 2026-05-17

### Added

- `mypy` configuration with stricter typing rules
- Test isolation for `locales_dir` via `tmp_path`

### Changed

- `locales_dir` is now a `Path`; `load_locales_file` accepts `list | None` and caches the YAML file list
- Stricter type annotations across loader, parser, builder and translator
- Dependency version lower bounds added (googletrans, loguru, etc.)

## [1.1.1] - 2025-11-05

### Changed

- AST parser now supports more call forms for text extraction
- `ruff` line length set to 120

## [1.1.0] - 2025-10-13

### Changed

- `target_lang` / `to_lang(s)` parameters renamed to `to_locales`; `locales` naming unified across the codebase
- `PostLanguageSelector` renamed to `PostLocaleSelector`; pre/post locale selectors abstracted with an ABC interface
- `load_locale_file` renamed to `load_locales_file`
- Improved type annotations and error messages

## [1.0.3] - 2025-05-28

### Changed

- Logging now supports DEBUG level

## [1.0.2] - 2025-05-27

### Fixed

- Wrong import path (`utiles` → `utils`)

## [1.0.1] - 2025-05-23

### Fixed

- Translation cache key now includes the translation function name and source file name

## [1.0.0] - 2025-04-28

### Changed

- First stable release
- Translation entry point renamed from `t()` to `i18n()`

## 0.0.x Development Series - 2025-04-23 ~ 2025-04-26

Pre-1.0 development iterations that established the core architecture:

- AST-based automatic extraction of translatable strings from source code
- Translation runtime with `PreLocaleSelector` / `PostLocaleSelector` and multi-language content
- Free Google translator and OpenAI translator with batch translation support
- Multiple translation function names and custom separator support
- asyncio-based concurrent translation, performance optimizations
- Python 3.12+ support, initial tests, and the PyPI publishing workflow
