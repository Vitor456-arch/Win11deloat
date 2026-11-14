"""Qt desktop shell. Windows reads and writes run off the UI thread."""
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time

from PySide6.QtCore import QObject, QRunnable, QSettings, QStandardPaths, Qt, QThreadPool, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from .catalog import APPS, PRESETS, SETTINGS, recommended_apps
from .engine import Action, Executor, Journal
from .storage import rectangles, scan, size_text, temp_preview
from .windows import Windows


SECTIONS = ['Dashboard', 'Fresh Windows', 'Windows Debloater', 'System Optimization',
            'Memory and Processes', 'Storage Analyzer', 'System Cleanup', 'Startup Manager',
            'Application Manager', 'Services Manager', 'Privacy Settings', 'Gaming Optimization',
            'System Health', 'Backup and Restore', 'Optimization History', 'Settings']


class Signals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(str)
    done = Signal()


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn, self.signals = fn, Signals()

    def run(self):
        try:
            self.signals.result.emit(self.fn(self.signals.progress.emit))
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.done.emit()


class NumberItem(QTableWidgetItem):
    def __init__(self, label, number):
        super().__init__(label)
        self.number = number

    def __lt__(self, other):
        return self.number < other.number if isinstance(other, NumberItem) else super().__lt__(other)


class DataTable(QWidget):
    def __init__(self, headers):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search these results…')
        self.search.setAccessibleName('Filter table')
        layout.addWidget(self.search)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        layout.addWidget(self.table)
        self.search.textChanged.connect(self.filter)

    def rows(self, rows):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, (values, data) in enumerate(rows):
            for j, value in enumerate(values):
                if isinstance(value, tuple):
                    item = NumberItem(str(value[0]), value[1])
                else:
                    item = QTableWidgetItem(str(value) if value is not None else 'Unavailable')
                item.setData(Qt.ItemDataRole.UserRole, data)
                item.setToolTip(item.text())
                self.table.setItem(i, j, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        for j in range(self.table.columnCount()):
            self.table.setColumnWidth(j, min(420, max(100, self.table.columnWidth(j))))
        self.filter()

    def filter(self):
        query = self.search.text().casefold()
        for row in range(self.table.rowCount()):
            text = ' '.join(self.table.item(row, col).text() for col in range(self.table.columnCount()) if self.table.item(row, col))
            self.table.setRowHidden(row, query not in text.casefold())

    def selected(self):
        row = self.table.currentRow()
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 and self.table.item(row, 0) else None


class Treemap(QWidget):
    activated = Signal(object)

    def __init__(self):
        super().__init__()
        self.node, self.blocks = None, []
        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self.setAccessibleName('Storage treemap. Use the table to navigate with the keyboard.')

    def set_node(self, node):
        self.node = node
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        self.blocks = rectangles(self.node.children, 0, 0, self.width(), self.height()) if self.node else []
        colors = ['#384955', '#52665c', '#655e50', '#5c566b', '#4f6870', '#6c5659']
        for node, x, y, w, h in self.blocks:
            color = colors[sum(Path(node.path).suffix.encode()) % len(colors)]
            p.fillRect(int(x), int(y), max(0, int(w)-1), max(0, int(h)-1), QColor(color))
            if w > 75 and h > 42:
                p.save()
                p.setClipRect(int(x)+6, int(y)+4, max(0, int(w)-12), max(0, int(h)-8))
                p.setPen(QPen(QColor('#ffffff')))
                label = Path(node.path).name
                p.drawText(int(x)+8, int(y)+20, label)
                p.drawText(int(x)+8, int(y)+39, size_text(node.size))
                p.restore()

    def node_at(self, pos):
        return next((n for n, x, y, w, h in self.blocks if x <= pos.x() <= x+w and y <= pos.y() <= y+h), None)

    def mouseMoveEvent(self, event):
        node = self.node_at(event.position())
        self.setToolTip(f'{node.path}\n{size_text(node.size)} logical bytes\n{node.files:,} files' if node else '')

    def mouseDoubleClickEvent(self, event):
        node = self.node_at(event.position())
        if node and node.directory:
            self.activated.emit(node)


class Window(QMainWindow):
    def __init__(self, data_dir=None, backend=None, auto_scan=True):
        super().__init__()
        self.backend = backend or Windows()
        self.settings = QSettings('ClearWindows', 'ClearWindows')
        self.data_dir = Path(data_dir or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        self.journal = Journal(self.data_dir / 'history.sqlite3')
        self.executor = Executor(self.backend, self.journal)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.busy, self.current_job = False, None
        self.cancel = threading.Event()
        self.inventory, self.metrics, self.queue = {}, {}, []
        self.samples, self.previous_cpu = [], {}
        self.scan_result, self.storage_node = None, None
        self.setWindowTitle('Clear Windows')
        self.resize(1280, 850)
        self.setMinimumSize(920, 650)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        header = QHBoxLayout()
        brand = QLabel('CLEAR WINDOWS')
        brand.setObjectName('brand')
        header.addWidget(brand)
        header.addStretch()
        self.platform_label = QLabel('Windows analysis' if self.backend.supported else f'{platform.system()} · Windows controls unavailable')
        header.addWidget(self.platform_label)
        self.refresh_button = self.button('Scan Windows', self.refresh)
        self.refresh_button.setEnabled(self.backend.supported)
        header.addWidget(self.refresh_button)
        outer.addLayout(header)
        body = QHBoxLayout()
        self.navigation = QListWidget()
        self.navigation.setAccessibleName('Main navigation')
        self.navigation.addItems(SECTIONS)
        self.navigation.setFixedWidth(218)
        body.addWidget(self.navigation)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)
        bottom = QHBoxLayout()
        self.status = QLabel('Ready. Nothing is changed automatically.')
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        self.cancel_button = self.button('Cancel scan', self.cancel.set)
        self.cancel_button.hide()
        bottom.addWidget(self.cancel_button)
        self.queue_button = self.button('Review queue (0)', self.review_queue)
        bottom.addWidget(self.queue_button)
        outer.addLayout(bottom)
        self.build_pages()
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        self.apply_theme()
        self.theme_timer = QTimer(self)
        self.theme_timer.timeout.connect(self.follow_system_theme)
        self.theme_timer.start(10000)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        if auto_scan:
            self.timer.start(10000)
        self.refresh_history()
        if auto_scan and self.backend.supported:
            QTimer.singleShot(100, self.refresh)

    def button(self, label, fn):
        b = QPushButton(label)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(fn)
        return b

    def page(self, title, description):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 10, 12, 12)
        heading = QLabel(title)
        heading.setObjectName('heading')
        layout.addWidget(heading)
        text = QLabel(description)
        text.setWordWrap(True)
        text.setObjectName('muted')
        layout.addWidget(text)
        self.pages.addWidget(page)
        return layout

    def text(self, layout, content=''):
        widget = QTextEdit()
        widget.setReadOnly(True)
        widget.setPlainText(content)
        layout.addWidget(widget)
        return widget

    def native(self, layout, label, key):
        b = self.button(label, lambda: self.guard(lambda: self.backend.open_settings(key)))
        b.setEnabled(self.backend.supported)
        layout.addWidget(b)

    def build_pages(self):
        l = self.page('Your system, clearly.', 'Real measurements. Reviewed changes. No optimization score and no automatic modifications.')
        self.dashboard = self.text(l, 'Run Scan Windows to load system information.\n\nStorage Analyzer works on this platform. Windows-only information is never simulated.')
        row = QHBoxLayout()
        row.addWidget(self.button('Save measurement baseline', self.save_baseline))
        row.addWidget(self.button('Compare with baseline', self.compare_baseline))
        l.addLayout(row)

        l = self.page('Fresh Windows', 'Review optional apps actually installed for the current user. Presets filter suggestions; they never apply changes or select apps for removal.')
        self.preset = QComboBox()
        self.preset.addItems(PRESETS)
        self.preset.currentIndexChanged.connect(self.fill_apps)
        l.addWidget(self.preset)
        self.app_table = DataTable(['Optional application', 'Why review', 'Removal consequences', 'Recovery'])
        l.addWidget(self.app_table)
        l.addWidget(self.button('Queue selected application removal', self.queue_app))
        self.fresh_summary = QLabel('Scan Windows first. No application is selected for removal by default.')
        self.fresh_summary.setWordWrap(True)
        l.addWidget(self.fresh_summary)

        self.setting_tables = {}
        l = self.page('Windows Debloater', 'Only reviewed per-user preferences are offered. No security, Windows Update, driver, network, or recovery changes.')
        self.build_settings_table(l, 'Windows Debloater')
        self.native(l, 'Manage optional Windows experiences in Settings', 'privacy')

        l = self.page('System Optimization', 'Transparent Explorer preferences. More advanced tweaks remain outside this version until compatibility and recovery tests exist.')
        self.build_settings_table(l, 'System Optimization')

        l = self.page('Memory and Processes', 'Working set is not wasted memory. CPU is sampled; a new process needs two samples. No memory purging or automatic process killing.')
        self.memory_summary = QLabel('Waiting for Windows measurements. Disk activity, signature, owner, and leak detection are not implemented.')
        self.memory_summary.setWordWrap(True)
        l.addWidget(self.memory_summary)
        self.process_table = DataTable(['Process', 'PID', 'Working set', 'CPU % (sampled)', 'Executable'])
        l.addWidget(self.process_table)
        l.addWidget(self.button('End selected user process…', self.terminate))

        l = self.page('Storage Analyzer', 'Cancellable directory scan with proportional treemap. Sizes are logical bytes, not reclaimable space; hard links may be counted more than once. Links and junctions are skipped.')
        row = QHBoxLayout()
        row.addWidget(self.button('Choose folder and scan', self.choose_storage))
        row.addWidget(self.button('Up one level', self.storage_up))
        row.addWidget(self.button('Open selected location', self.open_location))
        row.addWidget(self.button('Export report', self.export_storage))
        l.addLayout(row)
        self.storage_label = QLabel('No folder scanned. Double-click a block or directory row to explore.')
        self.storage_label.setWordWrap(True)
        l.addWidget(self.storage_label)
        self.treemap = Treemap()
        self.treemap.activated.connect(self.show_storage)
        l.addWidget(self.treemap)
        self.storage_table = DataTable(['Name', 'Logical size', 'Files', 'Modified', 'Path'])
        self.storage_table.table.cellDoubleClicked.connect(lambda *_: self.enter_storage())
        l.addWidget(self.storage_table)
        legend = QLabel('Colors group file extensions; directories use slate. Only 200 largest files per directory are retained; smaller files are aggregated. No files are deleted here.')
        legend.setWordWrap(True)
        l.addWidget(legend)

        l = self.page('System Cleanup', 'Preview current-user temporary files older than 7 days. Nothing is deleted. Use Windows Storage Sense for native cleanup; caches and personal data are excluded.')
        l.addWidget(self.button('Analyze user temporary directory', self.preview_temp))
        self.temp_table = DataTable(['File', 'Logical size', 'Last modified', 'Path'])
        l.addWidget(self.temp_table)
        self.temp_summary = QLabel('No cleanup preview yet.')
        l.addWidget(self.temp_summary)
        self.native(l, 'Open Windows Storage Sense', 'storage')

        l = self.page('Startup Manager', 'Read-only inventory from Windows startup mechanisms. Startup impact is unavailable. Enable or disable entries in Windows Settings; custom startup mutation is not implemented.')
        self.startup_table = DataTable(['Name', 'Command', 'Location', 'User'])
        l.addWidget(self.startup_table)
        self.native(l, 'Manage startup apps in Windows Settings', 'startup')

        l = self.page('Application Manager', 'Current-user Store packages and registered desktop software. Use the Fresh Windows catalog for controlled removals, or Windows Settings for official uninstallers.')
        self.installed_table = DataTable(['Application', 'Version', 'Publisher', 'Type', 'Registered size'])
        l.addWidget(self.installed_table)
        self.native(l, 'Open installed apps / uninstall', 'apps')

        l = self.page('Services Manager', 'Read-only service inventory. Criticality is unknown; no service is treated as disposable. Service modification and dependency analysis remain unimplemented.')
        self.services_table = DataTable(['Service', 'Display name', 'State', 'Startup mode', 'Description', 'Executable'])
        l.addWidget(self.services_table)

        l = self.page('Privacy Settings', 'Per-user advertising preference with original-value backup. This does not eliminate Windows telemetry or network communication.')
        self.build_settings_table(l, 'Privacy Settings')
        self.native(l, 'Open Windows privacy and app permissions', 'privacy')

        l = self.page('Gaming Optimization', 'Use the supported Windows Game Mode preference. Compare actual resource measurements on Dashboard; FPS, gaming power profiles, and overlays are not implemented.')
        self.build_settings_table(l, 'Gaming Optimization')
        self.native(l, 'Open Windows gaming settings', 'gaming')

        l = self.page('System Health', 'Hardware and Windows inventory, optional features, scheduled tasks. Temperatures, SMART, GPU utilization, and automated repair are unavailable in this release.')
        self.health = self.text(l, 'Run Scan Windows to inspect real hardware information.')
        self.feature_table = DataTable(['Optional feature', 'Caption', 'Install state (1 enabled / 2 disabled / 3 absent / 4 unknown)'])
        l.addWidget(self.feature_table)
        self.task_table = DataTable(['Scheduled task', 'Path', 'State'])
        l.addWidget(self.task_table)

        l = self.page('Backup and Restore', 'Restore points are not complete backups and do not guarantee app or personal-file recovery. Registry backups are recorded durably before every write.')
        row = QHBoxLayout()
        row.addWidget(self.button('Inspect restore-point availability', self.inspect_restore))
        row.addWidget(self.button('Create and verify restore point', self.create_restore))
        l.addLayout(row)
        self.restore_text = self.text(l, 'System Protection must be checked per drive in the native dialog. Existing restore points and policy values do not prove protection is enabled.')
        self.native(l, 'Open System Protection', 'protection')
        self.native(l, 'Open Windows recovery', 'recovery')
        self.recovery_table = DataTable(['Backup ID', 'Time (UTC)', 'Action', 'State'])
        l.addWidget(self.recovery_table)
        l.addWidget(self.button('Restore selected original Registry value…', self.rollback))
        l.addWidget(self.button('Reconcile selected interrupted operation', self.reconcile))

        l = self.page('Optimization History', 'Append-only execution records include prepared backups, verified results, failures, and interrupted operations. Exported reports may contain local paths and installed software names.')
        l.addWidget(self.button('Export history as JSON', self.export_history))
        self.history_table = DataTable(['ID', 'Time (UTC)', 'Event', 'Details'])
        l.addWidget(self.history_table)

        l = self.page('Settings', 'The app runs as a normal user, never applies changes at startup, and installs no persistent service.')
        self.theme = QComboBox()
        self.theme.addItems(['System', 'Light', 'Dark'])
        self.theme.setCurrentText(self.settings.value('theme', 'System'))
        self.theme.currentTextChanged.connect(self.change_theme)
        l.addWidget(QLabel('Appearance'))
        l.addWidget(self.theme)
        self.text(l, f'Clear Windows 0.1.0\n\nData directory: {self.data_dir}\n\nWindows-only operations use built-in Windows PowerShell and documented Registry preferences. This Linux session supports storage analysis and UI development only.\n\nNo vendor scripts, automatic downloads, telemetry, fabricated measurements, or continuous background optimizer.\n\nDevelopment foundation: see README and docs/STATUS.md for tested capabilities and unfinished work.')

    def build_settings_table(self, layout, group):
        table = DataTable(['Preference', 'Current', 'Proposed', 'Benefit', 'Side effects', 'Safety / compatibility'])
        self.setting_tables[group] = table
        layout.addWidget(table)
        layout.addWidget(self.button('Inspect current values', lambda: self.load_settings(group)))
        layout.addWidget(self.button('Add selected preference to queue', lambda: self.queue_setting(group)))

    def guard(self, fn):
        try:
            return fn()
        except Exception as exc:
            self.error(str(exc))

    def error(self, message):
        self.status.setText('Operation failed. ' + message[:250])
        QMessageBox.warning(self, 'Operation not completed', message)

    def work(self, fn, done, *, cancelable=False):
        if self.busy:
            self.status.setText('Another operation is running. Wait for it to finish.')
            return
        self.busy = True
        self.cancel.clear()
        self.pages.setEnabled(False)
        self.navigation.setEnabled(False)
        self.queue_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.cancel_button.setVisible(cancelable)
        job = Job(fn)
        self.current_job = job
        job.signals.progress.connect(self.status.setText)
        job.signals.result.connect(lambda value: self.guard(lambda: done(value)))
        job.signals.error.connect(self.error)
        job.signals.done.connect(self.finished)
        self.status.setText('Working…')
        self.pool.start(job)

    def finished(self):
        self.busy = False
        self.current_job = None
        self.pages.setEnabled(True)
        self.navigation.setEnabled(True)
        self.queue_button.setEnabled(True)
        self.refresh_button.setEnabled(self.backend.supported)
        self.cancel_button.hide()
        self.refresh_history()

    def refresh(self):
        def load(progress):
            progress('Reading Windows inventory…')
            return self.backend.inventory(), self.backend.metrics()
        def done(result):
            self.inventory = result[0]
            self.fill_inventory()
            self.fill_metrics(result[1])
            self.status.setText('Windows scan completed. Review findings before queuing changes.')
        self.work(load, done)

    def poll(self):
        if self.backend.supported and not self.busy and self.navigation.currentRow() in (0, 4, 11, 12):
            self.work(lambda _: self.backend.metrics(), self.fill_metrics)

    def fill_inventory(self):
        d = self.inventory
        self.fill_apps()
        self.startup_table.rows([([p.get(k) for k in ('Name', 'Command', 'Location', 'User')], p) for p in d.get('Startup', [])])
        rows = [([p.get('Name'), p.get('Version'), p.get('Publisher'), 'Store / current user', 'Unavailable'], p) for p in d.get('Apps', [])]
        rows += [([p.get('DisplayName'), p.get('DisplayVersion'), p.get('Publisher'), 'Desktop', size_text(p['EstimatedSize']*1024) if p.get('EstimatedSize') else 'Unavailable'], p) for p in d.get('DesktopApps', [])]
        self.installed_table.rows(rows)
        self.services_table.rows([([p.get(k) for k in ('Name','DisplayName','State','StartMode','Description','PathName')], p) for p in d.get('Services', [])])
        self.feature_table.rows([([p.get(k) for k in ('Name','Caption','InstallState')], p) for p in d.get('Features', [])])
        self.task_table.rows([([p.get(k) for k in ('TaskName','TaskPath','State')], p) for p in d.get('Tasks', [])])
        self.health.setPlainText(json.dumps({k: d.get(k) for k in ('OS','Build','Version','Boot','CPU','GPU','Issues')}, indent=2))

    def fill_apps(self, *_):
        apps = recommended_apps(self.inventory.get('Apps', []), self.preset.currentIndex())
        self.app_table.rows([([APPS[p['Name']].label, APPS[p['Name']].reason, APPS[p['Name']].consequence, 'Reinstall through Store if available; app data not backed up'], p) for p in apps])
        self.fresh_summary.setText(f'{len(apps)} catalog matches among {len(self.inventory.get("Apps", []))} current-user packages. No RAM savings are estimated. Optional features, tasks, services, and startup items are inventoried in their own sections, not automatically disabled.')

    def fill_metrics(self, metrics):
        self.metrics = metrics
        total, available = metrics['Total'], metrics['Available']
        processes = metrics.get('Processes', [])
        t = time.monotonic()
        rows = []
        next_cpu = {}
        logical = os.cpu_count() or 1
        for p in processes:
            key = (p['Id'], p.get('StartTicks'))
            previous = self.previous_cpu.get(key)
            cpu = p.get('CpuSeconds')
            rate = None
            if cpu is not None and previous and t > previous[0]:
                rate = max(0, min(100, (cpu-previous[1]) / (t-previous[0]) / logical * 100))
            if cpu is not None:
                next_cpu[key] = (t, cpu)
            rows.append(([p['Name'], (p['Id'], p['Id']), (size_text(p['Memory']), p['Memory']), (f'{rate:.1f}%' if rate is not None else 'Sampling / unavailable', rate or 0), p.get('Path')], p))
        self.previous_cpu = next_cpu
        self.process_table.rows(rows)
        stamp = datetime.now().astimezone().isoformat(timespec='seconds')
        sample = {'time': stamp, 'memory_used': total-available, 'cpu_percent': metrics.get('Cpu'), 'processes': len(processes), 'startup_entries': len(self.inventory.get('Startup', [])), 'current_user_packages': len(self.inventory.get('Apps', []))}
        self.samples.append(sample)
        self.samples = self.samples[-120:]
        self.memory_summary.setText(f'Installed/visible: {size_text(total)} · Available: {size_text(available)} · In use: {size_text(total-available)} · Cache bytes: {size_text(metrics.get("Cache", 0))} · Committed: {size_text(metrics.get("Committed", 0))}. Cache may overlap other categories; values are not additive.')
        d = self.inventory
        recent = '\n'.join(f'{s["time"]}  RAM {size_text(s["memory_used"])}  CPU {s["cpu_percent"]}%  Processes {s["processes"]}' for s in self.samples[-8:])
        self.dashboard.setPlainText(f'{d.get("OS", "Windows")} · Build {d.get("Build", "not scanned")}\n\nCPU: {", ".join(p["Name"] for p in d.get("CPU", []))}\nGPU: {", ".join(p["Name"] for p in d.get("GPU", []))}\n\nMemory in use: {size_text(total-available)} / {size_text(total)}\nAvailable: {size_text(available)}\nCPU utilization: {metrics.get("Cpu", "Unavailable")}%\nProcesses: {len(processes)}\nStartup entries: {sample["startup_entries"]}\nCurrent-user Store packages: {sample["current_user_packages"]}\n\nRecent samples (not guaranteed idle):\n{recent}\n\nNo sensor temperatures, boot timings, disk I/O or FPS are fabricated.')
        self.status.setText('Real resource sample updated at ' + stamp)

    def queue_app(self):
        p = self.app_table.selected()
        if not p:
            return self.error('Select an optional application first.')
        self.add_action(Action('appx', p['Name'], p))

    def load_settings(self, group):
        def load(_):
            return [(s, self.backend.registry_read(s)) for s in SETTINGS.values() if s.group == group]
        def done(values):
            self.setting_tables[group].rows([([s.label, json.dumps(v), str(s.value) + ' (DWORD)', s.reason, s.side_effect, 'Low · current user · reversible · no admin · Windows 10/11; build behavior must be validated'], (s.id, v)) for s, v in values])
            self.status.setText('Current preferences read. No values changed.')
        self.work(load, done)

    def queue_setting(self, group):
        item = self.setting_tables[group].selected()
        if not item:
            return self.error('Inspect values, then select a preference.')
        key, before = item
        s = SETTINGS[key]
        if before == {'exists': True, 'value': s.value, 'type': 4}:
            return self.error('This preference already has the proposed value.')
        self.add_action(Action('registry', key, before))

    def add_action(self, action):
        if any(a.key == action.key for a in self.queue):
            return self.error('This action is already queued.')
        self.queue.append(action)
        self.queue_button.setText(f'Review queue ({len(self.queue)})')
        self.status.setText('Queued for review; nothing applied. ' + action.key)

    def review_queue(self):
        if not self.queue:
            return self.error('Queue is empty. Select actions in Fresh Windows or a preferences section.')
        dialog = QDialog(self)
        dialog.setWindowTitle('Optimization Queue · Safety review')
        dialog.resize(850, 650)
        layout = QVBoxLayout(dialog)
        warning = QLabel('Review every change. App removal may lose unsynced app data. Restore points are not complete backups. Registry values are backed up before writes. Execution stops on first failure; earlier successful changes remain applied.')
        warning.setWordWrap(True)
        layout.addWidget(warning)
        preview = QTextEdit()
        preview.setReadOnly(True)
        descriptions = []
        for a in self.queue:
            if a.kind == 'appx':
                r = APPS[a.target]
                descriptions.append(f'REMOVE {r.label}\nCurrent: {a.expected.get("PackageFullName")}\nProposed: absent for current user\nReason: {r.reason}\nSide effects: {r.consequence}\nRisk: Moderate. Reversal: Store reinstall only if available; app data not backed up.\nPermissions: current user; compatibility revalidated using installed package.\nRestart: not normally required; close the app first. Resource benefit: unmeasured.')
            else:
                s = SETTINGS[a.target]
                descriptions.append(f'{s.label}\nHKCU\\{s.path} → {s.name}\nCurrent: {json.dumps(a.expected)}\nProposed: DWORD {s.value}\nBenefit: {s.reason}\nSide effects: {s.side_effect}\nRisk: Low. Reversible from journal. No admin required.\nCompatibility: Windows 10/11; builds may ignore preference.\nRestart: reopen affected app/Explorer. Resource benefit: unmeasured.')
        preview.setPlainText('\n\n──────────────────────────────\n\n'.join(descriptions))
        layout.addWidget(preview)
        protection = self.button('Inspect / configure System Protection', lambda: self.guard(lambda: self.backend.open_settings('protection')))
        layout.addWidget(protection)
        restore = QCheckBox('Create and verify a restore point first (requires elevated launch and System Protection)')
        layout.addWidget(restore)
        confirm = QCheckBox('I reviewed all changes, understand the limitations, and explicitly authorize execution.')
        layout.addWidget(confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Reset)
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.setEnabled(False)
        confirm.toggled.connect(apply_button.setEnabled)
        apply_button.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        def clear():
            self.queue.clear()
            self.queue_button.setText('Review queue (0)')
            dialog.reject()
        buttons.button(QDialogButtonBox.StandardButton.Reset).setText('Clear queue')
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(clear)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        actions = list(self.queue)
        restore_requested = restore.isChecked()
        def execute(progress):
            return self.executor.execute(actions, confirmed=True, restore_requested=restore_requested,
                progress=lambda i, n, text: progress(f'Applying {i+1}/{n}: {text}'))
        def done(results):
            completed = {r['action'] for r in results if r['status'] == 'verified'}
            self.queue = [a for a in self.queue if a.key not in completed]
            self.queue_button.setText(f'Review queue ({len(self.queue)})')
            self.status.setText(f'{len(completed)} changes verified. Refresh Windows inventory before further decisions.')
            QMessageBox.information(self, 'Execution results', json.dumps(results, indent=2))
        self.work(execute, done)

    def choose_storage(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose a drive or directory')
        if folder:
            self.start_storage(folder)

    def start_storage(self, folder):
        def done(result):
            self.scan_result = result
            self.show_storage(result.root)
            state = 'CANCELLED · partial results' if result.cancelled else 'Scan complete'
            self.status.setText(f'{state}: {result.files:,} files, {result.skipped_links} links skipped, {len(result.errors)} errors (capped at 100).')
        self.work(lambda progress: scan(folder, self.cancel, lambda n, p: progress(f'{n:,} files · {p}')), done, cancelable=True)

    def show_storage(self, node):
        self.storage_node = node
        self.treemap.set_node(node)
        self.storage_label.setText(f'{node.path}\n{size_text(node.size)} logical size · {node.files:,} files · double-click folders to zoom')
        self.storage_table.rows([([Path(n.path).name, (size_text(n.size), n.size), (n.files, n.files), datetime.fromtimestamp(n.modified).isoformat(timespec='seconds') if n.modified else 'Aggregate', n.path], n) for n in node.children])

    def enter_storage(self):
        n = self.storage_table.selected()
        if n and n.directory:
            self.show_storage(n)

    def storage_up(self):
        if not self.scan_result or self.storage_node is self.scan_result.root:
            return
        target = str(Path(self.storage_node.path).parent)
        stack = [self.scan_result.root]
        while stack:
            n = stack.pop()
            if n.path == target:
                self.show_storage(n)
                return
            stack.extend(c for c in n.children if c.directory)

    def open_location(self):
        node = self.storage_table.selected()
        if not node or not Path(node.path).exists():
            return self.error('Select an existing file or folder; aggregate blocks are not real files.')
        path = Path(node.path) if node.directory else Path(node.path).parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def export_json(self, value, name):
        path, _ = QFileDialog.getSaveFileName(self, 'Export report', name, 'JSON (*.json)')
        if path:
            self.guard(lambda: Path(path).write_text(json.dumps(value, indent=2), encoding='utf-8'))

    def export_storage(self):
        if not self.scan_result:
            return self.error('Scan a folder first.')
        r = self.scan_result
        # Flat export avoids recursion limits on deeply nested directory trees.
        rows, stack = [], [r.root]
        while stack:
            n = stack.pop()
            rows.append({'path': n.path, 'logical_size': n.size, 'files': n.files, 'directory': n.directory, 'modified': n.modified})
            stack.extend(n.children)
        self.export_json({'cancelled': r.cancelled, 'errors': r.errors, 'skipped_links': r.skipped_links, 'retained_largest_files_per_directory': r.retained_limit, 'entries': rows}, 'storage-report.json')

    def preview_temp(self):
        if not self.backend.supported:
            return self.error('User-temp cleanup preview is restricted to Windows. Use Storage Analyzer for other platforms.')
        root = os.environ.get('TEMP')
        local = os.environ.get('LOCALAPPDATA')
        if not root or not local or Path(root).resolve() != (Path(local) / 'Temp').resolve():
            return self.error('Only the standard current-user LocalAppData/Temp directory is supported.')
        def done(result):
            files, errors = result
            self.temp_table.rows([([Path(f.path).name, (size_text(f.size), f.size), datetime.fromtimestamp(f.mtime_ns/1e9).isoformat(timespec='seconds'), f.path], asdict(f)) for f in files])
            self.temp_summary.setText(f'{len(files):,} files · {size_text(sum(f.size for f in files))} logical bytes · {len(errors)} errors. Preview only; actual reclaimed space not measured.')
            self.status.setText('Temporary file preview finished. No files deleted.')
        self.work(lambda _: temp_preview(root, self.cancel), done, cancelable=True)

    def terminate(self):
        p = self.process_table.selected()
        if not p:
            return self.error('Select a process first.')
        if QMessageBox.question(self, 'End user process?', f'{p["Name"]} · PID {p["Id"]}\n{p.get("Path")}\n\nUnsaved data may be lost. System and other-user processes are blocked. End this process?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        def run(_):
            session = 'process-' + str(time.time_ns())
            self.journal.add(session, 'termination_requested', p)
            try:
                result = self.backend.terminate(p['Id'], p.get('StartTicks'))
                self.journal.add(session, 'termination_verified', result)
                return result
            except Exception as exc:
                self.journal.add(session, 'termination_failed', {'error': str(exc)})
                raise
        self.work(run, lambda _: self.status.setText('Process exit verified. Refresh on next measurement.'))

    def inspect_restore(self):
        self.work(lambda _: self.backend.restore_status(), lambda value: self.restore_text.setPlainText(json.dumps(value, indent=2)))

    def create_restore(self):
        if QMessageBox.question(self, 'Create restore point?', 'Create and verify a Windows restore point? Administrator permissions and System Protection are required. This is not a complete backup.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        def create(_):
            session = 'restore-' + str(time.time_ns())
            try:
                result = self.backend.create_restore_point()
                self.journal.add(session, 'restore_point', result)
                return result
            except Exception as exc:
                self.journal.add(session, 'restore_failed', {'error': str(exc)})
                raise
        self.work(create, lambda value: self.restore_text.setPlainText('Verified new restore point:\n' + json.dumps(value, indent=2)))

    def refresh_history(self):
        events = self.journal.events()
        self.history_table.rows([([e['id'], e['time'], e['event'], json.dumps(e['payload'])], e) for e in events])
        rolled = {e['payload'].get('backup_id') for e in events if e['event'] == 'rolled_back'}
        unresolved = {e['id'] for e in self.journal.unresolved()}
        self.recovery_table.rows([([e['id'], e['time'], e['payload']['action']['kind'] + ':' + e['payload']['action']['target'], 'Interrupted / unknown' if e['id'] in unresolved else 'Restored' if e['id'] in rolled else 'Inspect history for outcome'], e) for e in events if e['event'] == 'prepared'])

    def rollback(self):
        e = self.recovery_table.selected()
        if not e:
            return self.error('Select a Registry backup first.')
        if QMessageBox.question(self, 'Restore original value?', 'Restore the exact original value (or its absence)? Recovery refuses to overwrite an externally changed preference.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.work(lambda _: self.executor.rollback(e['id'], confirmed=True), self.status.setText)

    def reconcile(self):
        e = self.recovery_table.selected()
        if not e:
            return self.error('Select an interrupted operation first.')
        self.work(lambda _: self.executor.reconcile(e['id']), self.status.setText)

    def export_history(self):
        self.export_json(self.journal.events(), 'clearwindows-history.json')

    def save_baseline(self):
        if not self.samples:
            return self.error('A real Windows resource sample is required first.')
        if QMessageBox.question(self, 'Save baseline?', 'Close optional applications and wait until CPU activity settles. This saves the latest observed sample, not a guaranteed idle average. Continue?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.guard(lambda: (self.data_dir / 'baseline.json').write_text(json.dumps(self.samples[-1]), encoding='utf-8'))
            self.status.setText('Baseline sample saved with timestamp. Compare under equivalent conditions.')

    def compare_baseline(self):
        if not self.samples:
            return self.error('Collect a Windows sample first.')
        def compare():
            before = json.loads((self.data_dir / 'baseline.json').read_text(encoding='utf-8'))
            after = self.samples[-1]
            text = f'Before: {before["time"]}\nAfter: {after["time"]}\n\n'
            for key in ('memory_used','cpu_percent','processes','startup_entries','current_user_packages'):
                a, b = before.get(key), after.get(key)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    text += f'{key}: {a:,} → {b:,} (delta {b-a:+,})\n'
            text += '\nObserved differences do not establish causation. Match workload and idle conditions. Re-scan inventory for fresh app/startup counts. No boot-time improvement is inferred.'
            QMessageBox.information(self, 'Measured comparison', text)
        self.guard(compare)

    def change_theme(self, theme):
        self.settings.setValue('theme', theme)
        self.apply_theme()

    def follow_system_theme(self):
        if self.settings.value('theme', 'System') == 'System':
            self.apply_theme()

    def apply_theme(self):
        theme = self.settings.value('theme', 'System')
        dark = theme == 'Dark'
        if theme == 'System':
            dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
            if sys.platform == 'win32':
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                        dark = winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
                except OSError:
                    pass
        bg, card, fg, muted, border, selected = ('#151719','#202326','#f0f1f2','#b3b9bf','#3b4147','#363d44') if dark else ('#f5f6f7','#ffffff','#20252a','#505b65','#cbd0d5','#e0e6eb')
        QApplication.instance().setStyleSheet(f'''
QWidget {{font-family: "Segoe UI", "DejaVu Sans"; font-size: 13px; color: {fg};}}
QMainWindow, QDialog {{background: {bg};}}
QLabel#brand {{font-size: 18px; font-weight: 700; padding: 14px; letter-spacing: 2px;}}
QLabel#heading {{font-size: 27px; font-weight: 600; margin-bottom: 8px;}}
QLabel#muted {{color: {muted}; margin-bottom: 12px;}}
QListWidget, QTextEdit, QTableWidget, QLineEdit, QComboBox {{background: {card}; border: 1px solid {border}; border-radius: 5px; selection-background-color: {selected}; selection-color: {fg};}}
QListWidget {{padding: 5px;}} QListWidget::item {{padding: 10px 7px; border-radius: 4px;}}
QListWidget::item:selected {{background: {selected}; color: {fg};}}
QTableWidget {{alternate-background-color: {bg}; gridline-color: {border};}}
QHeaderView::section {{background: {bg}; color: {muted}; padding: 8px; border: 0; border-bottom: 1px solid {border};}}
QPushButton {{background: {card}; border: 1px solid {border}; border-radius: 5px; padding: 8px 13px;}}
QPushButton:hover {{background: {selected};}} QPushButton:focus {{border: 2px solid {muted};}}
QPushButton:disabled {{color: {muted}; background: {bg};}}
QLineEdit, QComboBox {{padding: 7px;}}
QCheckBox {{padding: 8px;}}
QToolTip {{background: {card}; color: {fg}; border: 1px solid {border};}}
''')

    def closeEvent(self, event):
        if self.busy:
            self.cancel.set()
            self.status.setText('Waiting for current operation to finish safely. Close again when it completes.')
            event.ignore()
        else:
            self.timer.stop()
            event.accept()


def main():
    if '--smoke-test' in sys.argv:
        from .smoke import run
        run()
        return
    app = QApplication(sys.argv)
    app.setApplicationName('Clear Windows')
    app.setOrganizationName('ClearWindows')
    app.setStyle('Fusion')
    window = Window()
    window.show()
    sys.exit(app.exec())
