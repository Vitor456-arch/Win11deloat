"""Explicit read-only packaged-app smoke test, no system modifications."""
import json
from pathlib import Path
import sys
import tempfile
import traceback

from PySide6.QtWidgets import QApplication
from .app import SECTIONS, Window
from .storage import scan


def run():
    args = sys.argv[sys.argv.index('--smoke-test') + 1:]
    if len(args) != 1:
        raise ValueError('Usage: ClearWindows.exe --smoke-test <report.json>')
    report = Path(args[0]).absolute()
    try:
        _run(report)
    except Exception:
        report.write_text(json.dumps({'ok': False, 'error': traceback.format_exc()}), encoding='utf-8')
        raise SystemExit(1)


def _run(report):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('Clear Windows packaging test')
    with tempfile.TemporaryDirectory(prefix='clearwindows-smoke-') as folder:
        root = Path(folder)
        fixture = root / 'scan'
        fixture.mkdir()
        (fixture / 'bytes.bin').write_bytes(b'X' * 4096)
        window = Window(data_dir=root / 'state', auto_scan=False)
        window.show()
        app.processEvents()
        for index in range(len(SECTIONS)):
            window.navigation.setCurrentRow(index)
            app.processEvents()
            if window.pages.currentIndex() != index:
                raise RuntimeError('Navigation smoke test failed')
        result = scan(fixture)
        window.scan_result = result
        window.show_storage(result.root)
        app.processEvents()
        if result.root.size != 4096 or result.root.files != 1:
            raise RuntimeError('Real storage scan smoke test failed')
        if window.storage_table.table.rowCount() != 1:
            raise RuntimeError('Storage table smoke test failed')
        window.close()
        report.write_text(json.dumps({'ok': True, 'pages': len(SECTIONS), 'logical_bytes': result.root.size, 'files': result.root.files, 'system_changes': False}), encoding='utf-8')
