"""Exercise the same CLI used by Windows portable/installed package smoke tests."""
import json
import os
import subprocess
import sys


def test_packaged_smoke_entrypoint_uses_real_files_without_system_changes(tmp_path):
    report = tmp_path / 'smoke.json'
    result = subprocess.run([sys.executable, '-m', 'clearwindows', '--smoke-test', str(report)],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=30)
    detail = report.read_text(encoding='utf-8') if report.exists() else 'No smoke report'
    assert result.returncode == 0, result.stdout + result.stderr + detail
    data = json.loads(report.read_text())
    assert data == {'ok': True, 'pages': 16, 'logical_bytes': 4096, 'files': 1, 'system_changes': False}


def test_license_bundle_preserves_qt_texts_and_exact_versions(tmp_path):
    from pathlib import Path
    from importlib import metadata
    script = Path(__file__).resolve().parents[1] / 'packaging' / 'collect_notices.py'
    result = subprocess.run([sys.executable, str(script), str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / 'third-party-licenses'
    for name in ('PySide6-Essentials', 'shiboken6'):
        assert (root / name / 'LGPL-3.0-only.txt').is_file()
        assert (root / name / 'GPL-3.0-only.txt').is_file()
        assert 'License' in (root / name / 'PACKAGE-METADATA.txt').read_text(encoding='utf-8')
        assert metadata.version(name) in (root / 'VERSIONS.txt').read_text()
