#!/usr/bin/env python3
"""Build a standalone Windows executable for desk-pricer."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / "desk-pricer.spec"
ENTRY_SCRIPT = PROJECT_ROOT / "scripts" / "run_desk_pricer.py"


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
    old_dist = DIST_DIR / "desk-pricer"
    old_exe = DIST_DIR / "desk-pricer.exe"
    if old_dist.exists():
        print(f"Removing {old_dist} ...")
        shutil.rmtree(old_dist)
    if old_exe.exists():
        print(f"Removing {old_exe} ...")
        old_exe.unlink()


def build(onefile: bool = True, windowed: bool = False):
    env_python = sys.executable
    clean()

    mode = "--onefile" if onefile else "--onedir"
    console_flag = "--windowed" if windowed else "--console"

    cmd = [
        env_python,
        "-m",
        "PyInstaller",
        "--name", "desk-pricer",
        mode,
        console_flag,
        "--noconfirm",
        "--clean",
        # Add src/ to PYTHONPATH so imports work inside the bundle
        "--paths", str(SRC_DIR),
        # Hidden imports that PyInstaller might miss
        "--hidden-import", "desk_pricer.app",
        "--hidden-import", "desk_pricer.pricing.american",
        "--hidden-import", "desk_pricer.pricing.european",
        "--hidden-import", "desk_pricer.pricing.engine",
        "--hidden-import", "desk_pricer.pricing.cross_greeks",
        "--hidden-import", "desk_pricer.pricing.implied_vol",
        "--hidden-import", "desk_pricer.pricing.conventions",
        "--hidden-import", "desk_pricer.errors",
        "--hidden-import", "desk_pricer.responses",
        "--hidden-import", "desk_pricer.schemas",
        "--hidden-import", "desk_pricer.main",
        # Data files
        "--add-data", f"{PROJECT_ROOT / 'pyproject.toml'};.",
        str(ENTRY_SCRIPT),
    ]

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    if onefile:
        artifact = DIST_DIR / "desk-pricer.exe"
        size_mb = artifact.stat().st_size / (1024 * 1024)
        print(f"\nBuild complete: {artifact}")
        print(f"Size: {size_mb:.1f} MB")
    else:
        artifact = DIST_DIR / "desk-pricer"
        print(f"\nBuild complete: {artifact}")
        print(f"Run with: {artifact / 'desk-pricer.exe'}")


def main():
    parser = argparse.ArgumentParser(description="Build desk-pricer standalone executable")
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
