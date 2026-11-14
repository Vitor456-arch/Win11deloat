import os
import threading
import time

import pytest

from clearwindows.storage import Node, cleanup_selected, rectangles, scan, temp_preview


def test_real_hierarchy_totals_and_aggregation(tmp_path):
    (tmp_path / 'a').mkdir()
    (tmp_path / 'a' / 'one.bin').write_bytes(b'x' * 200)
    (tmp_path / 'two.bin').write_bytes(b'x' * 100)
    (tmp_path / 'three.bin').write_bytes(b'x' * 50)
    result = scan(tmp_path, retain=1)
    assert result.root.size == 350
    assert result.root.files == 3
    assert result.files == 3
    assert not result.cancelled and not result.errors
    assert any('smaller files' in n.path for n in result.root.children)
    assert next(n for n in result.root.children if n.directory).size == 200


def test_symlink_loop_and_escape_not_followed(tmp_path):
    if os.name == 'nt':
        pytest.skip('Symlink creation may require Windows developer mode')
    (tmp_path / 'data').write_bytes(b'123')
    (tmp_path / 'loop').symlink_to(tmp_path, target_is_directory=True)
    result = scan(tmp_path)
    assert result.root.size == 3 and result.skipped_links == 1
    with pytest.raises(ValueError, match='Symlink'):
        scan(tmp_path / 'loop')


def test_cancelled_is_explicit(tmp_path):
    stop = threading.Event()
    stop.set()
    result = scan(tmp_path, cancel=stop)
    assert result.cancelled and result.files == 0


def test_treemap_areas_proportional_and_no_overlap():
    blocks = rectangles([Node('a', size=75), Node('b', size=25), Node('zero')], 0, 0, 400, 100)
    assert len(blocks) == 2
    assert blocks[0][3] * blocks[0][4] == 30000
    assert blocks[1][3] * blocks[1][4] == 10000
    assert blocks[0][1] + blocks[0][3] == blocks[1][1]
    assert rectangles([], 0, 0, 10, 10) == []


def test_temp_preview_only_old_regular_files_no_deletion(tmp_path):
    old = tmp_path / 'old.tmp'
    old.write_bytes(b'old')
    t = time.time() - 10 * 86400
    os.utime(old, (t, t))
    fresh = tmp_path / 'fresh.tmp'
    fresh.write_text('fresh')
    files, errors = temp_preview(tmp_path)
    assert [f.path for f in files] == [str(old)]
    assert not errors
    assert old.read_bytes() == b'old'
    with pytest.raises(NotImplementedError):
        cleanup_selected(tmp_path, files, confirmed=True)
    assert old.exists()


def test_empty_and_zero_length_directory(tmp_path):
    assert scan(tmp_path).root.size == 0
    (tmp_path / 'empty').touch()
    result = scan(tmp_path)
    assert result.files == 1 and result.root.size == 0
