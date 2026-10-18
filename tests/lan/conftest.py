import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def modules():
    import importlib.util
    assert importlib.util.find_spec('lan_transfer'), 'LAN protocol is not implemented yet'
    from lan_transfer.protocol import ProtocolError, validate_qr
    from lan_transfer.session import PairingSession
    return PairingSession, ProtocolError, validate_qr


@pytest.fixture
def session(modules, clock):
    return modules[0](clock=clock)


@pytest.fixture
def qr(session):
    return session.qr_payload('https://192.168.1.20:48123', 'a' * 64)


def pair_request(qr, name='Test phone'):
    return {key: qr[key] for key in ('session_id', 'pair_token')} | {'device_name': name}
