import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from clearwindows.app import SECTIONS, Window


class Unsupported:
    supported = False


def test_all_pages_theme_and_async_real_storage(tmp_path):
    app = QApplication.instance() or QApplication([])
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / 'settings'))
    window = Window(data_dir=tmp_path / 'state', backend=Unsupported())
    window.show()
    assert window.pages.count() == len(SECTIONS) == 16
    for i in range(16):
        window.navigation.setCurrentRow(i)
        app.processEvents()
        assert window.pages.currentIndex() == i
    for theme in ('Light', 'Dark', 'System'):
        window.theme.setCurrentText(theme)
        app.processEvents()
    folder = tmp_path / 'scan'
    folder.mkdir()
    (folder / 'real.bin').write_bytes(b'x' * 4096)
    window.navigation.setCurrentRow(5)
    window.start_storage(str(folder))
    loop = QEventLoop()
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(loop.quit)
    watchdog.start(10000)
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if not window.busy else None)
    poll.start(10)
    loop.exec()
    poll.stop()
    assert not window.busy
    assert window.scan_result.root.size == 4096
    assert window.storage_table.table.rowCount() == 1
    window.storage_table.search.setText('nonexistent')
    assert window.storage_table.table.isRowHidden(0)
    window.pool.waitForDone(2000)
    window.close()
    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTimer.singleShot(0, app.quit)
    app.exec()
