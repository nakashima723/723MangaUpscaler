"""Collect license texts for every component embedded in the Windows EXE."""

from __future__ import annotations

import shutil
import sys
from importlib import metadata
from pathlib import Path

LICENSE_FILES = {
    "numpy": ("LICENSE.txt", "LICENSES_bundled.txt"),
    "scipy": ("LICENSE.txt",),
    "Pillow": ("licenses/LICENSE",),
    "PyYAML": ("LICENSE",),
    "customtkinter": ("LICENSE",),
    "darkdetect": ("LICENSE",),
    "diplib": ("licenses/LICENSE.txt",),
    "PyInstaller": ("licenses/COPYING.txt",),
    "packaging": ("LICENSE", "LICENSE.APACHE", "LICENSE.BSD"),
}


def _find_distribution_file(distribution_name: str, suffix: str) -> Path:
    distribution = metadata.distribution(distribution_name)
    normalized_suffix = suffix.replace("\\", "/").lower()
    matches = []
    for relative_path in distribution.files or ():
        normalized_path = str(relative_path).replace("\\", "/").lower()
        if normalized_path.endswith(normalized_suffix):
            candidate = Path(distribution.locate_file(relative_path))
            if candidate.is_file():
                matches.append(candidate)
    if not matches:
        raise FileNotFoundError(f"License file not found: {distribution_name}/{suffix}")
    matches.sort(key=lambda path: ("dist-info" not in str(path).lower(), len(str(path))))
    return matches[0]


def collect(output_dir: Path) -> None:
    """Create a clean deterministic directory of third-party license texts."""

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    for distribution_name, suffixes in LICENSE_FILES.items():
        for index, suffix in enumerate(suffixes, start=1):
            source = _find_distribution_file(distribution_name, suffix)
            suffix_name = Path(suffix).name
            target_name = f"{distribution_name}-{index:02d}-{suffix_name}"
            shutil.copyfile(source, output_dir / target_name)

    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise FileNotFoundError(f"Python license file not found: {python_license}")
    shutil.copyfile(python_license, output_dir / "CPython-LICENSE.txt")

    tkinter_license = Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms"
    if not tkinter_license.is_file():
        raise FileNotFoundError(f"Tcl/Tk license file not found: {tkinter_license}")
    shutil.copyfile(tkinter_license, output_dir / "Tcl-Tk-license.terms")

    repo_root = Path(__file__).resolve().parents[1]
    shutil.copyfile(repo_root / "LICENSE", output_dir / "Roboto-Apache-2.0-LICENSE.txt")
    shutil.copyfile(
        repo_root / "licenses" / "Roboto-NOTICE.txt",
        output_dir / "Roboto-NOTICE.txt",
    )


def main() -> int:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/license_bundle")
    collect(output_dir.resolve())
    print(output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
