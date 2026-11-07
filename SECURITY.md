# Security policy

## Supported versions

| Version | Supported |
| - | - |
| 2.2.x | yes |
| < 2.2 | no |

## Reporting a vulnerability

Please report security issues privately through GitHub Security Advisories:

- <https://github.com/Golyb0u/ScreenText-OCR/security/advisories/new>

Do not open a public issue for a vulnerability. Include a description, the affected
version, and the steps needed to reproduce the problem.

You can expect an acknowledgement within a few days. Fixes are published as a new
release together with an entry in `CHANGELOG.md`.

## Scope notes

ScreenText OCR is a local desktop application. It does not send any data to
a remote server. Image data, OCR results and logs stay on the machine where the
application runs.

The application reads and writes:

- profiles in the `configs/` directory (or the directory set through
  `SCREENTEXT_CONFIG_DIR`);
- application settings in the `QSettings` location (or the file set through
  `SCREENTEXT_SETTINGS`);
- images that the user opens explicitly or captures from the screen.

The legacy `TESSERACT_STUDIO_CONFIG_DIR` and `TESSERACT_STUDIO_SETTINGS`
variables are still honoured as aliases for the two settings above; the
`SCREENTEXT_*` names are the documented ones. `SCREENTEXT_LANG` and
`SCREENTEXT_NO_RESTART` (and their legacy aliases) only affect the interface
language and the restart behaviour, they do not change what is stored or where.

No credentials, API keys or tokens are required or stored by the application.

The application starts the Tesseract OCR executable locally to recognise text.
That executable is installed separately by the user and is not part of this
repository.
