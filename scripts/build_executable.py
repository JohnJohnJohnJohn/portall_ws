#!/usr/bin/env python3
"""Build a standalone Windows executable for DeskPricer."""

import argparse
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / "DeskPricer.spec"
ENTRY_SCRIPT = PROJECT_ROOT / "scripts" / "run_deskpricer.py"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def _get_version() -> str:
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def _major_version() -> str:
    return _get_version().split(".")[0]


def clean():
    """Remove previous build artifacts."""
    for path in (BUILD_DIR, SPEC_FILE):
        if path.exists():
            print(f"Removing {path} ...")
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    # Remove old dist contents so we don't ship stale files
    for pattern in ("DeskPricer*", "deskpricer*"):
        for old in DIST_DIR.glob(pattern):
            print(f"Removing {old} ...")
            if old.is_dir():
                shutil.rmtree(old)
            else:
                old.unlink()


def build(onefile: bool = True, windowed: bool = False):
    env_python = sys.executable

    clean()

    mode = "--onefile" if onefile else "--onedir"
    console_flag = "--windowed" if windowed else "--console"

    cmd = [
        env_python,
        "-m",
        "PyInstaller",
        "--name", "DeskPricer",
        mode,
        console_flag,
        "--noconfirm",
        "--clean",
        # Add src/ to PYTHONPATH so imports work inside the bundle
        "--paths", str(SRC_DIR),
        # Hidden imports that PyInstaller might miss
        "--hidden-import", "deskpricer.app",
        "--hidden-import", "deskpricer.pricing.american",
        "--hidden-import", "deskpricer.pricing.european",
        "--hidden-import", "deskpricer.pricing.engine",
        "--hidden-import", "deskpricer.pricing.cross_greeks",
        "--hidden-import", "deskpricer.pricing.implied_vol",
        "--hidden-import", "deskpricer.pricing.conventions",
        "--hidden-import", "deskpricer.errors",
        "--hidden-import", "deskpricer.responses",
        "--hidden-import", "deskpricer.schemas",
        "--hidden-import", "deskpricer.logging_config",
        "--hidden-import", "deskpricer.main",
        # Uvicorn dynamic imports
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.http.httptools_impl",
        "--hidden-import", "uvicorn.loops.auto",
        # QuantLib native binaries
        "--collect-all", "QuantLib",
        str(ENTRY_SCRIPT),
    ]

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    if onefile:
        raw_exe = DIST_DIR / "DeskPricer.exe"
        versioned_exe = DIST_DIR / f"DeskPricer_v{_major_version()}.exe"
        shutil.move(str(raw_exe), str(versioned_exe))
        size_mb = versioned_exe.stat().st_size / (1024 * 1024)
        print(f"\nBuild complete: {versioned_exe}")
        print(f"Size: {size_mb:.1f} MB")
    else:
        raw_exe = DIST_DIR / "DeskPricer" / "DeskPricer.exe"
        print(f"\nBuild complete: {raw_exe}")
        print(f"Run with: {raw_exe}")


def main():
    parser = argparse.ArgumentParser(description="Build DeskPricer standalone executable")
    parser.add_argument(
        "--onedir", action="store_true",
        help="Build a directory instead of a single file (faster startup)"
    )
    parser.add_argument(
        "--windowed", action="store_true",
        help="Hide the console window (useful for background service)"
    )
    args = parser.parse_args()
    build(onefile=not args.onedir, windowed=args.windowed)


if __name__ == "__main__":
    main()
