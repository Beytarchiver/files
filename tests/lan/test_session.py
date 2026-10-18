import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import pair_request


def test_shared_qr_fixtures(modules):
    fixtures = json.loads((Path(__file__).parents[1] / 'protocol/lan-v1-fixtures.json').read_text())
    validate = modules[2]
    for example in fixtures:
        if example['valid']:
            assert validate(example['payload']) == json.loads(example['payload'])
        else:
            with pytest.raises(ValueError):
                validate(example['payload'])


@pytest.mark.parametrize('origin', [
    'http://192.168.1.20:1234', 'https://user@192.168.1.20:1234',
    'https://192.168.1.20:1234?key=x', 'https://192.168.1.20:1234/',
    'https://192.168.1.20:1234#x', 'https://8.8.8.8:443',
    'https://127.0.0.1:1234', 'https://169.254.1.1:1234',
    'https://100.64.0.1:1234', 'https://[::1]:1234', 'https://my-pc:1234',
    'https://192.168.1.20', 'https://192.168.1.20:0',
])
def test_qr_rejects_bad_origin(modules, qr, origin):
    with pytest.raises(ValueError): modules[2](json.dumps(qr | {'origin': origin}))


@pytest.mark.parametrize('change', [{'v': True}, {'v': 2}, {'cert_sha256': 'bad'},
                                  {'pair_token': 'short'}, {'expires_at': '2000-01-01T00:00:00Z'},
                                  {'session_id': ''}])
def test_qr_rejects_invalid_fields(modules, qr, change):
    with pytest.raises(ValueError): modules[2](json.dumps(qr | change))


def test_qr_rejects_large_or_duplicate_json(modules, qr):
    with pytest.raises(ValueError): modules[2](' ' * 2049)
    with pytest.raises(ValueError): modules[2](json.dumps(qr)[:-1] + ',"v":1}')


def test_approval_required(modules, session, qr):
    error = modules[1]
    request = session.request_pair(pair_request(qr), '192.168.1.2')
    assert len(request['code']) == 6 and request['code'].isdigit()
    assert request['poll_token'] != qr['pair_token']
    assert session.pair_status(request['request_id'], request['poll_token']) == {'status': 'pending'}
    with pytest.raises(error) as e: session.authorize(request['poll_token'])
    assert e.value.status == 401
    session.approve(request['request_id'])
    status = session.pair_status(request['request_id'], request['poll_token'])
    assert status['status'] == 'approved'
    assert status['access_token'] not in (request['poll_token'], qr['pair_token'])
    session.authorize(status['access_token'])
    with pytest.raises(error): session.authorize('incorrect')


def test_expired_qr(modules, session, qr, clock):
    clock.advance(120)
    with pytest.raises(modules[1]) as e: session.request_pair(pair_request(qr), '192.168.1.2')
    assert e.value.status == 410
    assert session.qr_payload(qr['origin'], qr['cert_sha256'])['pair_token'] != qr['pair_token']


def test_expired_approval_rotates_token(modules, session, qr, clock):
    request = session.request_pair(pair_request(qr), '192.168.1.2')
    clock.advance(60)
    with pytest.raises(modules[1]) as e: session.approve(request['request_id'])
    assert e.value.status == 410
    assert session.qr_payload(qr['origin'], qr['cert_sha256'])['pair_token'] != qr['pair_token']


def test_rejection_and_replay(modules, session, qr):
    request = session.request_pair(pair_request(qr), '192.168.1.2')
    with pytest.raises(modules[1]) as e: session.request_pair(pair_request(qr), '192.168.1.3')
    assert e.value.status == 409
    session.reject(request['request_id'])
    assert session.pair_status(request['request_id'], request['poll_token']) == {'status': 'rejected'}
    with pytest.raises(modules[1]): session.request_pair(pair_request(qr), '192.168.1.2')


def test_session_expiry_and_stop(modules, session, qr, clock):
    request = session.request_pair(pair_request(qr), '192.168.1.2')
    session.approve(request['request_id'])
    token = session.pair_status(request['request_id'], request['poll_token'])['access_token']
    clock.advance(900)
    with pytest.raises(modules[1]) as e: session.authorize(token)
    assert e.value.status == 410
    session.stop()
    with pytest.raises(modules[1]): session.authorize(token)


def test_pair_rate_limit(modules, session, qr, clock):
    for _ in range(10):
        with pytest.raises(modules[1]) as e:
            session.request_pair(pair_request(qr) | {'pair_token': 'bad'}, '192.168.1.2')
        assert e.value.status == 401
    with pytest.raises(modules[1]) as e: session.request_pair(pair_request(qr), '192.168.1.2')
    assert e.value.status == 429
    clock.advance(60)
    assert session.request_pair(pair_request(qr), '192.168.1.2')['request_id']


def test_poll_rate_limit(modules, session, qr):
    request = session.request_pair(pair_request(qr), '192.168.1.2')
    for _ in range(2): session.pair_status(request['request_id'], request['poll_token'])
    with pytest.raises(modules[1]) as e: session.pair_status(request['request_id'], request['poll_token'])
    assert e.value.status == 429


def test_only_one_concurrent_pairing(modules, session, qr):
    def attempt(i):
        try: return session.request_pair(pair_request(qr), f'192.168.1.{i}')
        except modules[1] as exc: return exc.status
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(2, 6)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count(409) == 3


@pytest.mark.parametrize('name', ['x' * 81, 'phone\nforged', 123])
def test_device_name_is_untrusted(modules, session, qr, name):
    with pytest.raises(modules[1]) as e: session.request_pair(pair_request(qr, name), '192.168.1.2')
    assert e.value.status == 400
