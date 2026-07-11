"""Minimal Windows hook for the SciPy ndimage subset used by 723 Manga Upscaler."""

# The stock PyInstaller hook bundles scipy.libs unconditionally. The application uses
# ndimage's filtering, morphology, interpolation, and measurement extensions,
# none of which link to SciPy's OpenBLAS DLL. Keep only SciPy's small utility
# extensions that are imported by the package itself.
hiddenimports = [
    "scipy._lib.messagestream",
    "scipy._lib._ccallback_c",
    "scipy._lib._fpumode",
]
