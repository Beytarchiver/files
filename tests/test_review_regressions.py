from test_beytarchiver import app
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


def test_empty_scan(tmp_path):
    (tmp_path/'a').touch(); (tmp_path/'b').touch()
    groups=[]
    obj=SimpleNamespace(safe_ui_update=lambda f,*a,**k:f(*a,**k), reset_dup_tree=lambda:None,
        populate_dup_tree=lambda g:groups.extend(g), av_engine=app.BeytNativeAntivirus(), lbl_dup_status=Mock())
    app.BeytarchiverApp.dup_scan_engine(obj,str(tmp_path))
    assert groups == []


def test_noop_preserves_undo():
    obj=SimpleNamespace(_undo_moves=[('a','b')],btn_org_undo=Mock(),lbl_org_status=Mock())
    app.BeytarchiverApp.finish_organize(obj,[], 'done')
    assert obj._undo_moves == [('a','b')]


def test_unique_extract_path(tmp_path):
    base=tmp_path/'a_extracted'; base.mkdir()
    assert app.unused_path(base) == tmp_path/'a_extracted (1)'


def test_missing_clean_file_is_success(tmp_path):
    counts=[]
    obj=SimpleNamespace(safe_ui_update=lambda f,*a:f(*a),finish_cleaning=counts.append)
    app.BeytarchiverApp.clean_engine(obj,[(tmp_path/'gone',0)],False)
    assert counts==[0]


def test_last_duplicate_protected(tmp_path):
    a=tmp_path/'a'; b=tmp_path/'b'; a.write_text('same'); b.write_text('same')
    assert not app.duplicates_have_survivors([(None,4,[str(a),str(b)])],[str(a),str(b)])
    assert app.duplicates_have_survivors([(None,4,[str(a),str(b)])],[str(b)])
    a.unlink()
    assert not app.duplicates_have_survivors([(None,4,[str(a),str(b)])],[str(b)])


def test_verified_download(tmp_path, monkeypatch):
    import io, hashlib
    class Response(io.BytesIO):
        headers={'Content-Length':'4'}
    monkeypatch.setattr(app.urllib.request,'urlopen',lambda *a,**k:Response(b'data'))
    url='https://github.com/Beytarchiver/files/releases/download/v4/a.exe'
    dest=tmp_path/'a.exe'
    digest='sha256:'+hashlib.sha256(b'data').hexdigest()
    app.download_verified(url,dest,digest)
    assert dest.read_bytes()==b'data'
    with pytest.raises(FileExistsError): app.download_verified(url,dest,digest)
    with pytest.raises(ValueError): app.download_verified(url,tmp_path/'bad.exe','sha256:'+'0'*64)
    assert not (tmp_path/'bad.exe').exists()
    assert not list(tmp_path.glob('*.part'))
    with pytest.raises(ValueError): app.download_verified('https://evil.test/a.exe',tmp_path/'evil.exe',digest)


@pytest.mark.parametrize('method,args', [('compress_engine',('zip','')),('vault_engine',('password',))])
def test_failed_archive_leaves_no_output(tmp_path, method, args):
    missing=tmp_path/'missing.txt'
    obj=SimpleNamespace(safe_ui_update=lambda f,*a,**kw:f(*a,**kw),
        lbl_status=Mock(),lbl_vault_status=Mock(),finish_compression=lambda:None)
    getattr(app.BeytarchiverApp,method)(obj,[str(missing)],*args)
    assert not list(tmp_path.glob('secure_vault*'))
