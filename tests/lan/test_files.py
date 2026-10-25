import hashlib
from pathlib import Path
from threading import Event

import pytest


def implementation():
    import lan_transfer
    assert (Path(lan_transfer.__file__).parent / 'files.py').exists(), 'File staging not implemented'
    from lan_transfer.files import prepare_offer
    return prepare_offer


@pytest.mark.parametrize('size', [0, 10 * 1024 * 1024])
def test_prepare_offer_snapshot(tmp_path, size):
    source = tmp_path / 'source'; work = tmp_path / 'work'; work.mkdir()
    with source.open('wb') as f:
        for _ in range(size // 1024): f.write(b'x' * 1024)
    offer = implementation()(source, work, Event())
    assert offer.size == size
    digest = hashlib.sha256()
    with source.open('rb') as f:
        for chunk in iter(lambda: f.read(131072), b''): digest.update(chunk)
    assert offer.sha256 == digest.hexdigest()
    source.write_bytes(b'changed after staging')
    assert offer.staged_path.stat().st_size == size
    assert offer.name == 'source'


def test_over_limit_source_leaves_no_staging(tmp_path):
    source = tmp_path / 'large'; work = tmp_path / 'work'; work.mkdir()
    with source.open('wb') as f: f.truncate(1024**3 + 1)
    with pytest.raises(ValueError): implementation()(source, work, Event())
    assert not list(work.iterdir())


def test_cancel_and_symlink_leave_no_staging(tmp_path):
    source = tmp_path / 'source'; source.write_bytes(b'keep')
    work = tmp_path / 'work'; work.mkdir()
    cancel = Event(); cancel.set()
    with pytest.raises(Exception): implementation()(source, work, cancel)
    assert not list(work.iterdir())
    link = tmp_path / 'link'; link.symlink_to(source)
    with pytest.raises(ValueError): implementation()(link, work, Event())


def test_windows_stamp_uses_birthtime_for_stat_fstat_consistency(monkeypatch):
    from lan_transfer import files
    from types import SimpleNamespace
    monkeypatch.setattr(files, 'os', SimpleNamespace(name='nt'))
    before = SimpleNamespace(st_dev=1, st_ino=2, st_size=10, st_mtime_ns=100,
                             st_ctime_ns=99, st_birthtime_ns=50)
    opened = SimpleNamespace(**(vars(before) | {'st_ctime_ns': 100}))
    assert files._stamp(before) == files._stamp(opened)
    changed = SimpleNamespace(**(vars(opened) | {'st_mtime_ns': 101}))
    assert files._stamp(before) != files._stamp(changed)


def test_changed_source_during_copy_is_rejected(tmp_path, monkeypatch):
    prepare = implementation()
    from lan_transfer import files
    source = tmp_path / 'source'; source.write_bytes(b'x' * 262144)
    work = tmp_path / 'work'; work.mkdir()
    original = files.os.fstat
    calls = 0
    def change_after_copy(fd):
        nonlocal calls
        calls += 1
        if calls == 2: source.write_bytes(b'changed')
        return original(fd)
    monkeypatch.setattr(files.os, 'fstat', change_after_copy)
    with pytest.raises(ValueError): prepare(source, work, Event())
    assert not list(work.iterdir())


def test_no_disk_space_and_unreadable_source(tmp_path, monkeypatch):
    prepare = implementation()
    from lan_transfer import files
    from types import SimpleNamespace
    source = tmp_path / 'source'; source.write_bytes(b'keep')
    work = tmp_path / 'work'; work.mkdir()
    monkeypatch.setattr(files.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    with pytest.raises(OSError): prepare(source, work, Event())
    with pytest.raises(OSError): prepare(tmp_path / 'missing', work, Event())
    assert source.read_bytes() == b'keep'
    assert not list(work.iterdir())
