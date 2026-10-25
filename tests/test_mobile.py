"""Real archive operations and Flet control construction, without a desktop client."""
import asyncio
from pathlib import Path
import sys
import threading
from unittest.mock import AsyncMock
import zipfile

import pytest

# Support direct execution from an editor as well as pytest.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if __name__ == '__main__':
    raise SystemExit(pytest.main([str(Path(__file__).resolve()), *sys.argv[1:]]))

from mobile import main as mobile
import beyt_core as core


def callbacks():
    progress, status = [], []
    return progress, status, lambda *args: progress.append(args), lambda *args: status.append(args)


def test_create_refuses_existing_output(tmp_path):
    source = tmp_path / 'hello.txt'
    source.write_text('hello')
    output = tmp_path / 'existing.zip'
    output.write_bytes(b'keep this')
    engine = mobile.BeytarchiverMobileEngine()
    progress, status, p, s = callbacks()
    engine.create_zip_from_files([str(source)], str(output), '', p, s)
    assert output.read_bytes() == b'keep this'
    assert progress[-1][0] == 0
    assert not engine.is_running


@pytest.mark.parametrize('password', ['', 'secret'])
def test_mobile_create_inspect_extract_round_trip(tmp_path, password):
    source = tmp_path / 'hello.txt'
    source.write_bytes(b'hello' * 20000)
    output = tmp_path / 'archive.zip'
    engine = mobile.BeytarchiverMobileEngine()
    progress, status, p, s = callbacks()
    engine.create_zip_from_files([str(source)], str(output), password, p, s)
    assert progress[-1][0] == 1, status
    items, total = core.inspect_zip(output)
    assert items[0]['name'] == source.name and total == source.stat().st_size
    engine.extract_verified_zip(str(output), str(tmp_path / 'out'), password, p, s)
    assert progress[-1][0] == 1, status
    assert (tmp_path / 'out' / source.name).read_bytes() == source.read_bytes()


def test_write_probe_does_not_overwrite_user_file(tmp_path):
    sentinel = tmp_path / '.beyt_write_test'
    sentinel.write_bytes(b'user data')
    assert mobile.is_directory_writable(str(tmp_path))
    assert sentinel.read_bytes() == b'user data'


def test_wrong_password_does_not_publish_target(tmp_path):
    source = tmp_path / 'data'
    source.write_text('data')
    engine = mobile.BeytarchiverMobileEngine()
    _, status, p, s = callbacks()
    engine.create_zip_from_files([str(source)], str(tmp_path / 'archive.zip'), 'secret', p, s)
    engine.extract_verified_zip(str(tmp_path / 'archive.zip'), str(tmp_path / 'out'), 'wrong', p, s)
    assert not (tmp_path / 'out').exists()
    assert not list(tmp_path.glob('.beyt-extract-*'))


def test_cancel_creation_removes_only_its_own_output(tmp_path):
    source = tmp_path / 'data'
    source.write_bytes(b'x' * 200000)
    output = tmp_path / 'new.zip'
    sentinel = tmp_path / 'keep.zip'
    sentinel.write_bytes(b'keep')
    engine = mobile.BeytarchiverMobileEngine()
    progress, status, p, s = callbacks()
    def cancel_on_progress(*args):
        p(*args)
        engine.cancel_event.set()
    engine.create_zip_from_files([str(source)], str(output), '', cancel_on_progress, s)
    assert not output.exists() and source.stat().st_size == 200000
    assert sentinel.read_bytes() == b'keep'
    assert progress[-1][0] == 0 and not engine.is_running


def test_missing_source_preserves_existing_archive(tmp_path):
    engine = mobile.BeytarchiverMobileEngine()
    output = tmp_path / 'old.zip'
    output.write_bytes(b'keep')
    _, _, p, s = callbacks()
    engine.create_zip_from_files([str(tmp_path / 'missing')], str(output), '', p, s)
    assert output.read_bytes() == b'keep'


def test_inspect_honors_size_and_entry_limits(tmp_path):
    archive = tmp_path / 'archive.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr('one', b'1234')
        zf.writestr('two', b'1234')
    for limits in ({'max_files': 1}, {'max_total_size': 7}):
        with pytest.raises(core.SecurityError):
            core.inspect_zip(archive, **limits)


def test_unique_names_handle_case_collisions():
    used = {'Photo.JPG'}
    assert core.unique_arcname('photo.jpg', used) == 'photo (1).jpg'


@pytest.mark.parametrize('name', ['../escape', '/absolute', r'a\..\escape', 'C:/drive',
                                  'NUL.txt', 'a:b', 'trailing.', 'a/../b'])
def test_inspect_rejects_unsafe_names(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr(name, 'data')
    with pytest.raises(core.SecurityError):
        core.inspect_zip(archive)


@pytest.mark.parametrize('names', [('a', 'A'), ('a', 'a/b'), ('a/b', 'a')])
def test_inspect_rejects_collisions(tmp_path, names):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        for name in names:
            zf.writestr(name, 'data')
    with pytest.raises(core.SecurityError):
        core.inspect_zip(archive)


def test_cancel_extract_leaves_no_target_and_reports_progress(tmp_path):
    archive = tmp_path / 'archive.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr('data', b'a' * (1024 * 256))
    cancel = threading.Event()
    reported = []
    def progress(done, total, name):
        reported.append((done, total, name))
        cancel.set()
    with pytest.raises(InterruptedError):
        core.safe_extract_archive(archive, tmp_path / 'out', progress=progress, cancel_event=cancel)
    assert reported and not (tmp_path / 'out').exists()
    assert not list(tmp_path.glob('.beyt-extract-*'))


class FakePage:
    def __init__(self):
        self.services, self.controls = [], []
        self.update_threads = []
        from types import SimpleNamespace
        self._services = SimpleNamespace(register_service=self.services.append)
    def update(self):
        self.update_threads.append(threading.get_ident())
    def add(self, *controls):
        self.controls.extend(controls)


def walk(control):
    yield control
    content = getattr(control, 'content', None)
    if content is not None and not isinstance(content, str):
        yield from walk(content)
    for child in getattr(control, 'controls', []):
        yield from walk(child)


def test_flet_build_and_picker_flows(tmp_path, monkeypatch):
    monkeypatch.setenv('FLET_APP_STORAGE_DATA', str(tmp_path))
    page = FakePage()
    archive = tmp_path / 'test.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr('hello.txt', 'hello')
    from types import SimpleNamespace
    pick_files = AsyncMock(return_value=[SimpleNamespace(path=str(archive))])
    pick_directory = AsyncMock(return_value=str(tmp_path))
    monkeypatch.setattr(mobile.ft.FilePicker, 'pick_files', pick_files)
    monkeypatch.setattr(mobile.ft.FilePicker, 'get_directory_path', pick_directory)
    async def scenario():
        from flet.controls.context import _context_page
        token = _context_page.set(page)
        try:
            await mobile.main(page)
        finally:
            _context_page.reset(token)
        controls = list(walk(page.controls[0]))
        buttons = {c.content: c for c in controls if isinstance(c, mobile.ft.Button)}
        await buttons['🔍 ZIP Seç & Denetle'].on_click(None)
        await buttons['➕ Dosya Seç'].on_click(None)
        await buttons['📁 Hedef Klasör'].on_click(None)
        await asyncio.sleep(0)
        assert pick_files.await_count == 2
        assert page.services
    asyncio.run(scenario())
    assert pick_files.await_count == 2 and pick_directory.await_count == 1


def test_ui_blocks_duplicate_jobs_and_updates_on_page_thread(tmp_path, monkeypatch):
    monkeypatch.setenv('FLET_APP_STORAGE_DATA', str(tmp_path))
    page = FakePage()
    engine = mobile.BeytarchiverMobileEngine()
    monkeypatch.setattr(mobile, 'BeytarchiverMobileEngine', lambda: engine)
    from types import SimpleNamespace
    source = tmp_path / 'data'; source.write_text('data')
    monkeypatch.setattr(mobile.ft.FilePicker, 'pick_files',
                        AsyncMock(return_value=[SimpleNamespace(path=str(source))]))
    started, release = threading.Event(), threading.Event()
    calls = []
    def create(*args):
        calls.append(args)
        args[-1]('working', '#CDD6F4')
        args[-2](0.5, 'working')
        # Simulate the engine's finally block before the UI coroutine resumes.
        engine.is_running = False
        started.set()
        assert release.wait(5)
    monkeypatch.setattr(engine, 'create_zip_from_files', create)
    async def scenario():
        await mobile.main(page)
        controls = list(walk(page.controls[0]))
        buttons = {c.content: c for c in controls if isinstance(c, mobile.ft.Button)}
        await buttons['➕ Dosya Seç'].on_click(None)
        job = asyncio.create_task(buttons['🗜️ ZIP Oluştur'].on_click(None))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            assert buttons['🗜️ ZIP Oluştur'].disabled
            await buttons['🗜️ ZIP Oluştur'].on_click(None)
            assert len(calls) == 1
            buttons['🛑 İptal Et'].on_click(None)
            assert engine.cancel_event.is_set()
        finally:
            release.set()
            await job
        assert buttons['🛑 İptal Et'].disabled
        assert not buttons['🗜️ ZIP Oluştur'].disabled
        assert not engine.is_running
    asyncio.run(scenario())
    assert set(page.update_threads) == {threading.get_ident()}

