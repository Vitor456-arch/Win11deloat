# Third-party components

Original Clear Windows code is MIT-licensed. Dependency code is not relicensed.

- **Qt for Python / PySide6 Essentials / Shiboken6**: Qt Company and contributors; LGPLv3/GPLv3/commercial options, with component-specific licenses. See installed distribution license files and https://doc.qt.io/qtforpython-6/licenses.html . Choose a compliant licensing/distribution approach before shipping an executable, preserve notices, and fulfill applicable LGPL obligations. This repository does not grant a commercial Qt license.
- **pytest** (development): MIT and included dependency notices.
- **PyInstaller** (optional packaging): GPL with bootloader exception; see https://pyinstaller.org/en/stable/license.html .

A source install dynamically uses separately installed Qt packages. An unsigned packaged artifact produced by CI is a development artifact, not a license-reviewed production release. Review bundled dependencies and supply required notices and source/relinking information before distributing it.
