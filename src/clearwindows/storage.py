"""Portable, cancellable streaming scanner. Never follows symlinks/reparse points."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
import threading
import time


def size_text(size):
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if abs(size) < 1024 or unit == 'TiB':
            return f'{size:,.1f} {unit}'
        size /= 1024


def reparse(st):
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & 0x400)


def safe_root(path):
    p = Path(os.path.abspath(path))
    for part in (p, *p.parents):
        if reparse(part.lstat()):
            raise ValueError('Symlink/junction roots and ancestors are not scanned')
    if not p.is_dir():
        raise ValueError('Choose a directory')
    return p


@dataclass
class Node:
    path: str
    size: int = 0
    allocated: int = 0
    modified: float = 0
    files: int = 0
    children: list = field(default_factory=list)
    directory: bool = False


@dataclass
class Scan:
    root: Node
    errors: list = field(default_factory=list)
    skipped_links: int = 0
    cancelled: bool = False
    files: int = 0
    # One tree node per directory and only the largest file nodes per directory.
    # Totals remain exact; omitted files are represented by an aggregate block.
    retained_limit: int = 200


def scan(path, cancel=None, progress=None, retain=200):
    import heapq
    cancel = cancel or threading.Event()
    root_path = safe_root(path)
    result = Scan(Node(str(root_path), directory=True), retained_limit=retain)
    stack = [(result.root, False)]
    last = 0
    while stack:
        if cancel.is_set():
            result.cancelled = True
            break
        node, visited = stack.pop()
        if visited:
            for child in node.children:
                node.size += child.size
                node.allocated += child.allocated
                node.files += child.files
            continue
        dirs, largest, omitted_size, omitted_alloc, omitted_count = [], [], 0, 0, 0
        try:
            # Check again before opening the directory (best effort for read-only scans).
            if reparse(os.lstat(node.path)):
                result.skipped_links += 1
                continue
            with os.scandir(node.path) as entries:
                for entry in entries:
                    if cancel.is_set():
                        break
                    try:
                        st = entry.stat(follow_symlinks=False)
                        if reparse(st):
                            result.skipped_links += 1
                            continue
                        child = Node(entry.path, modified=st.st_mtime)
                        if stat.S_ISDIR(st.st_mode):
                            child.directory = True
                            dirs.append(child)
                        elif stat.S_ISREG(st.st_mode):
                            child.size, child.files = st.st_size, 1
                            child.allocated = getattr(st, 'st_blocks', 0) * 512
                            result.files += 1
                            heapq.heappush(largest, (child.size, entry.path, child))
                            if len(largest) > retain:
                                _, _, dropped = heapq.heappop(largest)
                                omitted_size += dropped.size
                                omitted_alloc += dropped.allocated
                                omitted_count += 1
                    except OSError as exc:
                        if len(result.errors) < 100:
                            result.errors.append(f'{entry.path}: {exc}')
                    if progress and time.monotonic() - last > .2:
                        progress(result.files, entry.path)
                        last = time.monotonic()
        except OSError as exc:
            if len(result.errors) < 100:
                result.errors.append(f'{node.path}: {exc}')
        node.children = dirs + [x[2] for x in sorted(largest, reverse=True)]
        if omitted_count:
            node.children.append(Node(f'{node.path}{os.sep}[{omitted_count} smaller files]', omitted_size, omitted_alloc, files=omitted_count))
        stack.append((node, True))
        stack.extend((d, False) for d in dirs)
    # If cancelled, compute coherent partial totals without presenting them as complete.
    if result.cancelled:
        def total(n):
            for c in n.children:
                if c.directory:
                    total(c)
            if n.directory:
                n.size = sum(c.size for c in n.children)
                n.files = sum(c.files for c in n.children)
        total(result.root)
    return result


def rectangles(nodes, x, y, width, height):
    """Slice-and-dice layout with exact proportional areas and no overlap."""
    nodes = sorted((n for n in nodes if n.size > 0), key=lambda n: n.size, reverse=True)
    total = sum(n.size for n in nodes)
    if not total or width <= 0 or height <= 0:
        return []
    result = []
    horizontal = width >= height
    offset = 0.
    for n in nodes:
        fraction = n.size / total
        if horizontal:
            w = width * fraction
            result.append((n, x + offset, y, w, height))
            offset += w
        else:
            h = height * fraction
            result.append((n, x, y + offset, width, h))
            offset += h
    return result


@dataclass(frozen=True)
class TempFile:
    path: str
    size: int
    mtime_ns: int
    device: int
    inode: int


def temp_preview(root, cancel=None, age_days=7):
    root = safe_root(root)
    if root == Path(root.anchor) or root == Path.home():
        raise ValueError('Temp root must be a dedicated temporary directory')
    cutoff = time.time() - age_days * 86400
    files, errors = [], []
    stack = [root]
    while stack:
        if cancel and cancel.is_set():
            break
        folder = stack.pop()
        try:
            if reparse(folder.lstat()):
                continue
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        # Windows DirEntry.stat caches st_ino/st_dev/st_nlink as zero.
                        # Query the path explicitly for usable file identity / link count.
                        st = os.stat(entry.path, follow_symlinks=False)
                        if reparse(st):
                            continue
                        if stat.S_ISDIR(st.st_mode):
                            stack.append(Path(entry.path))
                        elif stat.S_ISREG(st.st_mode) and st.st_mtime < cutoff and st.st_nlink == 1:
                            files.append(TempFile(entry.path, st.st_size, st.st_mtime_ns, st.st_dev, st.st_ino))
                    except OSError as exc:
                        errors.append(str(exc))
        except OSError as exc:
            errors.append(str(exc))
    return files, errors


def cleanup_selected(root, selected, *, confirmed=False):
    """Disabled until Windows handle-based, race-resistant deletion is validated.

    A preview followed by Path.unlink is insufficient: parent directories can be
    replaced with junctions after validation. Use Windows Storage Sense instead.
    """
    raise NotImplementedError('Direct deletion is not enabled. Use the reviewed preview and Windows Storage Sense for cleanup.')
