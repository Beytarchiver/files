"""Private per-session staging with conservative cleanup after a crashed process."""
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

import psutil


def _stale(directory):
    """Only our recognized files, owned by a process that no longer exists."""
    try:
        marker = directory / 'owner.json'
        info = marker.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024:
            return False
        owner = json.loads(marker.read_text(encoding='utf-8'))
        pid, created = owner['pid'], owner['created']
        if (owner.get('schema') != 1 or type(pid) is not int or pid < 1
                or type(created) not in (int, float) or not math.isfinite(created) or created <= 0):
            return False
        try:
            if psutil.Process(pid).create_time() == created:
                return False
        except psutil.NoSuchProcess:
            pass
        for entry in directory.iterdir():
            if not stat.S_ISREG(entry.lstat().st_mode):
                return False
            if entry.name not in ('owner.json', 'server.pem', 'server-key.pem') and not re.fullmatch(r'offer-[A-Za-z0-9_-]+', entry.name):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, psutil.AccessDenied):
        return False


def create_work_dir(base=None):
    suffix = str(os.getuid()) if hasattr(os, 'getuid') else 'user'
    root = Path(base) if base is not None else Path(tempfile.gettempdir()) / f'beytarchiver-lan-{suffix}'
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or (hasattr(os, 'getuid') and info.st_uid != os.getuid()):
        raise ValueError('Geçici aktarım dizini güvenli değil.')
    if os.name != 'nt':
        root.chmod(0o700)
    for directory in root.iterdir():
        if directory.name.startswith('session-') and stat.S_ISDIR(directory.lstat().st_mode) and _stale(directory):
            try: shutil.rmtree(directory)
            except FileNotFoundError: pass  # Another instance may have cleaned it.
    directory = Path(tempfile.mkdtemp(prefix='session-', dir=root))
    owner = {'schema': 1, 'pid': os.getpid(), 'created': psutil.Process().create_time()}
    try:
        fd = os.open(directory / 'owner.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(owner, stream)
    except BaseException:
        shutil.rmtree(directory)
        raise
    return directory
