"""Thread-safe short-lived pairing; approval is a local-only operation."""
from collections import deque
from datetime import datetime, timedelta, timezone
import hmac
import secrets
import threading
import time

from .protocol import ProtocolError


def _matches(expected, supplied):
    return isinstance(supplied, str) and hmac.compare_digest(
        expected.encode('utf-8'), supplied.encode('utf-8'))


class PairingSession:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()
        self.session_id = secrets.token_hex(16)
        self._stopped = False
        self._requests = {}
        self._pending = None
        self._access_token = None
        self._access_deadline = None
        self._rate = {}
        self._poll_times = deque()
        self._rotate()

    def _rotate(self):
        self._pair_token = secrets.token_urlsafe(32)
        self._qr_deadline = self.clock() + 120
        self._expires_at = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat().replace('+00:00', 'Z')

    def _check_running(self):
        if self._stopped:
            raise ProtocolError(410, 'session_stopped')

    def _expire_pending(self):
        if self._pending and self.clock() >= self._pending['deadline']:
            self._pending['status'] = 'rejected'
            self._pending = None
            self._rotate()

    def qr_payload(self, origin, cert_sha256):
        with self.lock:
            self._check_running()
            self._expire_pending()
            if self.clock() >= self._qr_deadline and not self._pending and not self._access_token:
                self._rotate()
            return {'v': 1, 'origin': origin, 'session_id': self.session_id,
                    'cert_sha256': cert_sha256, 'pair_token': self._pair_token,
                    'expires_at': self._expires_at}

    def _limit_pair(self, ip):
        now = self.clock()
        self._rate = {key: value for key, value in self._rate.items() if now - value[0] < 60}
        if ip not in self._rate:
            if len(self._rate) >= 1024:
                raise ProtocolError(429, 'too_many_clients')
            self._rate[ip] = [now, 0]
        window = self._rate[ip]
        window[1] += 1
        if window[1] > 10:
            raise ProtocolError(429, 'pair_rate_limited')

    def request_pair(self, payload, peer_ip):
        with self.lock:
            self._check_running()
            self._limit_pair(peer_ip)
            self._expire_pending()
            if not isinstance(payload, dict):
                raise ProtocolError(400, 'invalid_pair_request')
            if not (_matches(self.session_id, payload.get('session_id'))
                    and _matches(self._pair_token, payload.get('pair_token'))):
                raise ProtocolError(401, 'invalid_pair_token')
            if self._pending or self._access_token:
                raise ProtocolError(409, 'pairing_in_progress')
            if self.clock() >= self._qr_deadline:
                raise ProtocolError(410, 'qr_expired')
            name = payload.get('device_name', '')
            if not isinstance(name, str) or len(name) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in name):
                raise ProtocolError(400, 'invalid_device_name')
            request_id = secrets.token_hex(16)
            request = {'request_id': request_id, 'poll_token': secrets.token_urlsafe(32),
                       'code': f'{secrets.randbelow(1000000):06}', 'device_name': name,
                       'deadline': self.clock() + 60, 'status': 'pending'}
            # Only retain the latest result; old IDs cannot accumulate indefinitely.
            self._requests = {request_id: request}
            self._pending = request
            self._poll_times.clear()
            return {key: request[key] for key in ('request_id', 'poll_token', 'code')}

    def pending(self):
        with self.lock:
            self._expire_pending()
            if not self._pending:
                return None
            return {key: self._pending[key] for key in ('request_id', 'code', 'device_name')}

    def approve(self, request_id):
        with self.lock:
            self._check_running()
            self._expire_pending()
            if not self._pending or self._pending['request_id'] != request_id:
                raise ProtocolError(410, 'request_expired')
            self._pending['status'] = 'approved'
            self._pending = None
            self._access_token = secrets.token_urlsafe(32)
            self._access_deadline = self.clock() + 900

    def reject(self, request_id):
        with self.lock:
            self._check_running()
            if not self._pending or self._pending['request_id'] != request_id:
                raise ProtocolError(404, 'request_not_found')
            self._pending['status'] = 'rejected'
            self._pending = None
            self._rotate()

    def pair_status(self, request_id, poll_token):
        with self.lock:
            self._check_running()
            self._expire_pending()
            request = self._requests.get(request_id)
            if not request:
                raise ProtocolError(404, 'request_not_found')
            if not _matches(request['poll_token'], poll_token):
                raise ProtocolError(401, 'invalid_poll_token')
            now = self.clock()
            while self._poll_times and now - self._poll_times[0] >= 1:
                self._poll_times.popleft()
            if len(self._poll_times) >= 2:
                raise ProtocolError(429, 'poll_rate_limited')
            self._poll_times.append(now)
            if request['status'] == 'approved':
                self.authorize(self._access_token)
                return {'status': 'approved', 'access_token': self._access_token}
            return {'status': request['status']}

    def authorize(self, access_token):
        with self.lock:
            self._check_running()
            if not self._access_token or not _matches(self._access_token, access_token):
                raise ProtocolError(401, 'invalid_access_token')
            if self.clock() >= self._access_deadline:
                raise ProtocolError(410, 'session_expired')

    def check_approved(self):
        """Local controller only; HTTP callers must supply their bearer token."""
        with self.lock:
            self.authorize(self._access_token)

    def expired(self):
        with self.lock:
            return self._access_deadline is not None and self.clock() >= self._access_deadline

    def stop(self):
        with self.lock:
            self._stopped = True
            self._access_token = None
            self._pair_token = ''
            self._requests.clear()
            self._pending = None
