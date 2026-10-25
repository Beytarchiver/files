import importlib.util
import json
import os
from pathlib import Path
from queue import Queue
import threading
import time
from unittest.mock import Mock

import pytest


def panel_module():
    import lan_transfer
    assert (Path(lan_transfer.__file__).parent / 'panel.py').exists(), 'Transfer panel not implemented'
    from lan_transfer import panel
    return panel


def test_network_list_contains_only_active_private_ipv4(monkeypatch):
    module = panel_module()
    import socket
    from types import SimpleNamespace
    monkeypatch.setattr(module.psutil, 'net_if_addrs', lambda: {
        'Wi-Fi': [SimpleNamespace(family=socket.AF_INET, address='192.168.1.2')],
        'Loopback': [SimpleNamespace(family=socket.AF_INET, address='127.0.0.1')],
        'Public': [SimpleNamespace(family=socket.AF_INET, address='8.8.8.8')],
        'Offline': [SimpleNamespace(family=socket.AF_INET, address='10.0.0.2')]})
    monkeypatch.setattr(module.psutil, 'net_if_stats', lambda: {
        name: SimpleNamespace(isup=name != 'Offline') for name in ('Wi-Fi','Loopback','Public','Offline')})
    assert list(module.local_interfaces().values()) == ['192.168.1.2']


@pytest.mark.skipif(os.name != 'nt' and not os.environ.get('DISPLAY'), reason='Requires a graphical display')
@pytest.mark.parametrize('mode', ['dark', 'light'])
def test_transfer_instructions_remain_readable_on_plain_tk_root(mode):
    module = panel_module()
    import tkinter as tk
    previous = module.ctk.get_appearance_mode()
    module.ctk.set_appearance_mode(mode)
    root = tk.Tk()
    root.configure(bg='white')
    panel = module.TransferPanel(root, lambda callback, *args: callback(*args))
    panel.pack(fill='both', expand=True)
    try:
        root.update()
        def luminance(color):
            channels = [value / 65535 for value in root.winfo_rgb(color)]
            linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                      for v in channels]
            return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
        for widget in (panel.status, panel.qr_label):
            # Native Tk colors include the background inherited through transparent frames.
            foreground = luminance(widget._label.cget('foreground'))
            background = luminance(widget._label.cget('background'))
            contrast = (max(foreground, background) + .05) / (min(foreground, background) + .05)
            assert contrast >= 4.5, f'{mode}: unreadable instructions (contrast {contrast:.2f})'
            assert widget.winfo_viewable()
    finally:
        panel.shutdown()
        root.destroy()
        module.ctk.set_appearance_mode(previous)


@pytest.mark.skipif(os.name != 'nt' and not os.environ.get('DISPLAY'), reason='Requires a graphical display')
def test_panel_worker_dispatch_and_duplicate_start(monkeypatch):
    module = panel_module()
    import tkinter as tk
    root = tk.Tk()
    owner = threading.get_ident()
    callbacks = Queue()
    servers = []
    class Server:
        def __init__(self, events):
            servers.append(self); self.events=events; self.state='idle'; self.session=Mock()
        def start(self, host):
            assert threading.get_ident() != owner
            assert host == '192.168.1.2'
            return {'v':1, 'origin':'https://192.168.1.2:1234', 'session_id':'a'*32,
                    'cert_sha256':'b'*64, 'pair_token':'A'*43, 'expires_at':'2099-01-01T00:00:00Z'}
        def stop(self): pass
    monkeypatch.setattr(module, 'local_interfaces', lambda: {'Wi-Fi — 192.168.1.2':'192.168.1.2'})
    panel = module.TransferPanel(root, lambda f,*a,**kw: callbacks.put((f,a,kw)), server_factory=Server)
    panel.pack()
    original_get = panel.interface.get
    def checked_get():
        assert threading.get_ident() == owner, 'worker accessed Tk'
        return original_get()
    monkeypatch.setattr(panel.interface, 'get', checked_get)
    try:
        panel.start_connection(); panel.start_connection()
        end=time.monotonic()+3
        while callbacks.empty() and time.monotonic()<end: root.update(); time.sleep(.01)
        assert len(servers)==1
        while not callbacks.empty():
            f,a,kw=callbacks.get(); f(*a,**kw)
        assert panel.status.cget('text').startswith('QR kodunu')
        panel.shutdown()
        # A late completion must not resurrect a closed panel.
        panel._started(servers[0], {})
        assert panel._closing
    finally:
        panel.shutdown(); root.destroy()


@pytest.mark.skipif(os.name != 'nt' and not os.environ.get('DISPLAY'), reason='Requires a graphical display')
def test_main_window_contains_transfer_panel_and_shuts_it_down(tmp_path, monkeypatch):
    panel_module()
    source=Path(__file__).parents[2]/'beytarchiver.py'
    spec=importlib.util.spec_from_file_location('beyt_lan_gui',source)
    app=importlib.util.module_from_spec(spec); spec.loader.exec_module(app)
    monkeypatch.setattr(app.Path,'home',lambda:tmp_path)
    marker=tmp_path/'version'; marker.write_text(app.CURRENT_VERSION)
    monkeypatch.setattr(app,'VERSION_FILE',str(marker))
    window=app.BeytarchiverApp()
    try:
        assert 'transfer' in window.nav_btns
        window.show_view('transfer'); window.update()
        assert window.transfer_panel.winfo_manager() == 'pack'
        assert not window.transfer_panel._closing
        window.close_app()
        assert window.transfer_panel._closing
    finally:
        if not window._closing: window.close_app()
