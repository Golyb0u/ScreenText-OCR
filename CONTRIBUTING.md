# Contributing

Thanks for improving **ScreenText OCR**.

## Development setup

```bash
git clone https://github.com/Golyb0u/ScreenText-OCR.git
cd ScreenText-OCR
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Tesseract OCR 5.x must be installed separately, see the setup section in
`README.md`.

## Project structure

```text
main.py                  Launcher used during development
ScreenTextOCR.spec       PyInstaller recipe for the Windows build
requirements.txt         Runtime dependencies
configs/default.json     Default OCR profiles shipped with the release
screentext_ocr/          Application package (config, OCR, imaging, UI)
docs/                    Screenshots and the demo animation
.github/workflows/       CI and tag-driven release
```

## Localization

- The Russian source string is the translation key.
- Add English values to `screentext_ocr/translations_en.py`.
- Contextual help lives in `ui/help_texts.py` (RU) and `ui/help_texts_en.py` (EN).
- After touching UI copy, switch to English with the language chip or launch with
  `python main.py --lang en` and check that no Cyrillic text is left in English
  mode and that every string resolves.
- When adding a new language, extend `i18n.LANGUAGES` and provide a catalogue
  module; the language selector and the `--lang` flag are data-driven.

## Documentation

- Keep `README.md` bilingual: the Russian and English sections describe the same
  features and must be updated together.
- Do not use long dashes in documentation or in the interface copy. Use a plain
  hyphen. Two hyphens in a row are allowed only where they are part of real
  syntax, for example a command-line flag or a `pip` option.
- Every new screenshot belongs in `docs/screenshots/` and must be referenced from
  both language sections.
- The demo animation `docs/demo.gif` is produced by driving the real window and
  running a real OCR pass. Keep the captured frames free of local paths.

## Renaming: what is stable

The project was renamed from **Tesseract OCR Studio** to **ScreenText OCR** in
2.2.0. Some names are part of the public contract: they appear in user scripts,
shortcuts, documentation and in data that already sits on users' disks. Do not
rename them again without a major release and a migration path.

- The Python package `screentext_ocr` and the `screentext-ocr` and
  `screentext-ocr-gui` console scripts.
- The `SCREENTEXT_*` environment variables: `SCREENTEXT_CONFIG_DIR`,
  `SCREENTEXT_SETTINGS`, `SCREENTEXT_LANG` and `SCREENTEXT_NO_RESTART`.
- The on-disk locations for profiles and settings, including the data migrated
  from the old `%LOCALAPPDATA%\TesseractStudio\configs` folder and the old
  `QSettings` subtree.

The legacy `TESSERACT_STUDIO_*` environment variables must keep working as
aliases. Mark them as deprecated in the docs first and remove them only in a
major release.

## Pull requests

- Keep changes focused and describe the user-visible effect.
- Check the import and the build before opening the pull request:
  `python -c "import screentext_ocr, screentext_ocr.app"` and
  `python -m PyInstaller --noconfirm --clean ScreenTextOCR.spec`.
- Update `CHANGELOG.md` for user-visible changes.
- Do not commit `dist/`, virtual environments, caches or personal profiles.

## Release checklist

1. Bump `APP_VERSION` in `screentext_ocr/config.py` and `pyproject.toml`.
2. Update `CHANGELOG.md` and confirm the new `## [X.Y.Z]` section is present:
   the release workflow copies that section into the GitHub release body.
3. Make sure CI is green on `main`: it installs the runtime dependencies,
   imports the package and builds the executable from the spec.
4. Tag the commit: `git tag -a vX.Y.Z -m "vX.Y.Z"` and push the tag.
5. `.github/workflows/release.yml` builds the Windows executable and publishes
   the release assets automatically. If the build fails after the tag is pushed,
   re-run the workflow manually (`workflow_dispatch`) with that tag instead of
   deleting and re-pushing it.
