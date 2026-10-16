"""Create a bounded, immutable-by-convention snapshot of a selected file."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import stat
import tempfile

from .protocol import CHUNK_SIZE, MAX_FILE_SIZE, ProtocolError


@dataclass(frozen=True)
class PreparedOffer:
    transfer_id: str
    name: str
    size: int
    sha256: str
    staged_path: Path

    def metadata(self):
        return {key: getattr(self, key) for key in ('transfer_id', 'name', 'size', 'sha256')}


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def prepare_offer(source, work_dir, cancel):
    source, work_dir = Path(source), Path(work_dir)
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_SIZE:
        raise ValueError('Normal bir dosya seçin; boyut en fazla 1 GiB olabilir.')
    if cancel.is_set():
        raise ProtocolError(409, 'transfer_cancelled')
    if shutil.disk_usage(work_dir).free < before.st_size + 65536:
        raise OSError('Dosya kopyası için yeterli boş alan yok.')
    staged = None
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        with os.fdopen(os.open(source, flags), 'rb') as incoming:
            if _stamp(os.fstat(incoming.fileno())) != _stamp(before):
                raise ValueError('Kaynak dosya değişti.')
            fd, name = tempfile.mkstemp(prefix='offer-', dir=work_dir)
            staged = Path(name)
            digest, count = hashlib.sha256(), 0
            with os.fdopen(fd, 'wb') as outgoing:
                while True:
                    if cancel.is_set():
                        raise ProtocolError(409, 'transfer_cancelled')
                    chunk = incoming.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > before.st_size or count > MAX_FILE_SIZE:
                        raise ValueError('Kaynak dosya hazırlanırken değişti.')
                    outgoing.write(chunk)
                    digest.update(chunk)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            if (count != before.st_size or _stamp(os.fstat(incoming.fileno())) != _stamp(before)
                    or _stamp(source.lstat()) != _stamp(before)):
                raise ValueError('Kaynak dosya hazırlanırken değişti.')
        if cancel.is_set():
            raise ProtocolError(409, 'transfer_cancelled')
        return PreparedOffer(secrets.token_hex(16), source.name, count, digest.hexdigest(), staged)
    except BaseException:
        if staged is not None:
            staged.unlink(missing_ok=True)
        raise
