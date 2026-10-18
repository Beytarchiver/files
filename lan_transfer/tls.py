"""Ephemeral TLS identities; no changes to the operating system trust store."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


@dataclass(frozen=True)
class TlsIdentity:
    cert_path: Path
    key_path: Path
    cert_sha256: str


def create_identity(host, directory):
    address = ipaddress.IPv4Address(host)
    directory = Path(directory)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Beytarchiver LAN')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(address)]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = directory / 'server.pem', directory / 'server-key.pem'
    for path, payload in (
        (key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption())),
        (cert_path, cert.public_bytes(serialization.Encoding.PEM)),
    ):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
    return TlsIdentity(cert_path, key_path, cert.fingerprint(hashes.SHA256()).hex())
