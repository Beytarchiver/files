import hashlib
import os
import faulthandler
import http.client
import json
from pathlib import Path
from queue import Queue
import socket
import ssl
import time
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conftest import pair_request


@pytest.fixture
def server(clock):
    import lan_transfer
    assert (Path(lan_transfer.__file__).parent / 'server.py').exists(), 'HTTPS service not implemented'
    from lan_transfer.server import TransferServer
    instance = TransferServer(Queue(), clock=clock)
    # Transport fixtures use loopback, never relaxed production QR parsing.
    instance.start('127.0.0.1')
    yield instance
    instance.stop()
    assert not instance.work_dir.exists()


def connection(server, hostname=None, trust=None):
    context = ssl.create_default_context(cafile=str(trust or server.identity.cert_path))
    conn = http.client.HTTPSConnection(hostname or '127.0.0.1', server.port, context=context, timeout=3)
    return conn


def request(server, method, path, body=None, token=None, headers=None):
    conn = connection(server)
    data = None if body is None else json.dumps(body)
    extra = {'Authorization': 'Bearer ' + token} if token else {}
    if data is not None: extra['Content-Type'] = 'application/json'
    extra.update(headers or {})
    try:
        conn.request(method, path, data, extra)
        response = conn.getresponse()
        payload = response.read()
        if response.getheader('Content-Type', '').startswith('application/json'):
            payload = json.loads(payload)
        return response.status, payload
    finally:
        conn.close()


def approve(server):
    status, pair = request(server, 'POST', '/v1/pair', pair_request(server.qr()))
    assert status == 202
    server.approve(pair['request_id'])
    status, result = request(server, 'GET', '/v1/pair/' + pair['request_id'], token=pair['poll_token'])
    assert status == 200
    return result['access_token']


def test_tls_identity_and_auth(server, tmp_path):
    from lan_transfer.tls import create_identity
    conn = connection(server); conn.connect()
    cert = conn.sock.getpeercert(binary_form=True)
    assert hashlib.sha256(cert).hexdigest() == server.identity.cert_sha256
    conn.close()
    other = create_identity('127.0.0.1', tmp_path)
    with pytest.raises(ssl.SSLCertVerificationError): connection(server, trust=other.cert_path).connect()
    with pytest.raises(ssl.SSLCertVerificationError): connection(server, hostname='localhost').connect()
    assert request(server, 'GET', '/v1/offer')[0] == 401
    assert request(server, 'GET', '/v1/files/../../etc/passwd')[0] == 401


@pytest.mark.parametrize('payload', [b'', b'hello' * 10000], ids=['empty', 'content'])
def test_receipt_required_and_idempotent(server, tmp_path, payload):
    token = approve(server)
    source = tmp_path / 'example'; source.write_bytes(payload)
    server.offer(source)
    status, offer = request(server, 'GET', '/v1/offer', token=token)
    assert status == 200 and offer['size'] == len(payload)
    assert 'staged_path' not in offer
    endpoint = '/v1/files/' + offer['transfer_id']
    assert request(server, 'GET', endpoint, token=token) == (200, payload)
    # The delivery thread flips the state after the client closes; poll instead of racing it.
    deadline = time.monotonic() + 5
    while server.state != 'awaiting_receipt' and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.state == 'awaiting_receipt'
    receipt = {key: offer[key] for key in ('transfer_id', 'size', 'sha256')}
    assert request(server, 'POST', '/v1/receipt', receipt | {'sha256': 'bad'}, token)[0] == 400
    for _ in range(2): assert request(server, 'POST', '/v1/receipt', receipt, token)[0] == 200
    assert server.state == 'completed'
    assert source.read_bytes() == payload


def test_transfer_cannot_be_replaced_or_downloaded_twice(server, tmp_path):
    from lan_transfer.protocol import ProtocolError
    token = approve(server)
    source = tmp_path / 'example'; source.write_bytes(b'content')
    server.offer(source)
    with pytest.raises(ProtocolError) as e: server.offer(source)
    assert e.value.status == 409
    _, offer = request(server, 'GET', '/v1/offer', token=token)
    path = '/v1/files/' + offer['transfer_id']
    assert request(server, 'GET', path, token=token)[0] == 200
    assert request(server, 'GET', path, token=token)[0] == 409


def test_cancel_and_expiry(server, tmp_path, clock):
    token = approve(server)
    source = tmp_path / 'example'; source.write_bytes(b'content')
    server.offer(source)
    _, offer = request(server, 'GET', '/v1/offer', token=token)
    body = {'transfer_id': offer['transfer_id']}
    for _ in range(2): assert request(server, 'POST', '/v1/cancel', body, token)[0] == 200
    assert server.state == 'cancelled'
    assert not list(server.work_dir.glob('offer-*'))
    assert request(server, 'GET', '/v1/files/' + offer['transfer_id'], token=token)[0] == 409
    clock.advance(900)
    assert request(server, 'GET', '/v1/offer', token=token)[0] == 410


def test_request_limits(server):
    assert request(server, 'POST', '/v1/pair', {'large': 'x' * 4096})[0] == 413
    conn = connection(server)
    conn.request('POST', '/v1/pair', headers={'Content-Length': '-1'})
    assert conn.getresponse().status == 400; conn.close()
    conn = connection(server)
    conn.request('POST', '/v1/pair', headers={'Transfer-Encoding': 'chunked'})
    assert conn.getresponse().status == 400; conn.close()
    assert request(server, 'GET', '/not-real')[0] == 404


@pytest.mark.parametrize('iteration', range(int(os.environ.get('BEYT_TLS_REPETITIONS', '1'))))
def test_half_open_tls_handshake_does_not_block_other_clients(server, monkeypatch, iteration):
    first_handshake = threading.Event()
    original_handshake = ssl.SSLSocket.do_handshake

    def observe_handshake(sock, *args, **kwargs):
        if sock.server_side:
            first_handshake.set()
        return original_handshake(sock, *args, **kwargs)

    monkeypatch.setattr(ssl.SSLSocket, 'do_handshake', observe_handshake)
    raw = socket.create_connection(('127.0.0.1', server.port), timeout=2)
    try:
        # Exercise an actual pending server handshake, not merely a connection
        # queued in the OS backlog before its worker has started.
        assert first_handshake.wait(3), 'Server did not start the first TLS handshake'
        try:
            assert request(server, 'GET', '/v1/offer')[0] == 401
        except TimeoutError:
            # Preserve the failure and show whether accept, registry locking or
            # TLS is blocking on the runner. No socket contents or tokens.
            faulthandler.dump_traceback(all_threads=True)
            raise
    finally:
        raw.close()


def test_connection_limit_and_stop_closes_pending_handshakes(server):
    clients = [socket.create_connection(('127.0.0.1', server.port), timeout=2) for _ in range(4)]
    try:
        # Wait for actual admission rather than sleeping for a guessed interval.
        end = time.monotonic() + 2
        while server.connection_count != 4 and time.monotonic() < end: time.sleep(.01)
        assert server.connection_count == 4
        extra = socket.create_connection(('127.0.0.1', server.port), timeout=2)
        try: assert extra.recv(1) == b''
        finally: extra.close()
        server.stop()
        assert server.connection_count == 0
    finally:
        for client in clients: client.close()


def test_expiry_during_preparation_cleans_new_snapshot(server, tmp_path, clock, monkeypatch):
    from lan_transfer import server as module
    from lan_transfer.protocol import ProtocolError
    approve(server)
    source=tmp_path/'source'; source.write_bytes(b'content')
    original=module.prepare_offer
    def expire(*args):
        result=original(*args)
        clock.advance(900)
        return result
    monkeypatch.setattr(module,'prepare_offer',expire)
    with pytest.raises(ProtocolError): server.offer(source)
    assert not list(server.work_dir.glob('offer-*'))


def test_start_failure_is_clean_and_stop_is_repeatable(monkeypatch):
    from lan_transfer import server as module
    instance=module.TransferServer(Queue())
    def fail(*args): raise OSError('simulated bind failure')
    monkeypatch.setattr(module,'_HttpServer',fail)
    with pytest.raises(OSError): instance.start('127.0.0.1')
    instance.stop(); instance.stop()
    assert not instance.work_dir.exists()


def test_receipt_cannot_complete_cancelled_transfer(server, tmp_path):
    token=approve(server)
    source=tmp_path/'source'; source.write_bytes(b'content')
    server.offer(source)
    _, offer=request(server,'GET','/v1/offer',token=token)
    server.cancel(offer['transfer_id'])
    receipt={key:offer[key] for key in ('transfer_id','size','sha256')}
    assert request(server,'POST','/v1/receipt',receipt,token)[0] == 409


def test_slow_handshake_times_out(server):
    # Inject only the I/O timeout, keeping the real TLS / worker behavior.
    server._http.io_timeout=.05
    raw=socket.create_connection(('127.0.0.1',server.port),timeout=2)
    try: assert raw.recv(1) == b''
    finally: raw.close()


def test_cancelled_sender_cannot_delete_replacement_offer(server, tmp_path):
    token=approve(server)
    source=tmp_path/'source'; source.write_bytes(b'content')
    server.offer(source)
    first=server.current_offer()
    entered, release=threading.Event(), threading.Event()
    class BlockedWriter:
        def write(self, data):
            entered.set()
            assert release.wait(3)
            raise OSError('cancelled old stream')
    handler=SimpleNamespace(wfile=BlockedWriter(), connection=Mock(), send_response=Mock(),
                            send_header=Mock(), end_headers=Mock())
    worker=threading.Thread(target=server.send_file,args=(handler,first['transfer_id'],token))
    worker.start()
    try:
        assert entered.wait(3)
        server.cancel(first['transfer_id'])
        server.offer(source)
        second=server.current_offer()
        assert second['transfer_id'] != first['transfer_id']
        release.set(); worker.join(3)
        assert not worker.is_alive()
        assert server.state == 'ready'
        assert server.current_offer() == second
        assert len(list(server.work_dir.glob('offer-*'))) == 1
    finally:
        release.set(); worker.join(3)


def test_receipt_rechecks_session_after_body_read(server, tmp_path, clock, monkeypatch):
    from lan_transfer import server as module
    token=approve(server)
    source=tmp_path/'source'; source.write_bytes(b'content')
    server.offer(source)
    _,offer=request(server,'GET','/v1/offer',token=token)
    assert request(server,'GET','/v1/files/'+offer['transfer_id'],token=token)[0] == 200
    original=module._Handler._body
    def expire_after_read(handler):
        result=original(handler)
        clock.advance(901)
        return result
    monkeypatch.setattr(module._Handler,'_body',expire_after_read)
    receipt={key:offer[key] for key in ('transfer_id','size','sha256')}
    assert request(server,'POST','/v1/receipt',receipt,token)[0] == 410
    assert server.state != 'completed'
