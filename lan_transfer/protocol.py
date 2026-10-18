"""The versioned wire contract shared with the Android client."""
import base64
from datetime import datetime, timezone
import ipaddress
import json
import re
from urllib.parse import urlsplit

MAX_FILE_SIZE = 1024 ** 3
CHUNK_SIZE = 128 * 1024
PRIVATE_NETWORKS = tuple(ipaddress.IPv4Network(net) for net in
                         ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


class ProtocolError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status, self.code = status, code


def private_ipv4(host):
    try:
        address = ipaddress.IPv4Address(host)
        return any(address in net for net in PRIVATE_NETWORKS)
    except ipaddress.AddressValueError:
        return False


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def decode_json(payload, max_bytes=4096):
    if not isinstance(payload, str) or len(payload.encode('utf-8')) > max_bytes:
        raise ValueError('Invalid JSON size')
    try:
        value = json.loads(payload, object_pairs_hook=_unique_object)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('Invalid JSON') from exc
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def validate_qr(payload):
    data = decode_json(payload, 2048)
    fields = {'v', 'origin', 'session_id', 'cert_sha256', 'pair_token', 'expires_at'}
    if set(data) != fields or type(data['v']) is not int or data['v'] != 1:
        raise ValueError('Unsupported QR format')
    if not all(isinstance(data[field], str) for field in fields - {'v'}):
        raise ValueError('Invalid QR fields')
    origin = data['origin']
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not private_ipv4(parsed.hostname)
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment
            or not parsed.port or not 1 <= parsed.port <= 65535
            or origin != f'https://{parsed.hostname}:{parsed.port}'):
        raise ValueError('Expected a private IPv4 HTTPS origin')
    if not re.fullmatch('[0-9a-f]{32}', data['session_id']):
        raise ValueError('Invalid session ID')
    if not re.fullmatch('[0-9a-f]{64}', data['cert_sha256']):
        raise ValueError('Invalid certificate fingerprint')
    token = data['pair_token']
    if not re.fullmatch('[A-Za-z0-9_-]{43}', token):
        raise ValueError('Invalid pairing token')
    raw = base64.urlsafe_b64decode(token + '=')
    if len(raw) != 32 or base64.urlsafe_b64encode(raw).decode().rstrip('=') != token:
        raise ValueError('Invalid pairing token encoding')
    try:
        expiry = datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00'))
        if not data['expires_at'].endswith('Z') or expiry <= datetime.now(timezone.utc):
            raise ValueError('Expired QR')
    except (ValueError, TypeError) as exc:
        raise ValueError('Expired or invalid QR timestamp') from exc
    return data
