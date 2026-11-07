# Publishing ScreenText OCR

Runbook for the 2.2.0 release, the one that renames the project from
**Tesseract OCR Studio** to **ScreenText OCR** on GitHub.

Everything here is manual by design:

- The `gh` CLI is **not installed** on this machine, so no step can be scripted
  against the GitHub API from here.
- Renaming the repository and editing the About box requires a signed-in GitHub
  session as the owner (`Golyb0u`), and `git push` needs the owner's
  credentials. No agent or tool can do it on the owner's behalf.

Work from the repository root in PowerShell:

```powershell
cd <repo>
```

Do the GitHub UI steps (1-3) first: they are instant, reversible, and they make
the local push in step 4 land on the already-renamed repository.

## Step 1 - Rename the repository on GitHub

1. Open <https://github.com/Golyb0u/Tesseract_OCR_Studio>.
2. **Settings** (top bar) -> **General**.
3. In **Repository name**, replace `Tesseract_OCR_Studio` with `ScreenText-OCR`.
4. Click **Rename**.

What happens:

- GitHub keeps a permanent redirect from every old
  `github.com/Golyb0u/Tesseract_OCR_Studio/...` URL to the new one, including
  clone, raw, issue and release links. Existing clones keep fetching and
  pushing without a warning.
- Stars, watchers, forks, issues, pull requests, releases, Actions history and
  the repository settings are preserved; only the name and the URLs change.
- The old URL keeps working indefinitely, so README badges and any link that
  still says `Tesseract_OCR_Studio` will resolve. Update them anyway when the
  chance comes up.

## Step 2 - Set the About box

On the repository home page click the gear icon next to **About** (or
**Settings -> General -> Description**) and paste the English description
(148 characters):

```text
Windows OCR app: screenshot or screen area → text on your clipboard in seconds. Offline Tesseract 5, no cloud, no telemetry, ready for any LLM chat.
```

A bilingual alternative (138 characters) is:

```text
OCR для Windows: текст с экрана или скриншота в буфер за секунды. Офлайн, без облака и телеметрии. Local Tesseract 5, LLM-ready, RU/EN UI.
```

In the same panel:

- **Releases**: ticked. The tag-driven workflow publishes the Windows build
  there, so it must be visible on the landing page.
- **Packages**: unticked. Nothing is published to GitHub Packages; the Windows
  build is shipped as a GitHub release, and the Python package can be installed
  from the repository with `pip install .`.
- **Website**: leave empty.

Save with **Set description**.

## Step 3 - Add Topics

In the same **About** panel click the gear next to **Topics** and paste all 20
comma-separated topics:

```text
ocr, ocr-recognition, tesseract, tesseract-ocr, screenshot-to-text, image-to-text, text-extraction, screen-capture, screen-text, screenshot, clipboard, windows, windows-app, desktop-app, pyqt5, python, opencv, offline, local-first, privacy
```

GitHub keeps at most 20 topics; do not add extras to this list. Deliberately
excluded: `llm`, `chatgpt`, `openai`, `neural-network`, `lstm`,
`machine-learning`, `ai`. The program runs Tesseract 5 locally and ships no
model, so those tags would mislead both users and search.

## Step 4 - Update the local remote and push

Review what is about to be published, then point the remote at the new name and
push:

```powershell
git remote set-url origin https://github.com/Golyb0u/ScreenText-OCR.git
git remote -v
git status
git push origin main
```

The rename, the cleanup and the documentation rewrite are already committed
locally as `feat!: rename project to ScreenText OCR (v2.2.0)`, so a clean
`git status` means there is nothing left to add and the push is the only
remaining step. If you change something first, stage and commit it with:

```powershell
git add -A
git commit -m "chore: post-rename adjustments"
```

`git remote -v` must show the new URL for both `fetch` and `push`. The `!` in
the commit subject is intentional: the package rename is a breaking change for
`pip install` users.

Before pushing, confirm the packaging side of the rename is in place; the
release job reads the spec path and the asset names literally:

```powershell
git grep -n "TesseractOCRStudio" -- .github pyproject.toml "*.spec" main.py
```

The command should print nothing. If `.github/workflows/release.yml` still
mentions `TesseractOCRStudio.spec`, the tag below will fail to build.

### Tag the release

```powershell
git tag -a v2.2.0 -m "ScreenText OCR 2.2.0"
git push origin v2.2.0
```

Pushing the tag starts `.github/workflows/release.yml`, which:

1. installs the runtime requirements and builds `dist/ScreenTextOCR.exe` with
   PyInstaller from `ScreenTextOCR.spec`;
2. zips the executable with the `configs/` folder as
   `dist/ScreenTextOCR-windows.zip`;
3. publishes a GitHub release for the tag with both assets attached.

The release body is cut from `CHANGELOG.md`: the workflow copies the
`## [2.2.0]` section into the release notes, so make sure that section is
committed before tagging.

## Step 5 - Verify

Run through this list once the push and the tag have landed:

- **CI badge**: the badge at the top of `README.md` renders and its workflow run
  is green. The new URL form is
  `https://github.com/Golyb0u/ScreenText-OCR/actions/workflows/ci.yml/badge.svg`.
- **Release assets**: open <https://github.com/Golyb0u/ScreenText-OCR/releases>
  and check that `v2.2.0` carries exactly `ScreenTextOCR.exe` and
  `ScreenTextOCR-windows.zip`. Any asset still named `TesseractOCRStudio*`
  means the workflow was not updated before tagging.
- **Old URL redirect**: this must print the same commit as `main`:

  ```powershell
  git ls-remote https://github.com/Golyb0u/Tesseract_OCR_Studio.git HEAD
  git ls-remote https://github.com/Golyb0u/ScreenText-OCR.git HEAD
  ```

- **Search**: typing `ScreenText OCR` into the GitHub search bar finds the
  repository with the new About text and the 20 topics.
- **Fresh clone**: `git clone https://github.com/Golyb0u/ScreenText-OCR.git`
  in a temporary folder, then `python main.py` starts the renamed app.

## Step 6 - Post-rename cleanup checklist

- [x] **`docs/screenshots/*.png` and `docs/demo.gif` are re-captured.** Commit
      `4db5c90` regenerated all three screenshots, the demo GIF and the sample
      frame from the 2.2.0 build, so the old "TESSERACT STUDIO" wordmark is no
      longer baked into the pixels.
- [ ] **Confirm the About box and the 20 topics** are the values listed in steps 2
      and 3 above - a rename resets the URL, not the text, but it is the one
      moment to double-check both.
- [ ] **Tell users that settings migrate automatically.** Either pin an issue
      titled "Upgrading to 2.2.0: your profiles and settings are kept" or add one
      line to the top of the release notes: on first launch 2.2.0 copies the old
      `%LOCALAPPDATA%\TesseractStudio\configs` folder and the old `QSettings`
      subtree, and the `TESSERACT_STUDIO_*` variables still work as deprecated
      aliases.
- [ ] Update any external link that is not covered by the GitHub redirect:
      CI badges in other repositories, blog posts, package manager manifests.
- [ ] Delete stale local clones that still point at the old remote, or run
      `git remote set-url origin https://github.com/Golyb0u/ScreenText-OCR.git`
      inside them.

## Rollback

Renaming the repository back on GitHub is possible at any time (**Settings ->
General -> Repository name**) and works instantly; issues, stars and releases
travel with it and the redirect simply reverses. Only the local remote has to
be pointed at the old URL again.

The part that cannot be rolled back so easily is the code-level rename: the
Python package `tesseract_studio` -> `screentext_ocr` and the
`TESSERACT_STUDIO_*` -> `SCREENTEXT_*` environment variables are a breaking
change for anyone who does `pip install screentext-ocr` or imports the package.
That is why the legacy environment variables stay supported as deprecated
aliases and why the old settings locations are migrated rather than dropped.
