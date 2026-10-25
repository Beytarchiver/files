"""UI-independent archive helpers shared by desktop and Flet applications."""
import gzip
import ntpath
import os
from pathlib import Path
import stat
import tarfile
import tempfile

import pyzipper

CHUNK_SIZE = 64 * 1024
MAX_EXTRACT_SIZE = 2 * 1024**3
MAX_FILES = 10000
MAX_COMPRESSION_RATIO = 100


class SecurityError(ValueError):
    """An archive exceeds resource limits or contains unsafe entries."""


def format_size(bytes_val):
    if not bytes_val:
        return '0 B'
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if bytes_val < 1024:
            return f'{bytes_val:.2f} {unit}'
        bytes_val /= 1024
    return f'{bytes_val:.2f} PB'


def unique_arcname(arc, used):
    base, ext = os.path.splitext(arc)
    candidate, number = arc, 1
    folded = {name.casefold() for name in used}
    while candidate.casefold() in folded:
        candidate = f'{base} ({number}){ext}'
        number += 1
    used.add(candidate)
    return candidate


class _ArchiveIndex:
    def __init__(self, max_total_size, max_files):
        if max_total_size < 0 or max_files < 1:
            raise ValueError('Geçersiz çıkartma sınırları.')
        self.max_total_size, self.max_files = max_total_size, max_files
        self.seen, self.count, self.declared = {}, 0, 0

    def add(self, name, size, is_dir):
        self.count += 1
        self.declared += size
        if self.count > self.max_files or size < 0 or self.declared > self.max_total_size:
            raise SecurityError('Arşiv dosya sayısı veya açılmış boyut sınırını aşıyor.')
        normalized = name.replace('\\', '/')
        parts = normalized.split('/')
        if (not normalized or normalized.startswith('/') or ntpath.splitdrive(name)[0]
                or '..' in parts or any(ord(c) < 32 for c in name)):
            raise SecurityError(f'Güvensiz arşiv yolu: {name!r}')
        parts = [part for part in parts if part not in ('', '.')]
        reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
        reserved.update(f'{prefix}{i}' for prefix in ('COM', 'LPT') for i in range(1, 10))
        for part in parts:
            if (part.endswith((' ', '.')) or any(c in part for c in ':<>"|?*')
                    or part.split('.')[0].upper() in reserved):
                raise SecurityError(f'Güvensiz dosya adı: {name!r}')
        if not parts:
            if is_dir:
                return ()
            raise SecurityError('Boş dosya adı.')
        key = '/'.join(parts).casefold()
        if key in self.seen:
            raise SecurityError(f'Çakışan arşiv yolu: {name!r}')
        for i in range(1, len(parts)):
            if self.seen.get('/'.join(parts[:i]).casefold()) is False:
                raise SecurityError('Dosya ve klasör yolları çakışıyor.')
        if not is_dir and any(k.startswith(key + '/') for k in self.seen):
            raise SecurityError('Dosya ve klasör yolları çakışıyor.')
        self.seen[key] = is_dir
        return parts


def _zip_entries(archive, max_total_size, max_files):
    index = _ArchiveIndex(max_total_size, max_files)
    entries = []
    for info in archive.infolist():
        kind = stat.S_IFMT(info.external_attr >> 16)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise SecurityError('Arşivde bağlantı veya özel dosya var.')
        parts = index.add(info.filename, info.file_size, info.is_dir())
        if info.file_size > 50 * 1024**2:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > MAX_COMPRESSION_RATIO:
                raise SecurityError('Arşiv aşırı sıkıştırma oranı içeriyor.')
        entries.append((info, parts))
    return entries, index.declared


def inspect_zip(zip_path, *, max_total_size=MAX_EXTRACT_SIZE, max_files=MAX_FILES):
    """Validate metadata and paths without decompressing or claiming CRC validation."""
    with pyzipper.AESZipFile(zip_path, 'r') as archive:
        entries, total = _zip_entries(archive, max_total_size, max_files)
        items = [{'name': info.filename, 'size': info.file_size,
                  'compressed': info.compress_size, 'is_dir': info.is_dir()}
                 for info, _ in entries]
    return items, total


def safe_extract_archive(archive_path, output_dir, password='', *,
                         max_total_size=MAX_EXTRACT_SIZE, max_files=MAX_FILES,
                         progress=None, cancel_event=None):
    """Stage regular files, verify streams, then publish a new destination."""
    archive_path, output_dir = Path(archive_path), Path(output_dir)
    if os.path.lexists(output_dir):
        raise FileExistsError('Hedef zaten var; farklı veya boşta bir hedef seçin.')
    index = _ArchiveIndex(max_total_size, max_files)
    actual = 0

    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError('İşlem kullanıcı tarafından iptal edildi.')

    check_cancel()
    with tempfile.TemporaryDirectory(prefix='.beyt-extract-', dir=output_dir.parent) as temp:
        stage = Path(temp) / 'content'
        stage.mkdir()

        def target(name, size, is_dir):
            return stage.joinpath(*index.add(name, size, is_dir))

        def copy_stream(source, destination, total, name):
            nonlocal actual
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as sink:
                while True:
                    check_cancel()
                    chunk = source.read(min(CHUNK_SIZE, max_total_size - actual + 1))
                    if not chunk:
                        break
                    actual += len(chunk)
                    if actual > max_total_size:
                        raise SecurityError('Açılmış veri boyut sınırını aşıyor.')
                    sink.write(chunk)
                    if progress:
                        progress(actual, total, name)

        ext = archive_path.suffix.lower()
        if ext in ('.zip', '.beyt'):
            with pyzipper.AESZipFile(archive_path, 'r') as archive:
                if password:
                    archive.setpassword(password.encode('utf-8'))
                entries, total = _zip_entries(archive, max_total_size, max_files)
                for info, parts in entries:
                    check_cancel()
                    dest = stage.joinpath(*parts)
                    if info.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        with archive.open(info) as source:
                            copy_stream(source, dest, total, info.filename)
        elif ext == '.7z':
            import py7zr  # Mobile ZIP operations do not require the desktop 7z dependency.
            with py7zr.SevenZipFile(archive_path, 'r', password=password or None,
                                   max_extract_size=max_total_size) as archive:
                for info in archive.list():
                    check_cancel()
                    if info.is_symlink or not (info.is_file or info.is_directory):
                        raise SecurityError('Arşivde bağlantı veya özel dosya var.')
                    target(info.filename, info.uncompressed, info.is_directory)
                archive.extractall(path=stage)
        elif ext in ('.tar', '.gz', '.tgz'):
            try:
                archive = tarfile.open(archive_path, 'r:*')
            except tarfile.ReadError:
                if ext != '.gz':
                    raise
                dest = target(archive_path.stem, 0, False)
                with gzip.open(archive_path, 'rb') as source:
                    copy_stream(source, dest, 0, archive_path.stem)
            else:
                with archive:
                    entries = []
                    for info in archive:
                        check_cancel()
                        if not (info.isfile() or info.isdir()):
                            raise SecurityError('Arşivde bağlantı veya özel dosya var.')
                        entries.append((info, target(info.name, info.size, info.isdir())))
                    for info, dest in entries:
                        check_cancel()
                        if info.isdir():
                            dest.mkdir(parents=True, exist_ok=True)
                        else:
                            with archive.extractfile(info) as source:
                                copy_stream(source, dest, index.declared, info.name)
        else:
            raise ValueError('Desteklenmeyen arşiv biçimi.')
        check_cancel()
        if os.path.lexists(output_dir):
            raise FileExistsError('Hedef işlem sırasında oluşturuldu; üzerine yazılmadı.')
        stage.rename(output_dir)
    return output_dir
