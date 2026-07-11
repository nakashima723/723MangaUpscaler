# Third-party notices

723 Manga Upscaler's Windows executable embeds the following third-party components.
Their complete license texts and bundled-library notices are stored under
`licenses/third_party` inside the executable's PyInstaller archive.

| Component | License | Project |
| --- | --- | --- |
| CPython and its bundled components | PSF-2.0 and incorporated notices | <https://www.python.org/> |
| Tcl/Tk | Tcl/Tk license | <https://www.tcl.tk/> |
| NumPy, OpenBLAS, LAPACK, and compiler runtimes | BSD-3-Clause and bundled notices | <https://numpy.org/> |
| SciPy | BSD-3-Clause and bundled notices | <https://scipy.org/> |
| Pillow and bundled image libraries | HPND and bundled notices | <https://python-pillow.org/> |
| PyYAML | MIT | <https://pyyaml.org/> |
| CustomTkinter | MIT | <https://github.com/TomSchimansky/CustomTkinter> |
| darkdetect | BSD-3-Clause | <https://github.com/albertosottile/darkdetect> |
| DIPlib / PyDIP | Apache-2.0 | <https://diplib.org/> |
| packaging | Apache-2.0 or BSD-2-Clause | <https://github.com/pypa/packaging> |
| PyInstaller bootloader | GPL-2.0-or-later with bootloader exception | <https://pyinstaller.org/> |
| Microsoft Visual C++ and OpenMP runtimes | Microsoft Visual Studio license; permitted System Libraries | <https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files> |

CustomTkinter's bundled Roboto font files are distributed under the Apache
License, Version 2.0, with their Google copyright notice. The application
itself is also Apache-2.0 licensed; its license text is stored at
`licenses/LICENSE` in the same archive. The Microsoft runtime files are taken
only from an authenticated Visual Studio x64 Redistributable installation and
are included as Windows System Libraries; they are not signed with this
project's certificate individually.
