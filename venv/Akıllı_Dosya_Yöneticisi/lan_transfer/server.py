"""A deliberately small HTTPS API serving only locally approved file snapshots."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import shutil
import socket
from socketserver import ThreadingMixIn
import ssl
import threading
import time

from .files import prepare_offer
from .protocol import CHUNK_SIZE, ProtocolError, decode_json
from .session import PairingSession
from .tls import create_identity
from .workspace import create_work_dir


class _HttpServer(ThreadingMixIn, HTTPServer):
    daemon_threads = False
    block_on_close = True
    io_timeout = 30

    def __init__(self, address, owner, context):
        self.owner, self.context = owner, context
        self._slots = threading.BoundedSemaphore(4)
        self._clients = set()
        self._clients_lock = threading.Lock()
        super().__init__(address, _Handler)

    def process_request(self, request, address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self._clients_lock:
            self._clients.add(request)
        try:
            super().process_request(request, address)
        except BaseException:
            with self._clients_lock: self._clients.discard(request)
            self._slots.release()
            raise

    def process_request_thread(self, raw, address):
        secured = None
        try:
            raw.settimeout(self.io_timeout)
            with self._clients_lock:
                secured = self.context.wrap_socket(raw, server_side=True, do_handshake_on_connect=False)
                self._clients.discard(raw)
                self._clients.add(secured)
            secured.do_handshake()
            self.finish_request(secured, address)
        except (OSError, ValueError):
            pass  # Peer disconnect, failed TLS or timeout; never log tokens or paths.
        finally:
            if secured is not None:
                self.shutdown_request(secured)
            else:
                self.shutdown_request(raw)
            with self._clients_lock:
                self._clients.discard(raw)
                self._clients.discard(secured)
            self._slots.release()

    def close_clients(self):
        with self._clients_lock:
            for client in tuple(self._clients):
                try: client.shutdown(socket.SHUT_RDWR)
                except OSError: pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    server_version = 'BeytarchiverLAN/1'
    sys_version = ''

    def log_message(self, *args):
        pass

    def _reply(self, status, data=None):
        payload = b'' if data is None else json.dumps(data, ensure_ascii=True).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        if data is not None: self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        if payload: self.wfile.write(payload)

    def _token(self):
        values = self.headers.get_all('Authorization', [])
        if len(values) != 1 or not values[0].startswith('Bearer '):
            raise ProtocolError(401, 'bearer_required')
        token = values[0][7:]
        if len(token) > 128:
            raise ProtocolError(401, 'invalid_bearer')
        return token

    def _body(self):
        sizes = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(sizes) != 1 or not re.fullmatch(r'[0-9]{1,10}', sizes[0]):
            raise ProtocolError(400, 'invalid_content_length')
        size = int(sizes[0])
        if size > 4096: raise ProtocolError(413, 'body_too_large')
        if not self.headers.get('Content-Type', '').lower().startswith('application/json'):
            raise ProtocolError(400, 'expected_json')
        raw = self.rfile.read(size)
        if len(raw) != size: raise ProtocolError(400, 'truncated_body')
        try: return decode_json(raw.decode('utf-8'))
        except (ValueError, UnicodeError): raise ProtocolError(400, 'invalid_json') from None

    def do_GET(self):
        self._route('GET')

    def do_POST(self):
        self._route('POST')

    def _route(self, method):
        owner = self.server.owner
        try:
            if method == 'POST' and self.path == '/v1/pair':
                body = self._body()
                result = owner.session.request_pair(body, self.client_address[0])
                owner.emit('pair_requested', request_id=result['request_id'], code=result['code'],
                           device_name=body.get('device_name', ''))
                self._reply(202, result)
            elif method == 'GET' and re.fullmatch('/v1/pair/[0-9a-f]{32}', self.path):
                self._reply(200, owner.session.pair_status(self.path.rsplit('/', 1)[1], self._token()))
            elif self.path == '/v1/offer' and method == 'GET':
                owner.session.authorize(self._token())
                offer = owner.current_offer()
                self._reply(200 if offer else 204, offer)
            elif self.path.startswith('/v1/files/') and method == 'GET':
                token = self._token()
                owner.session.authorize(token)
                if self.headers.get('Range'): raise ProtocolError(400, 'range_not_supported')
                owner.send_file(self, self.path[len('/v1/files/'):], token)
            elif self.path in ('/v1/receipt', '/v1/cancel') and method == 'POST':
                token = self._token()
                owner.session.authorize(token)
                body = self._body()
                if self.path == '/v1/receipt': owner.receipt(body, token)
                else: owner.cancel(body.get('transfer_id'), token=token)
                self._reply(200, {'status': 'ok'})
            else:
                self._reply(404, {'error': 'not_found'})
        except ProtocolError as exc:
            self._reply(exc.status, {'error': exc.code})


class TransferServer:
    def __init__(self, events, clock=time.monotonic):
        self.events, self.clock = events, clock
        self.session = PairingSession(clock)
        self.work_dir = None
        self.identity = None
        self._http = None
        self._thread = None
        self._maintenance = None
        self._stop = threading.Event()
        self._cancel = threading.Event()
        self._lock = threading.RLock()
        self._prepare_lock = threading.Lock()
        self._offer = None
        self._state = 'idle'
        self._send_socket = None

    @property
    def state(self):
        with self._lock: return self._state

    @property
    def connection_count(self):
        with self._http._clients_lock: return len(self._http._clients)

    def emit(self, kind, **fields):
        self.events.put({'kind': kind, **fields})

    def start(self, host):
        with self._lock:
            if self._http is not None or self._stop.is_set():
                raise ProtocolError(409, 'already_started')
            # Windows temporary directory is under the current user profile.
            self.work_dir = create_work_dir()
            try:
                self.identity = create_identity(host, self.work_dir)
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(self.identity.cert_path, self.identity.key_path)
                self._http = _HttpServer((host, 0), self, context)
            except BaseException:
                shutil.rmtree(self.work_dir)
                raise
            self.host, self.port = host, self._http.server_port
            self._thread = threading.Thread(target=self._http.serve_forever, kwargs={'poll_interval': .1}, name='beyt-https')
            self._thread.start()
            self._maintenance = threading.Thread(target=self._maintain, name='beyt-session')
            self._maintenance.start()
            return self.qr()

    def qr(self):
        return self.session.qr_payload(f'https://{self.host}:{self.port}', self.identity.cert_sha256)

    def _maintain(self):
        previous = self.qr()['pair_token']
        expired = False
        while not self._stop.wait(.25):
            if self.session.expired() and not expired:
                expired = True
                self._cancel.set()
                self._http.close_clients()
                with self._lock:
                    self._state = 'error'
                    self.emit('error', message='Bağlantı süresi doldu. Durdurup yeniden bağlanın.',
                              expired=True)
                    self._cleanup_offer()
            try:
                current = self.qr()['pair_token']
                if current != previous:
                    previous = current
                    self.emit('qr_changed')
            except ProtocolError:
                return

    def approve(self, request_id):
        self.session.approve(request_id)
        self.emit('paired')

    def reject(self, request_id):
        self.session.reject(request_id)
        self.emit('qr_changed')

    def _cleanup_offer(self, offer=None):
        target = offer if offer is not None else self._offer
        if target is not None:
            try: target.staged_path.unlink(missing_ok=True)
            except PermissionError: pass  # Windows: retry after the reader closes.

    def offer(self, source):
        with self._lock:
            self.session.check_approved()
            if self._state in ('preparing', 'ready', 'sending', 'awaiting_receipt'):
                raise ProtocolError(409, 'transfer_in_progress')
            self._cleanup_offer()
            self._offer = None
            self._cancel = threading.Event()
            self._state = 'preparing'
        self.emit('preparing')
        with self._prepare_lock:
            offer = None
            try:
                offer = prepare_offer(source, self.work_dir, self._cancel)
                with self._lock:
                    if self._cancel.is_set() or self._stop.is_set():
                        offer.staged_path.unlink(missing_ok=True)
                        raise ProtocolError(409, 'transfer_cancelled')
                    self.session.check_approved()
                    self._offer, self._state = offer, 'ready'
                self.emit('ready', **offer.metadata())
            except Exception:
                if offer is not None:
                    offer.staged_path.unlink(missing_ok=True)
                with self._lock: self._state = 'error'
                raise

    def current_offer(self):
        with self._lock:
            return self._offer.metadata() if self._offer and self._state == 'ready' else None

    def send_file(self, handler, transfer_id, token):
        with self._lock:
            if self._offer is None or self._offer.transfer_id != transfer_id:
                raise ProtocolError(404, 'file_not_found')
            if self._state != 'ready': raise ProtocolError(409, 'transfer_not_ready')
            offer = self._offer
            self._state = 'sending'
            self._send_socket = handler.connection
            cancel = self._cancel
        try:
            with offer.staged_path.open('rb') as stream:
                handler.send_response(200)
                handler.send_header('Content-Length', str(offer.size))
                handler.send_header('Content-Type', 'application/octet-stream')
                handler.send_header('Cache-Control', 'no-store')
                handler.send_header('Connection', 'close')
                handler.end_headers()
                count, last_event = 0, 0
                while True:
                    self.session.authorize(token)
                    if cancel.is_set() or self._stop.is_set(): raise OSError('cancelled')
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk: break
                    handler.wfile.write(chunk)
                    count += len(chunk)
                    now = time.monotonic()
                    if now - last_event >= .1:
                        self.emit('progress', bytes=count, total=offer.size)
                        last_event = now
            with self._lock:
                if self._offer is offer and not cancel.is_set():
                    self._state = 'awaiting_receipt'
                    self.emit('awaiting_receipt', bytes=offer.size, total=offer.size)
        except (OSError, ProtocolError):
            with self._lock:
                if self._offer is offer and self._state != 'cancelled':
                    self._state = 'error'
                    self.emit('error', message='Aktarım kesildi; dosyayı yeniden gönderin.')
        finally:
            with self._lock:
                if self._send_socket is handler.connection:
                    self._send_socket = None
                if cancel.is_set() or (self._offer is offer and self._state in ('error', 'cancelled')):
                    self._cleanup_offer(offer)

    def receipt(self, body, token):
        with self._lock:
            # The body may arrive across the expiry boundary; authorize at commit.
            self.session.authorize(token)
            if not self._offer or body.get('transfer_id') != self._offer.transfer_id:
                raise ProtocolError(404, 'file_not_found')
            if (type(body.get('size')) is not int or body['size'] != self._offer.size
                    or body.get('sha256') != self._offer.sha256):
                raise ProtocolError(400, 'receipt_mismatch')
            if self._state not in ('awaiting_receipt', 'completed'):
                raise ProtocolError(409, 'receipt_not_expected')
            if self._state != 'completed':
                self._state = 'completed'
                self._cleanup_offer()
                self.emit('completed')

    def cancel(self, transfer_id, *, token=None):
        with self._lock:
            if token is not None:
                self.session.authorize(token)
            if not self._offer or transfer_id != self._offer.transfer_id:
                raise ProtocolError(404, 'file_not_found')
            if self._state == 'completed':
                return
            self._cancel.set()
            if self._send_socket is not None:
                try: self._send_socket.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            self._state = 'cancelled'
            self._cleanup_offer()
            self.emit('cancelled')

    def stop(self):
        with self._lock:
            if self._stop.is_set(): return
            self._stop.set()
            self._cancel.set()
        self.session.stop()
        if self._http:
            self._http.shutdown()
            self._http.close_clients()
            self._http.server_close()
        for worker in (self._thread, self._maintenance):
            if worker and worker is not threading.current_thread(): worker.join()
        with self._prepare_lock:
            if self.work_dir is not None and self.work_dir.exists():
                shutil.rmtree(self.work_dir)
        self.emit('stopped')
