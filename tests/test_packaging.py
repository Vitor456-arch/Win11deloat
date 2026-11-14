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
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(report.read_text())
    assert data == {'ok': True, 'pages': 16, 'logical_bytes': 4096, 'files': 1, 'system_changes': False}
