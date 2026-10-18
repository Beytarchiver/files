"""Security regressions; all file operations use temporary test data."""
import gzip
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock
import tarfile
import threading
import zipfile

import pytest


SOURCE = Path(__file__).parents[1] / 'venv/AkÃ„Â±llÃ„Â±_Dosya_YÃƒÂ¶neticisi/beytarchiver.py'
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location('beytarchiver', SOURCE)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def api(name):
    assert hasattr(app, name), f'Missing security implementation: {name}'
    return getattr(app, name)


def test_vault_encrypts_and_requires_master_password(tmp_path):
    path = tmp_path / 'passwords.enc'
    vault = api('PasswordVault')(path)
    vault.create('correct master password')
    vault.save({'example.org': ' secret with spaces '})
    first = path.read_bytes()
    assert b'example.org' not in first and b'secret with spaces' not in first
    vault.save(vault.data)
    assert path.read_bytes() != first
    vault.lock()
    assert not vault.data
    with pytest.raises(ValueError):
        vault.unlock('wrong master password')
    assert not vault.data
    vault.unlock('correct master password')
    assert vault.data == {'example.org': ' secret with spaces '}
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600


def test_vault_does_not_overwrite_existing_or_accept_tampered_data(tmp_path):
    path = tmp_path / 'passwords.enc'
    vault = api('PasswordVault')(path)
    vault.create('correct master password')
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        vault.create('another master password')
    assert path.read_bytes() == before
    document = json.loads(before)
    document['ciphertext'] = document['ciphertext'][:-8] + 'AAAAAAAA'
    path.write_text(json.dumps(document))
    vault.lock()
    with pytest.raises(ValueError):
        vault.unlock('correct master password')
    assert not vault.data


def test_vault_locked_save_and_weak_master_are_rejected(tmp_path):
    vault = api('PasswordVault')(tmp_path / 'passwords.enc')
    with pytest.raises(ValueError):
        vault.create('short')
    with pytest.raises(ValueError):
        vault.save({'site': 'password'})
    assert not vault.path.exists()


@pytest.mark.parametrize('name,data', [('empty.txt', b''), ('rapor.2026.pdf', b'report')])
def test_antivirus_does_not_flag_benign_names_or_empty_files(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    results, digest = app.BeytNativeAntivirus().scan_file(str(path))
    assert results == []
    assert len(digest) == 64


def test_antivirus_detects_disguised_executable(tmp_path):
    path = tmp_path / 'rapor.pdf.exe'
    path.write_bytes(b'not executed')
    results, _ = app.BeytNativeAntivirus().scan_file(str(path))
    assert any('ÃƒÂ§ift uzantÃ„Â±' in result for result in results)


def test_antivirus_reports_unreadable_file_instead_of_clean(tmp_path):
    results, digest = app.BeytNativeAntivirus().scan_file(str(tmp_path / 'missing'))
    assert digest is None
    assert any('okunamadÃ„Â±' in result.lower() for result in results)


@pytest.mark.parametrize('kind', ['zip', 'beyt', '7z', 'tar', 'tar.gz', 'gz'])
def test_extract_supported_formats(tmp_path, kind):
    archive = tmp_path / ('sample.' + kind)
    payload = b'representative content'
    if kind in ('zip', 'beyt'):
        with app.pyzipper.AESZipFile(archive, 'w', encryption=app.pyzipper.WZ_AES) as z:
            z.setpassword(b'password')
            z.writestr('hello.txt', payload)
    elif kind == '7z':
        with app.py7zr.SevenZipFile(archive, 'w', password='password') as z:
            z.writestr(payload, 'hello.txt')
    elif kind in ('tar', 'tar.gz'):
        with tarfile.open(archive, 'w:gz' if kind.endswith('.gz') else 'w') as t:
            member = tarfile.TarInfo('hello.txt'); member.size = len(payload)
            t.addfile(member, io.BytesIO(payload))
    else:
        archive.write_bytes(gzip.compress(payload))
    output = tmp_path / 'output'
    api('safe_extract_archive')(archive, output, 'password')
    expected = 'sample' if kind == 'gz' else 'hello.txt'
    assert (output / expected).read_bytes() == payload


@pytest.mark.parametrize('name', ['../escape.txt', '/absolute.txt', 'C:/escape.txt',
                                  '..\\escape.txt', 'ok/../../escape.txt', 'file:stream',
                                  'CON.txt', 'folder./file'])
def test_zip_rejects_unsafe_paths_without_leaving_output(tmp_path, name):
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('valid.txt', 'first')
        z.writestr(name, 'bad')
    output = tmp_path / 'output'
    with pytest.raises(ValueError):
        api('safe_extract_archive')(archive, output)
    assert not output.exists()
    assert not (tmp_path / 'escape.txt').exists()


@pytest.mark.parametrize('member_type', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_tar_rejects_links_and_special_files(tmp_path, member_type):
    archive = tmp_path / 'unsafe.tar'
    with tarfile.open(archive, 'w') as t:
        member = tarfile.TarInfo('link'); member.type = member_type
        member.linkname = '../escape'
        t.addfile(member)
    with pytest.raises(ValueError):
        api('safe_extract_archive')(archive, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('limits', [{'max_total_size': 4}, {'max_files': 1}])
def test_extract_enforces_limits(tmp_path, limits):
    archive = tmp_path / 'sample.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('one', b'12345'); z.writestr('two', b'12345')
    with pytest.raises(ValueError):
        api('safe_extract_archive')(archive, tmp_path / 'out', **limits)
    assert not (tmp_path / 'out').exists()


def test_gzip_enforces_streamed_size_limit(tmp_path):
    archive = tmp_path / 'sample.gz'
    archive.write_bytes(gzip.compress(b'x' * 10000))
    with pytest.raises(ValueError):
        api('safe_extract_archive')(archive, tmp_path / 'out', max_total_size=100)
    assert not (tmp_path / 'out').exists()


def test_extraction_never_overwrites_existing_destination(tmp_path):
    archive = tmp_path / 'sample.zip'
    with zipfile.ZipFile(archive, 'w') as z: z.writestr('keep', 'new')
    output = tmp_path / 'out'; output.mkdir()
    (output / 'keep').write_text('original')
    with pytest.raises(FileExistsError):
        api('safe_extract_archive')(archive, output)
    assert (output / 'keep').read_text() == 'original'


@pytest.mark.parametrize('kind', ['zip', '7z'])
def test_wrong_archive_password_leaves_no_output(tmp_path, kind):
    archive = tmp_path / ('encrypted.' + kind)
    if kind == 'zip':
        with app.pyzipper.AESZipFile(archive, 'w', encryption=app.pyzipper.WZ_AES) as z:
            z.setpassword(b'correct'); z.writestr('data', b'content')
    else:
        with app.py7zr.SevenZipFile(archive, 'w', password='correct') as z:
            z.writestr(b'content', 'data')
    with pytest.raises(Exception):
        app.safe_extract_archive(archive, tmp_path / 'out', 'incorrect')
    assert not (tmp_path / 'out').exists()
    assert not list(tmp_path.glob('.beyt-extract-*'))


def test_7z_rejects_symbolic_link(tmp_path):
    original = tmp_path / 'original'; original.write_bytes(b'keep')
    link = tmp_path / 'link'; link.symlink_to(original)
    archive = tmp_path / 'link.7z'
    with app.py7zr.SevenZipFile(archive, 'w', dereference=False) as z:
        z.write(link, 'link')
    with pytest.raises(ValueError):
        app.safe_extract_archive(archive, tmp_path / 'out')
    assert original.read_bytes() == b'keep'
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('names', [('a', 'A'), ('a', 'a/b'), ('a/b', 'a')])
def test_extraction_rejects_colliding_paths(tmp_path, names):
    archive = tmp_path / 'collision.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for name in names: z.writestr(name, b'content')
    with pytest.raises(ValueError):
        app.safe_extract_archive(archive, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_vault_failed_write_preserves_previous_data(tmp_path, monkeypatch):
    vault = app.PasswordVault(tmp_path / 'vault.enc')
    vault.create('correct master password')
    vault.save({'original': 'password'})
    before = vault.path.read_bytes()
    def fail(*args): raise OSError('simulated disk failure')
    monkeypatch.setattr(app.os, 'replace', fail)
    with pytest.raises(OSError): vault.save({'new': 'data'})
    assert vault.path.read_bytes() == before
    assert vault.data == {'original': 'password'}
    assert not list(tmp_path.glob('.beyt-vault-*'))


def test_corrupt_archive_is_not_reported_as_success(tmp_path):
    archive = tmp_path / 'corrupt.zip'; archive.write_bytes(b'not an archive')
    with pytest.raises(Exception): app.safe_extract_archive(archive, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_ui_queue_survives_callback_failure():
    queue = Queue()
    queue.put((lambda: 1 / 0, (), {}))
    called = []
    queue.put((called.append, ('next callback',), {}))
    target = SimpleNamespace(ui_queue=queue, after=Mock(), report_callback_exception=Mock(),
                             process_ui_queue=Mock(), _closing=False)
    app.BeytarchiverV37App.process_ui_queue(target)
    assert called == ['next callback']
    target.after.assert_called_once()
    target.report_callback_exception.assert_called_once()


def test_shred_cancel_leaves_file_untouched(tmp_path, monkeypatch):
    path = tmp_path / 'keep.txt'; path.write_text('keep')
    monkeypatch.setattr(app.filedialog, 'askopenfilename', lambda **kw: str(path))
    monkeypatch.setattr(app.messagebox, 'askyesno', lambda *a, **kw: False)
    worker = Mock()
    monkeypatch.setattr(app.threading, 'Thread', worker)
    target = SimpleNamespace(lbl_shred_file=Mock(), shred_engine=Mock())
    app.BeytarchiverV37App.start_shred(target)
    worker.assert_not_called()
    assert path.read_text() == 'keep'


def test_overwrite_deletes_only_regular_file(tmp_path):
    path = tmp_path / 'temporary'; path.write_bytes(b'x' * (1024 * 1024 + 7))
    api('overwrite_and_delete')(path)
    assert not path.exists()


def test_overwrite_refuses_symlink_and_hardlink(tmp_path):
    path = tmp_path / 'keep'; path.write_bytes(b'original')
    link = tmp_path / 'symbolic'; link.symlink_to(path)
    with pytest.raises(ValueError): api('overwrite_and_delete')(link)
    link.unlink(); os.link(path, link)
    with pytest.raises(ValueError): api('overwrite_and_delete')(link)
    assert path.read_bytes() == b'original'


def test_ui_queue_does_not_starve_the_event_loop():
    queue = Queue()
    for _ in range(250): queue.put((lambda: None, (), {}))
    target = SimpleNamespace(ui_queue=queue, after=Mock(), report_callback_exception=Mock(),
                             process_ui_queue=Mock(), _closing=False)
    app.BeytarchiverV37App.process_ui_queue(target)
    assert not queue.empty()
    target.after.assert_called_once()


def test_passwords_view_uses_existing_panel():
    keys = ['compress', 'extract', 'vault', 'ram', 'updater', 'antivirus', 'cleaner',
            'analyzer', 'duplicates', 'shredder', 'organizer', 'startup', 'hash',
            'monitor', 'password', 'settings', 'transfer']
    target = SimpleNamespace(**{key + '_panel': Mock() for key in keys},
                             nav_btns={}, load_startup_apps=Mock(), start_monitor_loop=Mock(),
                             lock_passwords=Mock())
    app.BeytarchiverV37App.show_view(target, 'passwords')
    target.password_panel.pack.assert_called_once()


@pytest.mark.parametrize('method,args,tree', [
    ('analyze_disk_engine', ('TARGET',), 'ana_tree'),
    ('dup_scan_engine', ('TARGET',), 'dup_tree'),
])
def test_background_scans_never_read_tree_widgets(tmp_path, method, args, tree):
    owner = threading.get_ident()
    class Tree:
        def get_children(self):
            assert threading.get_ident() == owner, 'Tk accessed from worker'
            return ()
        delete = Mock()
        insert = Mock()
    queue = Queue()
    target = SimpleNamespace(**{tree: Tree()}, av_engine=app.BeytNativeAntivirus(),
                             lbl_ana_path=Mock(), lbl_dup_status=Mock(),
                             clear_tree=lambda t: None,
                             safe_ui_update=lambda f, *a, **kw: queue.put((f,a,kw)))
    failures = []
    def run():
        try: getattr(app.BeytarchiverV37App, method)(target, str(tmp_path))
        except Exception as exc: failures.append(exc)
    worker = threading.Thread(target=run); worker.start(); worker.join(timeout=5)
    assert not failures
    assert not worker.is_alive()


def test_password_ui_preserves_spaces_and_replaces_existing_row(tmp_path):
    vault = api('PasswordVault')(tmp_path / 'passwords.enc')
    vault.create('correct master password')
    target = SimpleNamespace(password_vault=vault, ent_site=Mock(), ent_pass=Mock(),
                             refresh_passwords=Mock(), password_activity=Mock())
    target.ent_site.get.return_value = 'example.org'
    target.ent_pass.get.return_value = ' password with spaces '
    app.BeytarchiverV37App.save_password(target)
    assert vault.data == {'example.org': ' password with spaces '}
    target.ent_pass.get.return_value = 'replacement'
    app.BeytarchiverV37App.save_password(target)
    assert vault.data == {'example.org': 'replacement'}
    vault.lock(); vault.unlock('correct master password')
    assert vault.data == {'example.org': 'replacement'}


def test_cleaner_worker_uses_captured_options_only(tmp_path):
    (tmp_path / 'temporary').write_bytes(b'1234')
    queue = Queue()
    target = SimpleNamespace(clear_tree=Mock(), clean_tree=Mock(),
                             finish_clean_scan=Mock(),
                             safe_ui_update=lambda f, *a, **kw: queue.put((f,a,kw)))
    app.BeytarchiverV37App.scan_engine(target, [(str(tmp_path), 'Test')])
    while not queue.empty():
        f, a, kw = queue.get(); f(*a, **kw)
    target.finish_clean_scan.assert_called_once()
    files, total = target.finish_clean_scan.call_args.args
    assert files == [(str(tmp_path / 'temporary'), 4)]
    assert total == 4


def test_compression_captures_password_without_stripping(monkeypatch):
    target = SimpleNamespace(_compressing=False, files_to_archive=['one'],
                             combo_fmt=Mock(), entry_pass=Mock(), btn_start=Mock(),
                             compress_engine=Mock())
    target.combo_fmt.get.return_value='zip'
    target.entry_pass.get.return_value=' password '
    worker=Mock(); monkeypatch.setattr(app.threading, 'Thread', worker)
    app.BeytarchiverV37App.start_compression(target)
    assert worker.call_args.kwargs['args'] == (('one',), 'zip', ' password ')


def test_extraction_captures_archive_before_starting_worker(monkeypatch):
    target = SimpleNamespace(_extracting=False, archive_to_extract='one.zip',
                             entry_ext_pass=Mock(), btn_start_extract=Mock(), extract_engine=Mock())
    target.entry_ext_pass.get.return_value=' password '
    worker=Mock(); monkeypatch.setattr(app.threading, 'Thread', worker)
    app.BeytarchiverV37App.start_extraction(target)
    assert worker.call_args.kwargs['args'] == ('one.zip', ' password ')


@pytest.mark.parametrize('kind', ['zip', '7z', 'tar'])
def test_compression_worker_round_trip(tmp_path, monkeypatch, kind):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'hello.txt'; source.write_bytes(b'real compression output')
    statuses = []
    target = SimpleNamespace(lbl_status=SimpleNamespace(configure=lambda **kw: statuses.append(kw['text'])),
                             finish_compression=Mock(), safe_ui_update=lambda f, *a, **kw: f(*a, **kw))
    password = '' if kind == 'tar' else ' password with spaces '
    app.BeytarchiverV37App.compress_engine(target, (str(source),), kind, password)
    assert statuses[-1].startswith('SÃ„Â±kÃ„Â±Ã…Å¸tÃ„Â±rma BaÃ…Å¸arÃ„Â±lÃ„Â±:')
    archive = next(tmp_path.glob('beyt_archive_*.' + kind))
    app.safe_extract_archive(archive, tmp_path / 'out', password)
    assert (tmp_path / 'out/hello.txt').read_bytes() == source.read_bytes()
    target.finish_compression.assert_called_once()


@pytest.mark.skipif(not os.environ.get('DISPLAY'), reason='Requires a graphical display')
def test_real_gui_navigation_vault_and_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(app.Path, 'home', lambda: tmp_path)
    version = tmp_path / 'version'; version.write_text(app.CURRENT_VERSION)
    monkeypatch.setattr(app, 'VERSION_FILE', str(version))
    monkeypatch.setattr(app.simpledialog, 'askstring', lambda *a, **kw: 'test master password')
    monkeypatch.setattr(app.messagebox, 'askyesno', lambda *a, **kw: True)
    window = app.BeytarchiverV37App()
    errors = []
    window.report_callback_exception = lambda *error: errors.append(error)
    try:
        for view in window.nav_btns:
            window.show_view(view)
            window.update()
        window.show_view('passwords')
        window.unlock_passwords()
        window.ent_site.insert(0, '00123')
        window.ent_pass.insert(0, ' secret with spaces ')
        window.save_password()
        window.ent_site.insert(0, '123')
        window.ent_pass.insert(0, 'different password')
        window.save_password()
        row = window.pass_tree.get_children()[0]
        assert str(window.pass_tree.item(row)['values'][1]) == 'Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢'
        window.pass_tree.selection_set(row)
        window.reveal_password()
        assert window.pass_tree.item(row)['values'][1] == ' secret with spaces '
        window.delete_password()
        assert window.password_vault.data == {'123': 'different password'}
        window.show_view('compress')
        assert not window.password_vault.unlocked
        assert not window.pass_tree.get_children()
        window.safe_ui_update(window.lbl_status.configure, text='Queue works')
        window.after(300, window.quit)
        window.mainloop()
        assert window.lbl_status.cget('text') == 'Queue works'
        assert not errors
    finally:
        window.close_app()
