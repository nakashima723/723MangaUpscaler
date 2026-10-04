from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "mlu"
ALLOWED_NDIMAGE_CALLS = {
    "binary_closing",
    "binary_dilation",
    "binary_propagation",
    "convolve",
    "distance_transform_edt",
    "gaussian_filter",
    "gaussian_filter1d",
    "generate_binary_structure",
    "grey_closing",
    "label",
    "map_coordinates",
    "maximum_filter",
}


def test_frozen_scipy_stub_covers_every_application_ndimage_call() -> None:
    used_calls: set[str] = set()
    for source_path in SRC_ROOT.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "ndimage"
            ):
                used_calls.add(node.func.attr)

    assert used_calls
    assert used_calls <= ALLOWED_NDIMAGE_CALLS


def test_onefile_build_keeps_only_supported_image_and_scipy_features() -> None:
    script = (REPO_ROOT / "tools" / "build_gui_exe.ps1").read_text(encoding="utf-8")

    assert "--onefile" in script
    assert "--noupx" in script
    assert "--version-file $VersionFile" in script
    assert "$CustomTkinterPath\\assets;customtkinter\\assets" in script
    assert "--exclude-module PIL._avif" in script
    assert "--exclude-module scipy.special" in script
    assert "--additional-hooks-dir $HookDirectory" in script
    assert "--runtime-hook $SciPyRuntimeHook" in script
    assert "Resolve-OfficialMsvcRedistributable" in script
    assert "Get-AuthenticodeSignature" in script
    assert "O=Microsoft Corporation" in script
    assert "ImageMagick" in script
    assert "--exclude-module win32pdh" in script


def test_release_dependencies_and_ci_actions_are_immutable() -> None:
    lock = (REPO_ROOT / "requirements-release.txt").read_text(encoding="utf-8")
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (
        REPO_ROOT / ".github" / "workflows" / "signpath-release.yml"
    ).read_text(encoding="utf-8")

    requirement_lines = [line for line in lock.splitlines() if "==" in line]
    hash_lines = [line for line in lock.splitlines() if "--hash=sha256:" in line]
    assert requirement_lines
    assert len(requirement_lines) == len(hash_lines)
    assert "--require-hashes" in ci
    assert "--require-hashes" in release
    assert "actions/checkout@v" not in ci + release
    assert "actions/setup-python@v" not in ci + release
    assert "actions/upload-artifact@v" not in release
    assert "signpath/github-action-submit-signing-request@v" not in release
    assert "vars.SIGNPATH_SUBMISSION_ENABLED == 'true'" in release
    assert "RELEASE_TAG: ${{ inputs.release_tag }}" in release
    assert "git check-ref-format \"refs/tags/${{ inputs.release_tag }}\"" not in release
    assert "$metadata.ProductVersion -ne \"${{ inputs.product_version }}\"" not in release
    assert "$metadata.FileVersion -ne \"${{ inputs.file_version }}\"" not in release
    assert "project-slug: ${{ vars.SIGNPATH_PROJECT_SLUG }}" in release


def test_public_tree_excludes_unlicensed_local_material() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "images/input/" in gitignore
    assert "docs/assets/" in gitignore
    assert "reviews/" in gitignore
    assert (REPO_ROOT / "examples" / "synthetic_lineart.png").is_file()
    assert "images\\input" not in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_distribution_license_collector_includes_roboto_notice() -> None:
    collector = (REPO_ROOT / "tools" / "collect_distribution_licenses.py").read_text(
        encoding="utf-8"
    )

    assert "Roboto-Apache-2.0-LICENSE.txt" in collector
    assert "Roboto-NOTICE.txt" in collector


def test_authenticode_release_scripts_fail_closed_and_do_not_store_private_keys() -> None:
    signing_script = (REPO_ROOT / "tools" / "sign_gui_exe.ps1").read_text(encoding="utf-8")
    verification_script = (REPO_ROOT / "tools" / "verify_gui_signature.ps1").read_text(
        encoding="utf-8"
    )
    release_script = (REPO_ROOT / "tools" / "build_signed_gui_exe.ps1").read_text(
        encoding="utf-8"
    )
    authenticode_module = (REPO_ROOT / "tools" / "AuthenticodeTools.psm1").read_text(
        encoding="utf-8"
    )
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert '"/fd", "SHA256"' in signing_script
    assert '"/tr", $TimestampServer.AbsoluteUri' in signing_script
    assert '"/td", "SHA256"' in signing_script
    assert '"/sha1", $Thumbprint' in signing_script
    assert "Pfx" not in signing_script
    assert "AllowUntrustedRootForTest" in signing_script
    assert "HashMismatch" in verification_script
    assert "CertificateThumbprint" in release_script
    assert "723MangaUpscaler_unsigned_stage" in release_script
    assert "[IO.File]::Replace" in release_script
    assert '"verify", "/pa", "/all", "/tw", "/v"' in verification_script
    assert "TestTamperDetection" in verification_script
    assert "WaitForExit($TimeoutSeconds * 1000)" in authenticode_module
    assert "$process.Kill($true)" in authenticode_module
    assert "*.pfx" in gitignore
    assert "*.p12" in gitignore
    assert "*.pem" in gitignore
    assert "*.key" in gitignore
