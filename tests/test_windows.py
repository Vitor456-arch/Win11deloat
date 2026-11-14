import sys
import pytest
from clearwindows.windows import Windows, PlatformUnavailable


def test_non_windows_fails_explicitly():
    if sys.platform == 'win32':
        pytest.skip('Only non-Windows guard')
    b = Windows()
    for fn in (b.inventory, b.metrics, b.restore_status):
        with pytest.raises(PlatformUnavailable):
            fn()


@pytest.mark.skipif(sys.platform != 'win32', reason='Requires Windows; read-only integration')
def test_windows_real_inventory_and_metrics():
    b = Windows()
    inventory = b.inventory()
    assert int(inventory['Build']) > 0
    assert isinstance(inventory['Apps'], list)
    assert isinstance(inventory['Startup'], list)
    metrics = b.metrics()
    assert metrics['Total'] > 0
    assert 0 <= metrics['Available'] <= metrics['Total']
    assert len(metrics['Processes']) > 0
