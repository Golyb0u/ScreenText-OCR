"""One-shot migration of the pre-2.2 user state.

Version 2.2 renamed the product to "ScreenText OCR". That rename also moved
two things that live outside the package: the profile folder under
``%LOCALAPPDATA%`` and the ``QSettings`` identity (organization plus
application name). Without a migration an upgrading user would start with an
empty profile list and the default theme, which looks exactly like a fresh
install and loses their data.

The migration only ever *copies*: the legacy folder and the legacy settings
store are left untouched, so downgrading still works and a half-finished
migration can be repeated. Every step is guarded, because a failure here must
never stop the application from starting.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from PyQt5 import QtCore

from .config import APP_NAME, CONFIG_DIR, ORG_NAME

#: Identity of the settings store used before the rename.
LEGACY_ORG_NAME = "TesseractStudio"
LEGACY_APP_NAME = "Tesseract OCR Studio"


def _local_appdata() -> Optional[Path]:
    value = os.environ.get("LOCALAPPDATA", "").strip()
    return Path(value) if value else None


def _legacy_profiles_dir() -> Optional[Path]:
    """``%LOCALAPPDATA%\\TesseractStudio\\configs``, or None without LOCALAPPDATA."""
    root = _local_appdata()
    return root / LEGACY_ORG_NAME / "configs" if root is not None else None


def _profile_files(folder: Optional[Path]) -> list[Path]:
    if folder is None:
        return []
    try:
        return sorted(path for path in folder.glob("*.json") if path.is_file())
    except OSError:
        return []


def _migrate_profiles(target: Optional[Path], legacy: Optional[Path]) -> None:
    """Copy legacy ``*.json`` profiles into an as yet unpopulated target folder."""
    if target is None or legacy is None:
        return
    try:
        if target.resolve() == legacy.resolve():
            return
    except OSError:
        return
    # A folder that already holds profiles belongs to the user: never merge
    # into it, an old ``default.json`` would silently override the current one.
    if _profile_files(target):
        return
    sources = _profile_files(legacy)
    if not sources:
        return
    for source in sources:
        destination = target / source.name
        if destination.exists():
            continue
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        except OSError:
            continue


def _migrate_settings() -> None:
    """Copy the legacy ``QSettings`` tree into the new identity."""
    current = QtCore.QSettings(ORG_NAME, APP_NAME)
    if current.allKeys():
        # Something already stored settings under the new name; keep it.
        return
    legacy = QtCore.QSettings(LEGACY_ORG_NAME, LEGACY_APP_NAME)
    keys = legacy.allKeys()
    if not keys:
        return
    for key in keys:
        value = legacy.value(key)
        if value is None:
            continue
        current.setValue(key, value)
    current.sync()


def migrate_legacy_state(
    profiles_dir: Optional[Path] = None,
    legacy_profiles_dir: Optional[Path] = None,
) -> None:
    """Bring pre-2.2 profiles and settings over to the new locations.

    Idempotent and silent: running it twice changes nothing, and any error is
    swallowed so a broken upgrade path never blocks the application. The two
    keyword arguments only exist so a test can point the copy at a temporary
    folder instead of the real ``%LOCALAPPDATA%``.
    """
    try:
        _migrate_profiles(
            Path(profiles_dir) if profiles_dir is not None else CONFIG_DIR,
            Path(legacy_profiles_dir)
            if legacy_profiles_dir is not None
            else _legacy_profiles_dir(),
        )
    except Exception:  # noqa: BLE001 - migration is strictly best effort
        pass
    try:
        _migrate_settings()
    except Exception:  # noqa: BLE001 - migration is strictly best effort
        pass
