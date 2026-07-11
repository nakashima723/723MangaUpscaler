"""Provide the unused scipy.special import expected by scipy.ndimage."""

from __future__ import annotations

import sys
from types import ModuleType


# scipy.ndimage._interpolation imports scipy.special at module load time solely
# for rotate(), which 723 Manga Upscaler does not call. Shipping the real submodule
# would pull in SciPy linalg, sparse, and a second OpenBLAS runtime. A frozen-only
# empty module preserves every ndimage operation used by this application.
sys.modules.setdefault("scipy.special", ModuleType("scipy.special"))
