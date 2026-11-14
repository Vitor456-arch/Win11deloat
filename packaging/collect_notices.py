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
    if name in ('PySide6-Essentials', 'shiboken6') and not found:
        raise RuntimeError(f'No license files found for {name}; refusing incomplete bundle')
(destination / 'VERSIONS.txt').write_text('\n'.join(versions) + '\n', encoding='utf-8')
print('\n'.join(versions))
