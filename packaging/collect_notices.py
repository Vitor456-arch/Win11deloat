"""Retain original dependency license files and record exact installed versions."""
from importlib import metadata
from pathlib import Path
import shutil
import sys

app = Path(sys.argv[1])
destination = app / 'third-party-licenses'
destination.mkdir(parents=True, exist_ok=True)
names = ['PySide6-Essentials', 'shiboken6', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'packaging', 'pefile', 'pywin32-ctypes', 'setuptools']
versions = []
for name in names:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        continue
    versions.append(f'{dist.metadata["Name"]}=={dist.version}')
    found = 0
    for file in dist.files or []:
        lower = str(file).lower()
        if any(part in lower for part in ('license', 'copying', 'copyright', 'notice')):
            source = Path(dist.locate_file(file))
            if source.is_file():
                # Package-relative paths keep identically named licenses distinct.
                relative = Path(*[p for p in Path(file).parts if p not in ('.', '..')])
                target = destination / name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                found += 1
    if name in ('PySide6-Essentials', 'shiboken6'):
        # Some official wheels declare LGPL in metadata without shipping texts.
        target = destination / name
        shutil.copytree(Path(__file__).parent / 'licenses', target, dirs_exist_ok=True)
        (target / 'PACKAGE-METADATA.txt').write_text(str(dist.metadata), encoding='utf-8')
(destination / 'VERSIONS.txt').write_text('\n'.join(versions) + '\n', encoding='utf-8')
print('\n'.join(versions))

python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.is_file():
    shutil.copy2(python_license, destination / 'CPython-LICENSE.txt')
versions_file = destination / 'PYTHON-VERSION.txt'
versions_file.write_text(sys.version + '\n', encoding='utf-8')
