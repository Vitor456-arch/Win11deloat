# Third-party components

Original Clear Windows code is MIT-licensed. Dependency code is not relicensed.

- **Qt for Python / PySide6 Essentials / Shiboken6**: Qt Company and contributors; LGPLv3/GPLv3/commercial options, with component-specific licenses. See installed distribution license files and https://doc.qt.io/qtforpython-6/licenses.html . Choose a compliant licensing/distribution approach before shipping an executable, preserve notices, and fulfill applicable LGPL obligations. This repository does not grant a commercial Qt license.
- **pytest** (development): MIT and included dependency notices.
- **PyInstaller** (optional packaging): GPL with bootloader exception; see https://pyinstaller.org/en/stable/license.html .

A source install dynamically uses separately installed Qt packages. An unsigned packaged artifact produced by CI is a development artifact, not a license-reviewed production release. Review bundled dependencies and supply required notices and source/relinking information before distributing it.

## Binary development bundles

The Setup and portable ZIP use PyInstaller's **onedir** layout with separate
DLLs and extension modules in `_internal`. Qt remains dynamically linked. No
restriction on replacing compatible Qt DLLs, or reverse engineering to debug
modifications to the LGPL libraries, is imposed by Clear Windows. Keep the
original library notices with redistributed copies.

`third-party-licenses/` in each binary bundle preserves license files from the
installed distributions; `VERSIONS.txt` records their exact versions.
Corresponding unmodified upstream sources are available from the original
projects, including versioned archives/tags:

- Qt: https://download.qt.io/archive/qt/ and https://code.qt.io/cgit/qt/
- Qt for Python (PySide / Shiboken): https://download.qt.io/official_releases/QtForPython/ and https://code.qt.io/cgit/pyside/pyside-setup.git/
- CPython: https://www.python.org/downloads/source/
- PyInstaller: https://github.com/pyinstaller/pyinstaller
- Clear Windows source: https://github.com/Vitor456-arch/Win11deloat

Refer to each bundled license for its terms. The upstream source tags must match
the exact versions recorded in the bundle; this project does not modify Qt,
Shiboken, CPython or the PyInstaller bootloader.
