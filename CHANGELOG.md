# Changelog

All notable changes to **ScreenText OCR** (formerly **Tesseract OCR Studio**)
are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Visual language ported from **Golyb0u Flat UI 2.1.0**: the dark shell is a
  navy board with a radial bloom, cards float above it as translucent navy
  tiles with a hairline and a soft ambient shadow, and the accent is azure.
- `ui/card_paint.py`: cards paint their own surface (gradient, 1 px border,
  layered shadow) instead of relying on a flat QSS fill, so the board stays
  visible through the tiles. Painting stands down in `--system` mode.
- Theme helpers for painter-based widgets: `resolve_tokens()` is now the single
  source of truth for accent, mark, radius and font in both variants,
  `publish_tokens()` / `active_tokens()` share the active palette, and
  `painted_palette()`, `log_palette()`, `tooltip_palette()` and
  `panel_palette()` expose resolved inks to the cards, console, tooltips and
  help panel.

### Changed

- Accent default changed from cyan `#37b6d6` to azure `#0b6ee8` with a lighter
  azure hover. Primary buttons use the azure fill, secondary buttons a
  flat steel blue (`#173a5c`, hover `#24527f`, pressed `#0f2b49`), danger a
  flat wine.
- The four settings tabs are rounded pills; the active one is a solid azure
  pill with a white label. The toolbar became a glass gradient strip
  with chip buttons, the dock title is accent-tinted, the status bar is
  transparent and the Windows title bar follows the theme.
- Inputs sit on a flat card surface with a bottom hairline and a 2 px azure
  focus underline; combo popups and menus use a dark diagonal gradient with a
  blue hover ramp, and scrollbar thumbs use an azure ramp.
- Help, the activity console, rich tooltips and the full-screen region selector
  follow the same navy/azure palette; diagnostics use the new success, warn
  and danger inks. Icons are recoloured from the active theme.
- The light palette is preserved and re-derived as white tiles on a pale azure
  board with the same layout and radii. The appearance inspector still exposes
  variant, accent, radius (0-20, default 10), font family and size, and the
  live QSS export still works.
- Theme tokens, painted cards, light surfaces, selection ink, navigation fit and
  the painted chevrons were re-checked against the running window.
- The three README screenshots were re-captured at 1600x950 from the new build.
- The toolbar now holds only the capture/OCR workflow: region, capture, open,
  paste, the primary OCR-frame button, OCR region and the activity-log toggle.
  Theme and appearance moved out of it to icon-only buttons in the menu-bar
  corner, immediately left of the language chip. The language menu is two
  icon-aligned rows, `Русский (RU)` and `English (EN)`, with a check for the
  active language and a globe for the other, so both captions share one text
  column, and the chip is a fixed-height 28 px symmetric pill.
- Combo-box popups reuse the menu dropdown surface: a single rounded panel with
  the same row padding, radius, hover wash and selected-row gradient, so the
  rows no longer read as separate dark blocks.
- The corner language selector became a dedicated globe chip with an uppercase
  code, a hairline border and a painted chevron, the version chip left the
  toolbar for the window title and the About dialog, and the status plaque
  above the workspace is gone, so transient messages live in the status bar.
  Dropdown, spin-box, menu and header sort arrows are painted PNG chevrons
  instead of CSS border triangles, the splitter seam warms to a translucent
  azure wash on hover with softer scrollbar thumbs, the settings navigation is
  an icon-free pill row that fits all four captions, and the application icon
  and `docs/logo.png` show a centred 3x3 azure grid on the navy tile.

### Fixed

- Changing the interface language or closing the application no longer crashes
  on a stale soft tooltip. A queued Enter/Leave event could arrive after the
  parentless `SoftToolTip` had been deleted, raising
  `RuntimeError: wrapped C/C++ object of type SoftToolTip has been deleted`; the
  help panel now guards the access and recreates the tooltip lazily.
- Language switching works when the app is launched through the pip console
  script. The restart helper passed the generated `.exe` launcher to
  `python.exe`; it now detects frozen builds, `.py` entry points and
  console-script launchers separately.

## [2.2.0] - 2026-11-18

### Changed

- The project is now called **ScreenText OCR** (was "Tesseract OCR Studio").
  The Python package moved from `tesseract_studio` to `screentext_ocr`, the
  console scripts are `screentext-ocr` and `screentext-ocr-gui`, the PyInstaller
  spec is `ScreenTextOCR.spec` and the packaged executable is `ScreenTextOCR.exe`.
- The GitHub repository was renamed to `ScreenText-OCR`; GitHub keeps redirects
  from the old `Tesseract_OCR_Studio` URLs, so existing links, clones and badges
  keep working.

### Added

- Automatic migration of existing user settings and OCR profiles. On the first
  launch of 2.2.0 the old `%LOCALAPPDATA%\TesseractStudio\configs` profile
  folder and the old `QSettings` registry subtree are copied to the new
  locations, so saved profiles and preferences survive the rename.
- New `SCREENTEXT_*` environment variables: `SCREENTEXT_CONFIG_DIR`,
  `SCREENTEXT_SETTINGS`, `SCREENTEXT_LANG` and `SCREENTEXT_NO_RESTART`.

### Deprecated

- The `TESSERACT_STUDIO_*` environment variables still work as aliases but are
  deprecated. They will be removed in a future major release; use the
  `SCREENTEXT_*` names instead.

### Docs

- README rewritten with a bilingual RU/EN quick start, an FAQ and broader SEO
  keyword coverage.

## [2.1.0] - 2026-11-07

### Added

- Complete Russian/English UI localization with a language selector in the toolbar
  and a `--lang ru|en` command-line flag.
- English contextual help (`help_texts_en.py`) and English translations for every
  status, dialog, diagnostic and OCR preset.
- GitHub release readiness: MIT license, `pyproject.toml`, CI matrix for Windows,
  tag-driven Windows release workflow, issue templates and changelog.
- Single instance guard. A second launch now brings the running window to the
  front and exits instead of opening another window. The lock is a named
  shared memory segment, because `QLocalServer` lets two processes in the same
  Windows session listen on the same name.
- Demo animation `docs/demo.gif` that records a real OCR run against Tesseract
  5.x: frame loading, parameter setup and the recognised text.

### Removed

- The legacy `app.py` entry point and every trace of it. It only forwarded to
  `main.py`, so `python main.py` and the `tesseract-ocr-studio` console script
  are now the only supported ways to start the application.

### Changed

- Version bumped to 2.1.0.
- Language changes restart the application cleanly so every page, help text and
  dialog is rebuilt in the selected language.
- README expanded with language switching, release and localization instructions.
- Repository prepared for the public GitHub release: screenshots moved to
  `docs/screenshots/`, `.gitignore` extended with secrets, coverage and OS
  artefacts, README restructured with badges, environment variables, usage
  examples, limitations and roadmap.
- Windows is now the only supported platform: the CI matrix, documentation,
  issue templates and package classifiers drop Linux and macOS.
- Long dashes were replaced with plain hyphens in the interface copy and the
  documentation. The Russian string is the translation key, so the Russian and
  English catalogues were updated together.
- The three README screenshots were re-captured from the current build so the
  visible text matches the shipped interface.
- The `.gitignore` no longer hides the PyInstaller spec file that the release
  workflow needs.

### Fixed

- The application no longer flashes a dozen empty windows while it starts. Card
  titles, card hints and the status banner were made visible before they had a
  parent, and a parentless widget that is shown turns into its own top-level
  window. The labels are now added to their layout before they are shown.
- Switching the interface language no longer crashes the application. The
  restart helper unpacked the result of `QProcess.startDetached` as a tuple,
  but the two-argument overload returns a plain bool, which raised a
  `TypeError` right after the language had been saved.
- A package installed with `pip install .` no longer writes its profiles into
  `site-packages`. The profile folder now resolves to
  `%LOCALAPPDATA%\TesseractStudio\configs` when the application runs from an
  installed package, while a source checkout and the packaged executable keep
  their previous locations.
- Status bar messages no longer overlap the permanent status labels.
- Light theme accent colours are darkened for readable titles and toolbar labels.
- Missing `rus.traineddata` is reported explicitly by the diagnostics panel.
- ComboBox popups no longer show white platform bands around the dark rounded
  list; the popup container follows the active palette.
- Tab labels such as "Обработка" no longer clip at the edges; the navigation
  tabs now reserve room for bold translated text and carry matching icons.
- The settings column keeps enough width for buttons and wrapped hints at the
  minimum window size.

## [2.0.0] - 2026-11-06

### Added

- GUI ported from **Qt UI Lab**: token-based dark/light theme, gradient shell,
  flat cards, painted indicators, appearance inspector, activity console,
  live help and rich tooltips.
- Modular `tesseract_studio` package split from the old monolithic `app.py`.
- Bilingual RU/EN README, screenshots and a sample OCR image.
- Automated checks covering configuration, preprocessing, theme, window and profiles.

### Changed

- New entry point `main.py`; `app.py` remains a compatibility wrapper.
- Updated PyInstaller spec and runtime requirements.
