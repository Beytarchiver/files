import json
import os
from pathlib import Path

import pytest
import psutil


def implementation():
    import lan_transfer
    assert (Path(lan_transfer.__file__).parent/'workspace.py').exists(), 'Crash cleanup not implemented'
    from lan_transfer.workspace import create_work_dir
    return create_work_dir


def owner(directory, created):
    (directory/'owner.json').write_text(json.dumps({'schema':1,'pid':os.getpid(),'created':created}))


def test_workspace_preserves_active_and_unknown_files_and_cleans_abandoned(tmp_path):
    stale=tmp_path/'session-stale'; stale.mkdir(); owner(stale,1)
    (stale/'offer-old').write_bytes(b'old staged data')
    active=tmp_path/'session-active'; active.mkdir()
    owner(active,psutil.Process().create_time())
    unknown=tmp_path/'session-unknown'; unknown.mkdir(); owner(unknown,1)
    (unknown/'user-document').write_text('keep')
    new=implementation()(tmp_path)
    assert new.is_dir() and (new/'owner.json').exists()
    assert not stale.exists()
    assert active.exists()
    assert (unknown/'user-document').read_text() == 'keep'
    if os.name != 'nt': assert new.stat().st_mode & 0o777 == 0o700


def test_workspace_never_follows_symlinks(tmp_path, make_symlink):
    external=tmp_path/'outside'; external.mkdir(); (external/'keep').write_text('keep')
    root=tmp_path/'root'; root.mkdir()
    make_symlink(root/'session-link', external, target_is_directory=True)
    implementation()(root)
    assert (external/'keep').read_text() == 'keep'
    alias=tmp_path/'alias'; alias.symlink_to(root,target_is_directory=True)
    with pytest.raises(ValueError): implementation()(alias)
