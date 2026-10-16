import ctypes
import base64
import gzip
import hashlib
import ntpath
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import psutil
import json
import tarfile
from datetime import datetime
from queue import Empty, Queue

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

import customtkinter as ctk
import py7zr
import pyzipper
from tkinter import filedialog, ttk, messagebox, simpledialog
from tkinterdnd2 import DND_FILES, TkinterDnD
from lan_transfer.panel import TransferPanel

# --- Windows Özel Kütüphaneler ---
try:
    import winreg
    import winsound
except ImportError:
    winreg = None
    winsound = None

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False

# --- Sabitler ve Versiyon ---
CURRENT_VERSION = "4.0"
VERSION_FILE = os.path.expanduser("~/.beytarchiver_version")
SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004

# --- Yardımcı Fonksiyonlar ---
def beep(freq, dur):
    if winsound:
        try: winsound.Beep(freq, dur)
        except: pass

def send_notification(title, message):
    if HAS_PLYER:
        try: notification.notify(title=title, message=message, app_name="Beytarchiver", timeout=5)
        except: pass

def get_path_size(path):
    if os.path.isfile(path): return os.path.getsize(path)
    total_size = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try: total_size += os.path.getsize(os.path.join(dirpath, f))
            except: pass
    return total_size

def format_size(bytes_val):
    if not bytes_val: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024: return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} PB"

def open_in_explorer(path):
    if not os.path.exists(path): return
    if os.path.isfile(path): path = os.path.dirname(path)
    if sys.platform == "win32": os.startfile(path)
    elif sys.platform == "darwin": subprocess.Popen(["open", path])
    else: subprocess.Popen(["xdg-open", path])

def unique_arcname(arc, used):
    base, ext = os.path.splitext(arc)
    cand, n = arc, 1
    while cand in used:
        cand = f"{base} ({n}){ext}"
        n += 1
    used.add(cand)
    return cand


class PasswordVault:
    """Authenticated encrypted storage. The master password is never persisted."""

    AAD = b'beytarchiver-password-vault-v1'

    def __init__(self, path):
        self.path = Path(path)
        self.lock()

    def lock(self):
        self._key = None
        self._salt = None
        self.data = {}

    @property
    def unlocked(self):
        return self._key is not None

    @staticmethod
    def _derive(password, salt):
        return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode('utf-8'))

    def create(self, password):
        if self.path.exists():
            raise FileExistsError('Kasa zaten var; mevcut ana parolayla açın.')
        if len(password) < 12:
            raise ValueError('Ana parola en az 12 karakter olmalı.')
        self._salt = os.urandom(16)
        self._key = self._derive(password, self._salt)
        try:
            self.save({})
        except Exception:
            self.lock()
            raise

    def unlock(self, password):
        self.lock()
        try:
            if self.path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError('Kasa dosyası çok büyük.')
            document = json.loads(self.path.read_text(encoding='utf-8'))
            if document['version'] != 1:
                raise ValueError('Desteklenmeyen kasa sürümü.')
            salt = base64.b64decode(document['salt'], validate=True)
            nonce = base64.b64decode(document['nonce'], validate=True)
            if len(salt) != 16 or len(nonce) != 12:
                raise ValueError('Geçersiz kasa biçimi.')
            key = self._derive(password, salt)
            payload = AESGCM(key).decrypt(
                nonce, base64.b64decode(document['ciphertext'], validate=True), self.AAD)
            data = json.loads(payload)
            self._validate(data)
        except (InvalidTag, ValueError, KeyError, TypeError) as exc:
            raise ValueError('Ana parola yanlış veya kasa dosyası bozuk.') from exc
        self._key, self._salt, self.data = key, salt, data

    @staticmethod
    def _validate(data):
        if not isinstance(data, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise ValueError('Geçersiz şifre kayıtları.')

    def save(self, data):
        if not self.unlocked:
            raise ValueError('Önce kasanın kilidini açın.')
        self._validate(data)
        nonce = os.urandom(12)
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        ciphertext = AESGCM(self._key).encrypt(nonce, payload, self.AAD)
        document = {'version': 1, 'salt': base64.b64encode(self._salt).decode('ascii'),
                    'nonce': base64.b64encode(nonce).decode('ascii'),
                    'ciphertext': base64.b64encode(ciphertext).decode('ascii')}
        # mkstemp uses restrictive permissions; replace only after a complete write.
        fd, name = tempfile.mkstemp(prefix='.beyt-vault-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(document, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        self.data = dict(data)


def safe_extract_archive(archive_path, output_dir, password='', *,
                         max_total_size=2 * 1024**3, max_files=10000):
    """Extract only regular files/directories into a new destination, or leave none."""
    archive_path, output_dir = Path(archive_path), Path(output_dir)
    if os.path.lexists(output_dir):
        raise FileExistsError('Hedef zaten var; farklı veya boşta bir hedef seçin.')
    if max_total_size < 0 or max_files < 1:
        raise ValueError('Geçersiz çıkartma sınırları.')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
    reserved.update(f'{prefix}{i}' for prefix in ('COM', 'LPT') for i in range(1, 10))
    seen, count, declared, actual = {}, 0, 0, 0

    with tempfile.TemporaryDirectory(prefix='.beyt-extract-', dir=output_dir.parent) as temp:
        stage = Path(temp) / 'content'
        stage.mkdir()

        def target(name, size, is_dir):
            nonlocal count, declared
            count += 1
            declared += size
            if count > max_files or size < 0 or declared > max_total_size:
                raise ValueError('Arşiv dosya sayısı veya açılmış boyut sınırını aşıyor.')
            normalized = name.replace('\\', '/')
            parts = normalized.split('/')
            if (not normalized or normalized.startswith('/') or ntpath.splitdrive(name)[0]
                    or '..' in parts or any(ord(c) < 32 for c in name)):
                raise ValueError(f'Güvensiz arşiv yolu: {name!r}')
            parts = [part for part in parts if part not in ('', '.')]
            for part in parts:
                if (part.endswith((' ', '.')) or any(c in part for c in ':<>"|?*')
                        or part.split('.')[0].upper() in reserved):
                    raise ValueError(f'Güvensiz dosya adı: {name!r}')
            if not parts:
                if is_dir:
                    return stage
                raise ValueError('Boş dosya adı.')
            key = '/'.join(parts).casefold()
            if key in seen:
                raise ValueError(f'Çakışan arşiv yolu: {name!r}')
            for i in range(1, len(parts)):
                if seen.get('/'.join(parts[:i]).casefold()) is False:
                    raise ValueError('Dosya ve klasör yolları çakışıyor.')
            if not is_dir and any(k.startswith(key + '/') for k in seen):
                raise ValueError('Dosya ve klasör yolları çakışıyor.')
            seen[key] = is_dir
            return stage.joinpath(*parts)

        def copy_stream(source, destination):
            nonlocal actual
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as sink:
                while True:
                    chunk = source.read(min(1024 * 1024, max_total_size - actual + 1))
                    if not chunk:
                        break
                    actual += len(chunk)
                    if actual > max_total_size:
                        raise ValueError('Açılmış veri boyut sınırını aşıyor.')
                    sink.write(chunk)

        ext = archive_path.suffix.lower()
        if ext in ('.zip', '.beyt'):
            with pyzipper.AESZipFile(archive_path, 'r') as archive:
                if password:
                    archive.setpassword(password.encode('utf-8'))
                entries = []
                for info in archive.infolist():
                    kind = stat.S_IFMT(info.external_attr >> 16)
                    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                        raise ValueError('Arşivde bağlantı veya özel dosya var.')
                    entries.append((info, target(info.filename, info.file_size, info.is_dir())))
                for info, dest in entries:
                    if info.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        with archive.open(info) as source:
                            copy_stream(source, dest)
        elif ext == '.7z':
            # py7zr >= 1.1.4 enforces the size limit during decompression too.
            with py7zr.SevenZipFile(archive_path, 'r', password=password or None,
                                   max_extract_size=max_total_size) as archive:
                for info in archive.list():
                    if info.is_symlink or not (info.is_file or info.is_directory):
                        raise ValueError('Arşivde bağlantı veya özel dosya var.')
                    target(info.filename, info.uncompressed, info.is_directory)
                archive.extractall(path=stage)
        elif ext in ('.tar', '.gz', '.tgz'):
            # A .gz file can hold a tar archive or a single compressed stream.
            try:
                archive = tarfile.open(archive_path, 'r:*')
            except tarfile.ReadError:
                if ext != '.gz':
                    raise
                dest = target(archive_path.stem, 0, False)
                with gzip.open(archive_path, 'rb') as source:
                    copy_stream(source, dest)
            else:
                with archive:
                    entries = []
                    for info in archive:
                        if not (info.isfile() or info.isdir()):
                            raise ValueError('Arşivde bağlantı veya özel dosya var.')
                        entries.append((info, target(info.name, info.size, info.isdir())))
                    for info, dest in entries:
                        if info.isdir():
                            dest.mkdir(parents=True, exist_ok=True)
                        else:
                            with archive.extractfile(info) as source:
                                copy_stream(source, dest)
        else:
            raise ValueError('Desteklenmeyen arşiv biçimi.')
        if os.path.lexists(output_dir):
            raise FileExistsError('Hedef işlem sırasında oluşturuldu; üzerine yazılmadı.')
        stage.rename(output_dir)
    return output_dir


def overwrite_and_delete(path):
    """Best-effort file overwrite, not a guarantee of SSD/backup erasure."""
    path = Path(path)
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
        raise ValueError('Yalnızca bağlantısız, normal dosyalar silinebilir.')
    fd = os.open(path, os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'r+b') as stream:
        current = os.fstat(stream.fileno())
        if (current.st_dev, current.st_ino) != (initial.st_dev, initial.st_ino) or current.st_nlink != 1:
            raise ValueError('Dosya değişti; işlem iptal edildi.')
        for pattern in (b'\x00', b'\xff', None):
            stream.seek(0)
            remaining = initial.st_size
            while remaining:
                length = min(1024 * 1024, remaining)
                stream.write(pattern * length if pattern else os.urandom(length))
                remaining -= length
            stream.flush()
            os.fsync(stream.fileno())
    current = path.lstat()
    if (current.st_dev, current.st_ino) != (initial.st_dev, initial.st_ino):
        raise ValueError('Dosya yolu değişti; silme iptal edildi.')
    path.unlink()

# --- Zengin Renk Paletleri ---
COLOR_THEMES = {
    "Catppuccin (Varsayılan)": {
        "dark": {"bg": "#181825", "card": "#1E1E2E", "text": "#CDD6F4"},
        "light": {"bg": "#EFF1F5", "card": "#E6E9EF", "text": "#4C4F69"}
    },
    "Emerald Matrix (Yeşil)": {
        "dark": {"bg": "#0D1117", "card": "#161B22", "text": "#E6EDF3"},
        "light": {"bg": "#E6F4EA", "card": "#CEEAD6", "text": "#137333"}
    },
    "Cyberpunk Neon (Mor/Pembe)": {
        "dark": {"bg": "#10002B", "card": "#240046", "text": "#F72585"},
        "light": {"bg": "#F3E8FF", "card": "#E9D5FF", "text": "#5B21B6"}
    },
    "Sunset Orange (Sıcak)": {
        "dark": {"bg": "#1A0C00", "card": "#2B1704", "text": "#FEF3C7"},
        "light": {"bg": "#FFF7ED", "card": "#FFEDD5", "text": "#9A3412"}
    },
    "Ocean Blue (Mavi)": {
        "dark": {"bg": "#0F172A", "card": "#1E293B", "text": "#F1F5F9"},
        "light": {"bg": "#F0F9FF", "card": "#E0F2FE", "text": "#0369A1"}
    },
    "Cherry Blossom (Pembe)": {
        "dark": {"bg": "#1A0915", "card": "#2A1224", "text": "#FCE7F3"},
        "light": {"bg": "#FDF2F8", "card": "#FCE7F3", "text": "#9D174D"}
    },
    "Crimson Red (Kırmızı)": {
        "dark": {"bg": "#180505", "card": "#2B0B0B", "text": "#FEE2E2"},
        "light": {"bg": "#FEF2F2", "card": "#FEE2E2", "text": "#991B1B"}
    },
    "Midnight Purple (Gece Moru)": {
        "dark": {"bg": "#0F0C1B", "card": "#1B1730", "text": "#EDE9FE"},
        "light": {"bg": "#F5F3FF", "card": "#EDE9FE", "text": "#5B21B6"}
    },
    "Mocha Coffee (Kahve)": {
        "dark": {"bg": "#1C1917", "card": "#292524", "text": "#FEF3C7"},
        "light": {"bg": "#FAFAF9", "card": "#F5F5F4", "text": "#78350F"}
    },
    "Nordic Ice (Buz Mavisi)": {
        "dark": {"bg": "#0B132B", "card": "#1C2541", "text": "#E0FBFC"},
        "light": {"bg": "#F0FDF4", "card": "#CCFBF1", "text": "#0F766E"}
    },
    "Gold / Amber (Altın)": {
        "dark": {"bg": "#121212", "card": "#1E1E1E", "text": "#FEF08A"},
        "light": {"bg": "#FEFCE8", "card": "#FEF9C3", "text": "#854D0E"}
    }
}

LANGUAGES = {
    "TR": {
        "transfer": "📱 Telefonla Aktar",
        "compress": "📦 Sıkıştırma", "extract": "📂 Çıkartma", "vault": "🔐 Gizli Kasa",
        "ram": "⚡ RAM Temizle", "updater": "🔄 Güncelleyici", "antivirus": "🛡️ Antivirüs",
        "cleaner": "🧹 Temizleyici", "analyzer": "📊 Disk Analizi", "duplicates": "👥 Çift Dosya",
        "shredder": "🔥 Güvenli Sil", "organizer": "📁 Düzenleyici", "startup": "🚀 Başlangıç",
        "hash": "🧮 Hash", "settings": "⚙️ Ayarlar", "monitor": "📈 İzleyici", "passwords": "🔑 Şifreler",
        "drop_compress": "Sıkıştırılacak dosya ve klasörleri buraya sürükleyin",
        "drop_extract": "Çıkartılacak arşivi (.zip, .7z, .tar, .beyt) buraya sürükleyin",
        "start_compress": "🚀 Sıkıştırmayı Başlat", "start_extract": "📂 Tümünü Çıkart",
        "password": "Şifre (Opsiyonel)", "password_req": "Şifre (Gerekliyse)",
        "theme": "Görünüm Modu:", "color_palette": "Renk Teması / Palette:", "language": "Dil / Language:",
        "junk_sub": "Temizlenebilir Sistem Çöpü", "scan": "🔍 Tara", "clean": "🧹 Temizle",
        "av_title": f"🛡️ Beytarchiver Güvenlik Motoru v{CURRENT_VERSION} Ultimate", "av_sub": "Kurumsal İmza & Sezgisel Derin Analiz",
        "av_select": "🔍 Taranacak Dosya Seç", "no_file": "Dosya Seçilmedi",
        "update_title": f"🚀 Beytarchiver v{CURRENT_VERSION} Pro Ultimate Raporu",
        "update_notes": "📌 SÜRÜM GELİŞİM GEÇMİŞİ:\n\n✨ v4.0:\n• 📱 TELEFONLA AKTAR: Aynı yerel ağda Android telefona dosya gönderme.\n• 🔗 QR ile eşleştirme, altı haneli kod onayı ve TLS bağlantısı.\n• ✅ SHA-256 doğrulaması ve telefondan kayıt onayı.\n• 🧪 Android istemcisi alpha aşamasında; aktarım sırasında açık tutulmalıdır.\n\n✨ v3.7 (Ultimate Edition):\n• 📈 CANLI İZLEYİCİ: CPU ve RAM kullanımı anlık takibi eklendi.\n• 🔑 ŞİFRE YÖNETİCİSİ: Ana parolalı AES-256-GCM kasa ve otomatik kilitleme.\n• 🛠️ AV OPTİMİZASYONU: False-Positive (Yanlış Alarm) uyarıları azaltıldı.\n• 🧹 REGISTRY CLEANER: Kayıt defteri optimizasyonu sağlandı.\n• 🛡️ Dosya Silme: Onaylı, parçalı üç geçişli üzerine yazma; SSD silme garantisi yoktur.\n• 🛠️ UI Stability: UI Queue (Kuyruk) mimarisi ile Thread-Safe yapıldı.",
        "btn_close_update": "Harika, Başlayalım! 🚀"
    },
    "EN": {
        "transfer": "📱 Phone Transfer",
        "compress": "📦 Compress", "extract": "📂 Extract", "vault": "🔐 Vault",
        "ram": "⚡ RAM Cleaner", "updater": "🔄 Updater", "antivirus": "🛡️ Antivirus",
        "cleaner": "🧹 Cleaner", "analyzer": "📊 Disk Analyzer", "duplicates": "👥 Duplicates",
        "shredder": "🔥 Shredder", "organizer": "📁 Organizer", "startup": "🚀 Startup",
        "hash": "🧮 Hash", "settings": "⚙️ Settings", "monitor": "📈 Monitor", "passwords": "🔑 Passwords",
        "drop_compress": "Drag files and folders to compress here",
        "drop_extract": "Drag archive (.zip, .7z, .tar, .beyt) here",
        "start_compress": "🚀 Start Compression", "start_extract": "📂 Extract All",
        "password": "Password (Optional)", "password_req": "Password (If Required)",
        "theme": "Appearance Mode:", "color_palette": "Color Theme / Palette:", "language": "Language / Dil:",
        "junk_sub": "Cleanable System Junk", "scan": "🔍 Scan", "clean": "🧹 Clean",
        "av_title": f"🛡️ Beytarchiver Security Engine v{CURRENT_VERSION} Ultimate", "av_sub": "Enterprise Signature & Heuristic Analysis",
        "av_select": "🔍 Select File to Scan", "no_file": "No File Selected",
        "update_title": f"🚀 Beytarchiver v{CURRENT_VERSION} Pro Ultimate Changelog",
        "update_notes": "📌 VERSION CHANGELOG:\n\n✨ v4.0:\n• 📱 PHONE TRANSFER: Send files to Android on the same local network.\n• 🔗 QR pairing, six-digit code approval and TLS connection.\n• ✅ SHA-256 verification and saved-file acknowledgement.\n• 🧪 Android client is in alpha; keep it open during transfers.\n\n✨ v3.7 (Ultimate Edition):\n• 📈 LIVE MONITOR: Real-time CPU and RAM tracking.\n• 🔑 PASSWORD MANAGER: Master-password protected AES-256-GCM vault and automatic locking.\n• 🛠️ AV OPTIMIZATION: Reduced false-positive warnings.\n• 🧹 REGISTRY CLEANER: Added registry optimization module.\n• 🛡️ File Removal: Confirmed, chunked three-pass overwrite; no SSD erasure guarantee.\n• 🛠️ UI Stability: Full Thread-Safe UI Queue implemented.",
        "btn_close_update": "Awesome, Let's Go! 🚀"
    }
}

# --- Güvenlik Motoru ---
class BeytNativeAntivirus:
    def __init__(self):
        self.malware_signatures = {
            # EICAR is a harmless antivirus test file, not a real malware database.
            "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f": "EICAR.Test.File"
        }
        self.high_risk_extensions = [".exe", ".vbs", ".bat", ".cmd", ".ps1", ".scr", ".pif", ".hta"]

    def calculate_file_hash(self, file_path):
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except: return None

    def scan_file(self, file_path):
        results = []
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()

        if filename.count(".") > 1 and ext in self.high_risk_extensions:
            results.append(f"⚠️ SEZGİSEL UYARI: Gizlenmiş çift uzantılı dosya! ({filename})")
        if ext in self.high_risk_extensions:
            results.append(f"ℹ️ SEZGİSEL BİLGİ: Potansiyel betik/uygulama ({ext})")

        file_hash = self.calculate_file_hash(file_path)
        if file_hash is None:
            results.append("❌ Dosya okunamadı; tarama tamamlanamadı.")
        if file_hash and file_hash in self.malware_signatures:
            results.append(f"⚠️ TEST İMZASI BULUNDU: {self.malware_signatures[file_hash]}")

        return results, file_hash

# --- Ana Uygulama ---
class BeytarchiverV37App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"Beytarchiver v{CURRENT_VERSION} Pro Enterprise - Ultimate Edition")
        self.geometry("1300x900")
        self.minsize(1100, 800)

        if os.path.exists("logo.ico"):
            try: self.iconbitmap("logo.ico")
            except: pass

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.current_lang = "TR"
        self.active_palette_name = "Catppuccin (Varsayılan)"
        self.av_engine = BeytNativeAntivirus()

        # Thread-Safe UI Queue (Parametre çökmelerini kesin engelleyen yapı)
        self.ui_queue = Queue()
        self._closing = False
        self._queue_after = None
        self._password_after = None
        self._reveal_after = None
        self._password_sites = {}
        self.protocol('WM_DELETE_WINDOW', self.close_app)
        self.process_ui_queue()

        self.files_to_archive = []
        self.archive_to_extract = ""
        self.junk_files = []
        self.password_vault = PasswordVault(Path.home() / '.beyt_passwords.enc')
        self.legacy_pass_file = Path.home() / '.beyt_passwords.json'
        self._extracting = False
        self._compressing = False
        self._cleaning = False

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.build_toolbar()
        self.build_navbar()

        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        self.build_all_views()

        self.status_bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#11111B")
        self.status_bar.grid(row=3, column=0, sticky="ew")

        self.lbl_status = ctk.CTkLabel(self.status_bar, text="Sistem Hazır", font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        self.lbl_status.pack(side="left", padx=10)

        self.lbl_stats = ctk.CTkLabel(self.status_bar, text=f"Beytarchiver v{CURRENT_VERSION} Ultimate Edition Active", font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        self.lbl_stats.pack(side="right", padx=10)

        self.show_view("compress")
        self.after(500, self.check_first_launch_update)
        
        # Başlangıçta temayı uygula
        self.apply_color_palette(self.active_palette_name)

    # ==========================================
    # KUSURSUZ THREAD-SAFE QUEUE (Çökmeleri Engelleyen Kısım)
    # ==========================================
    def process_ui_queue(self):
        if self._closing:
            return
        # Limit each batch so a large scan cannot starve Tk's event loop.
        for _ in range(100):
            try:
                func, args, kwargs = self.ui_queue.get_nowait()
            except Empty:
                break
            try:
                func(*args, **kwargs)
            except Exception:
                self.report_callback_exception(*sys.exc_info())
        self._queue_after = self.after(100, self.process_ui_queue)

    def safe_ui_update(self, func, *args, **kwargs):
        if not self._closing:
            self.ui_queue.put((func, args, kwargs))

    @staticmethod
    def clear_tree(tree):
        for item in tree.get_children():
            tree.delete(item)

    def close_app(self):
        self._closing = True
        self.transfer_panel.shutdown()
        self.monitor_running = False
        self.lock_passwords()
        if self._queue_after is not None:
            self.after_cancel(self._queue_after)
        self.destroy()

    def t(self, key):
        return LANGUAGES.get(self.current_lang, {}).get(key, key)

    def apply_color_palette(self, palette_name=None):
        if palette_name: self.active_palette_name = palette_name
        p = COLOR_THEMES.get(self.active_palette_name, COLOR_THEMES["Catppuccin (Varsayılan)"])
        
        mode = ctk.get_appearance_mode().lower()
        # System mode fallback koruması
        if mode not in ["light", "dark"]: 
            mode = "dark" 
            
        theme_colors = p.get("light", p["dark"]) if mode == "light" else p["dark"]

        # DÜZELTME: Ana pencere (TkinterDnD) 'bg' parametresi kullanır
        self.configure(bg=theme_colors["bg"])
        self.toolbar.configure(fg_color=theme_colors["card"])
        self.view_bar.configure(fg_color=theme_colors["bg"])
        self.status_bar.configure(fg_color=theme_colors["bg"])

    def change_appearance_mode(self, new_mode):
        ctk.set_appearance_mode(new_mode.lower())
        self.apply_color_palette()

    def check_first_launch_update(self):
        last_version = ""
        if os.path.exists(VERSION_FILE):
            try:
                with open(VERSION_FILE, "r") as f: last_version = f.read().strip()
            except: pass
        if last_version != CURRENT_VERSION: self.show_update_notes_dialog()

    def show_update_notes_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Beytarchiver Güncelleme Raporu")
        dialog.geometry("560x440")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        lbl_title = ctk.CTkLabel(dialog, text=self.t("update_title"), font=ctk.CTkFont(size=18, weight="bold"), text_color="#89B4FA")
        lbl_title.pack(pady=(20, 10))

        txt_box = ctk.CTkTextbox(dialog, width=500, height=260, corner_radius=10)
        txt_box.pack(pady=10, padx=20)
        txt_box.insert("end", self.t("update_notes"))
        txt_box.configure(state="disabled")

        def close_and_save():
            try:
                with open(VERSION_FILE, "w") as f: f.write(CURRENT_VERSION)
            except: pass
            dialog.destroy()

        btn_ok = ctk.CTkButton(dialog, text=self.t("btn_close_update"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=close_and_save)
        btn_ok.pack(pady=12)

    def change_language(self, new_lang):
        self.current_lang = new_lang
        self.update_ui_language()

    def update_ui_language(self):
        for key, btn in self.nav_btns.items(): btn.configure(text=self.t(key))
        self.drop_lbl.configure(text=self.t("drop_compress"))
        self.extract_drop_lbl.configure(text=self.t("drop_extract"))
        self.btn_start.configure(text=self.t("start_compress"))
        self.btn_start_extract.configure(text=self.t("start_extract"))
        self.entry_pass.configure(placeholder_text=self.t("password"))
        self.entry_ext_pass.configure(placeholder_text=self.t("password_req"))
        self.lbl_av_status.configure(text=self.t("av_title"))
        self.lbl_av_sub.configure(text=self.t("av_sub"))
        self.btn_select_av_file.configure(text=self.t("av_select"))

    def build_toolbar(self):
        self.toolbar = ctk.CTkFrame(self, height=65, corner_radius=0, fg_color="#1E1E2E")
        self.toolbar.grid(row=0, column=0, sticky="ew")

        if HAS_PIL and os.path.exists("logo.png"):
            try:
                img = Image.open("logo.png")
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(38, 38))
                lbl_logo = ctk.CTkLabel(self.toolbar, image=ctk_img, text="")
                lbl_logo.pack(side="left", padx=(12, 5), pady=10)
            except: pass
        else:
            lbl_logo_text = ctk.CTkLabel(self.toolbar, text=f"⚡ BEYT v{CURRENT_VERSION}", font=ctk.CTkFont(size=16, weight="bold"), text_color="#89B4FA")
            lbl_logo_text.pack(side="left", padx=(15, 10), pady=10)

        self.create_tb_btn("➕ Ekle", self.select_compress_files)
        self.create_tb_btn("📂 Çıkart", lambda: self.show_view("extract"))
        self.create_tb_btn("🔐 Kasa", lambda: self.show_view("vault"))
        self.create_tb_btn("⚡ RAM", lambda: self.show_view("ram"))
        self.create_tb_btn("📈 İzleyici", lambda: self.show_view("monitor"))
        self.create_tb_btn("📱 Telefon", lambda: self.show_view("transfer"))
        self.create_tb_btn("🛡️ Antivirüs", lambda: self.show_view("antivirus"))
        self.create_tb_btn("🧹 Temizleyici", lambda: self.show_view("cleaner"))
        self.create_tb_btn("🔑 Şifreler", lambda: self.show_view("passwords"))
        self.create_tb_btn("📌 Yenilikler", self.show_update_notes_dialog)
        self.create_tb_btn("⚙️ Ayarlar", lambda: self.show_view("settings"))

    def create_tb_btn(self, text, command):
        btn = ctk.CTkButton(self.toolbar, text=text, width=85, height=42, fg_color="#313244", hover_color="#45475A", font=ctk.CTkFont(size=11, weight="bold"), command=command)
        btn.pack(side="left", padx=2, pady=10)
        return btn

    def build_navbar(self):
        self.view_bar = ctk.CTkFrame(self, height=35, corner_radius=0, fg_color="#181825")
        self.view_bar.grid(row=1, column=0, sticky="ew")

        self.nav_btns = {}
        views = [
            ("compress", "compress"), ("extract", "extract"), ("vault", "vault"), ("ram", "ram"),
            ("updater", "updater"), ("antivirus", "antivirus"), ("cleaner", "cleaner"),
            ("analyzer", "analyzer"), ("duplicates", "duplicates"), ("shredder", "shredder"),
            ("organizer", "organizer"), ("startup", "startup"), ("hash", "hash"),
            ("monitor", "monitor"), ("passwords", "passwords"), ("settings", "settings")
        ]
        views.insert(2, ('transfer', 'transfer'))

        for key, text_key in views:
            btn = ctk.CTkButton(self.view_bar, text=self.t(text_key), fg_color="transparent", width=85, height=28, command=lambda k=key: self.show_view(k))
            btn.pack(side="left", padx=2, pady=3)
            self.nav_btns[key] = btn

    def show_view(self, view_name):
        if view_name != 'passwords':
            self.lock_passwords()
        panels = [
            self.compress_panel, self.extract_panel, self.vault_panel, self.ram_panel, self.updater_panel,
            self.antivirus_panel, self.cleaner_panel, self.analyzer_panel, self.duplicates_panel,
            self.shredder_panel, self.organizer_panel, self.startup_panel, self.hash_panel,
            self.monitor_panel, self.password_panel, self.settings_panel, self.transfer_panel
        ]
        for panel in panels: panel.pack_forget()
        for btn in self.nav_btns.values(): btn.configure(fg_color="transparent")

        if view_name in self.nav_btns: self.nav_btns[view_name].configure(fg_color="#313244")

        target = getattr(self, 'password_panel' if view_name == 'passwords' else f"{view_name}_panel")
        target.pack(fill="both", expand=True)

        if view_name == "startup": self.load_startup_apps()
        if view_name == "monitor": self.start_monitor_loop()

    def build_all_views(self):
        self.build_compress_view()
        self.build_extract_view()
        self.build_vault_view()
        self.build_ram_view()
        self.build_updater_view()
        self.build_antivirus_view()
        self.build_cleaner_view()
        self.build_analyzer_view()
        self.build_duplicates_view()
        self.build_shredder_view()
        self.build_organizer_view()
        self.build_startup_view()
        self.build_hash_view()
        self.build_monitor_view()
        self.build_password_view()
        self.build_settings_view()
        self.transfer_panel = TransferPanel(self.content_frame, self.safe_ui_update)

    # ==========================================
    # 📈 CANLI KAYNAK İZLEYİCİ
    # ==========================================
    def build_monitor_view(self):
        self.monitor_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.monitor_panel, corner_radius=12, fg_color="#1E1E2E", height=90)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="📈 Sistem Kaynak İzleyicisi", font=ctk.CTkFont(size=20, weight="bold"), text_color="#89B4FA").pack(pady=(15, 0))

        body = ctk.CTkFrame(self.monitor_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True, padx=20, pady=20)

        self.lbl_cpu = ctk.CTkLabel(body, text="CPU Kullanımı: %0", font=ctk.CTkFont(size=18))
        self.lbl_cpu.pack(pady=(20, 0))
        self.prog_cpu = ctk.CTkProgressBar(body, width=500)
        self.prog_cpu.pack(pady=10)
        self.prog_cpu.set(0)

        self.lbl_ram = ctk.CTkLabel(body, text="RAM Kullanımı: %0", font=ctk.CTkFont(size=18))
        self.lbl_ram.pack(pady=(20, 0))
        self.prog_ram = ctk.CTkProgressBar(body, width=500)
        self.prog_ram.pack(pady=10)
        self.prog_ram.set(0)

    def start_monitor_loop(self):
        if getattr(self, "monitor_running", False): return
        self.monitor_running = True
        
        def update_stats():
            while self.monitor_running:
                try:
                    cpu = psutil.cpu_percent()
                    ram = psutil.virtual_memory().percent
                    self.safe_ui_update(self.lbl_cpu.configure, text=f"CPU Kullanımı: %{cpu}")
                    self.safe_ui_update(self.prog_cpu.set, cpu/100)
                    self.safe_ui_update(self.lbl_ram.configure, text=f"RAM Kullanımı: %{ram}")
                    self.safe_ui_update(self.prog_ram.set, ram/100)
                except: pass
                threading.Event().wait(1)
        threading.Thread(target=update_stats, daemon=True).start()

    # ==========================================
    # 🔑 ŞİFRE YÖNETİCİSİ
    # ==========================================
    def build_password_view(self):
        self.password_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.password_panel, corner_radius=12, fg_color="#1E1E2E", height=90)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="🔑 AES-256 Şifre Yöneticisi", font=ctk.CTkFont(size=20, weight="bold"), text_color="#A6E3A1").pack(pady=(15, 0))

        body = ctk.CTkFrame(self.password_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True, padx=20, pady=20)

        input_frame = ctk.CTkFrame(body, fg_color="transparent")
        input_frame.pack(pady=10)
        self.ent_site = ctk.CTkEntry(input_frame, placeholder_text="Site / Uygulama", width=200)
        self.ent_site.pack(side="left", padx=5)
        self.ent_pass = ctk.CTkEntry(input_frame, placeholder_text="Şifre", width=200)
        self.ent_pass.configure(show='*')
        self.ent_pass.pack(side="left", padx=5)
        self.ent_site.bind('<KeyPress>', lambda event: self.password_activity())
        self.ent_pass.bind('<KeyPress>', lambda event: self.password_activity())
        ctk.CTkButton(input_frame, text="Kaydet", command=self.save_password, width=100, fg_color="#89B4FA", text_color="#11111B").pack(side="left", padx=5)

        self.pass_tree = ttk.Treeview(body, columns=("site", "pass"), show="headings")
        self.pass_tree.heading("site", text="Site"); self.pass_tree.heading("pass", text="Şifre")
        self.pass_tree.pack(fill="both", expand=True, pady=10)
        self.pass_tree.bind('<<TreeviewSelect>>', lambda event: self.password_activity())
        self.lbl_password_status = ctk.CTkLabel(body, text='Kasa kilitli')
        self.lbl_password_status.pack(pady=5)
        ctk.CTkButton(body, text='Kasa Oluştur / Kilidi Aç', command=self.unlock_passwords).pack(pady=5)
        ctk.CTkButton(body, text='Kilitle', command=self.lock_passwords).pack(pady=5)
        ctk.CTkButton(body, text='Seçili Şifreyi 15 Saniye Göster', command=self.reveal_password).pack(pady=5)
        ctk.CTkButton(body, text='Eski JSON Kayıtlarını İçe Aktar', command=self.import_legacy_passwords).pack(pady=5)
        ctk.CTkButton(body, text="Seçiliyi Sil", fg_color="#F38BA8", command=self.delete_password).pack(pady=5)

    def unlock_passwords(self):
        password = simpledialog.askstring('Şifre Kasası', 'Ana parola (yeni kasa: en az 12 karakter):',
                                          show='*', parent=self)
        if password is None:
            return
        try:
            if self.password_vault.path.exists():
                self.password_vault.unlock(password)
            else:
                confirm = simpledialog.askstring('Yeni Kasa', 'Ana parolayı tekrar girin:', show='*', parent=self)
                if password != confirm:
                    raise ValueError('Ana parolalar eşleşmiyor.')
                self.password_vault.create(password)
            self.refresh_passwords()
            self.password_activity()
            self.lbl_password_status.configure(text='Kasa açık; sekmeden ayrılınca veya 5 dakika sonra kilitlenir.')
        except (OSError, ValueError) as exc:
            self.lock_passwords()
            messagebox.showerror('Kasa açılamadı', str(exc), parent=self)

    def password_activity(self):
        if self.password_vault.unlocked:
            if self._password_after is not None:
                self.after_cancel(self._password_after)
            self._password_after = self.after(5 * 60 * 1000, self.lock_passwords)

    def lock_passwords(self):
        if self._password_after is not None:
            self.after_cancel(self._password_after)
            self._password_after = None
        if self._reveal_after is not None:
            self.after_cancel(self._reveal_after)
            self._reveal_after = None
        self.password_vault.lock()
        self._password_sites.clear()
        self.clear_tree(self.pass_tree)
        self.ent_site.delete(0, 'end')
        self.ent_pass.delete(0, 'end')
        self.lbl_password_status.configure(text='Kasa kilitli')

    def refresh_passwords(self):
        self.clear_tree(self.pass_tree)
        self._password_sites.clear()
        for site in sorted(self.password_vault.data):
            row = self.pass_tree.insert('', 'end', values=(site, '••••••••'))
            # Treeview coerces numeric-looking values (e.g. '00123') to ints.
            # Row identity, rather than display values, must identify the record.
            self._password_sites[row] = site

    def reveal_password(self):
        selected = self.pass_tree.selection()
        if selected and self.password_vault.unlocked:
            item = selected[0]
            site = self._password_sites[item]
            self.pass_tree.item(item, values=(site, self.password_vault.data[site]))
            if self._reveal_after is not None:
                self.after_cancel(self._reveal_after)
            self._reveal_after = self.after(15000, self.hide_revealed_passwords)
            self.password_activity()

    def hide_revealed_passwords(self):
        self._reveal_after = None
        self.refresh_passwords()

    def import_legacy_passwords(self):
        if not self.password_vault.unlocked:
            messagebox.showinfo('Kasa kilitli', 'Önce kasanın kilidini açın.', parent=self)
            return
        if not self.legacy_pass_file.exists():
            messagebox.showinfo('İçe aktar', 'Eski JSON dosyası bulunamadı.', parent=self)
            return
        if not messagebox.askyesno('Eski kayıtlar',
                'Açık metin JSON kayıtları şifreli kasaya alınacak. Mevcut kasa kayıtları korunur. '
                'Eski dosya silinmez ve açık metin kalır; işlemden sonra ayrıca kaldırmalısınız. Devam edilsin mi?',
                parent=self):
            return
        try:
            if self.legacy_pass_file.stat().st_size > 16 * 1024 * 1024:
                raise ValueError('Eski kayıt dosyası çok büyük.')
            data = json.loads(self.legacy_pass_file.read_text(encoding='utf-8'))
            PasswordVault._validate(data)
            self.password_vault.save({**data, **self.password_vault.data})
            self.refresh_passwords()
            self.password_activity()
            messagebox.showinfo('İçe aktarıldı', 'Şifreli kayıt tamamlandı. Eski açık metin JSON dosyası korunmuştur.',
                                parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror('İçe aktarılamadı', str(exc), parent=self)

    def save_password(self):
        if not self.password_vault.unlocked:
            messagebox.showinfo('Kasa kilitli', 'Önce kasanın kilidini açın.', parent=self)
            return
        site, pwd = self.ent_site.get().strip(), self.ent_pass.get()
        if not site or not pwd:
            return
        try:
            self.password_vault.save({**self.password_vault.data, site: pwd})
            self.refresh_passwords()
            self.password_activity()
            self.ent_site.delete(0, 'end')
            self.ent_pass.delete(0, 'end')
        except (OSError, ValueError) as exc:
            messagebox.showerror('Kaydedilemedi', str(exc), parent=self)

    def delete_password(self):
        if not self.password_vault.unlocked:
            return
        selected = self.pass_tree.selection()
        if selected:
            site = self._password_sites[selected[0]]
            data = dict(self.password_vault.data)
            data.pop(site, None)
            try:
                self.password_vault.save(data)
                self.refresh_passwords()
                self.password_activity()
            except (OSError, ValueError) as exc:
                messagebox.showerror('Silinemedi', str(exc), parent=self)

    # ==========================================
    # 🛠️ DİĞER MODÜLLER
    # ==========================================

    def build_compress_view(self):
        self.compress_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.drop_zone = ctk.CTkFrame(self.compress_panel, height=75, border_width=2, border_color="#89B4FA", corner_radius=10)
        self.drop_zone.pack(fill="x", pady=(0, 8))
        self.drop_zone.pack_propagate(False)
        self.drop_lbl = ctk.CTkLabel(self.drop_zone, text=self.t("drop_compress"), font=ctk.CTkFont(size=13, weight="bold"))
        self.drop_lbl.pack(expand=True)
        self.drop_zone.bind("<Button-1>", lambda e: self.select_compress_files())

        self.tree_frame = ctk.CTkFrame(self.compress_panel, fg_color="transparent")
        self.tree_frame.pack(fill="both", expand=True)
        columns = ("name", "size", "type", "path")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="headings")
        self.tree.heading("name", text="Dosya Adı"); self.tree.heading("size", text="Boyut"); self.tree.heading("type", text="Tür"); self.tree.heading("path", text="Tam Yol")
        self.tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.opt_panel = ctk.CTkFrame(self.compress_panel, height=50, corner_radius=10)
        self.opt_panel.pack(fill="x", pady=8)
        self.combo_fmt = ctk.CTkComboBox(self.opt_panel, values=["zip", "7z", "tar"], width=80)
        self.combo_fmt.pack(side="left", padx=5, pady=8)
        self.entry_pass = ctk.CTkEntry(self.opt_panel, placeholder_text=self.t("password"), show="*", width=130)
        self.entry_pass.pack(side="left", padx=5, pady=8)
        self.btn_start = ctk.CTkButton(self.opt_panel, text=self.t("start_compress"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_compression)
        self.btn_start.pack(side="right", padx=8, pady=8)

        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self.handle_compress_drop)

    def select_compress_files(self):
        selected = filedialog.askopenfilenames()
        for f in selected: self.add_to_compress_list(f)

    def handle_compress_drop(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            f = f.strip("{}")
            if os.path.exists(f): self.add_to_compress_list(f)

    def add_to_compress_list(self, path):
        if path not in self.files_to_archive:
            self.files_to_archive.append(path)
            size = format_size(get_path_size(path))
            ftype = "Klasör" if os.path.isdir(path) else "Dosya"
            self.tree.insert("", "end", values=(os.path.basename(path), size, ftype, path))

    def start_compression(self):
        if self._compressing:
            return
        if not self.files_to_archive:
            self.safe_ui_update(self.lbl_status.configure, text="Lütfen önce dosya ekleyin!", text_color="#F38BA8")
            return
        files = tuple(self.files_to_archive)
        fmt, pwd = self.combo_fmt.get().lower(), self.entry_pass.get()
        self._compressing = True
        self.btn_start.configure(state='disabled')
        threading.Thread(target=self.compress_engine, args=(files, fmt, pwd), daemon=True).start()

    def compress_engine(self, files, fmt, pwd):
        self.safe_ui_update(self.lbl_status.configure, text="Sıkıştırılıyor...", text_color="#89B4FA")
        try:
            out_name = f"beyt_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
            used_names = set()
            all_entries = []
            
            for item in files:
                if os.path.isfile(item):
                    arcname = unique_arcname(os.path.basename(item), used_names)
                    all_entries.append((item, arcname))
                elif os.path.isdir(item):
                    for root, _, files in os.walk(item):
                        for f in files:
                            fp = os.path.join(root, f)
                            rel = os.path.relpath(fp, start=os.path.dirname(item))
                            arcname = unique_arcname(rel, used_names)
                            all_entries.append((fp, arcname))

            if fmt == "zip":
                with pyzipper.AESZipFile(out_name, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES if pwd else None) as zf:
                    if pwd: zf.setpassword(pwd.encode())
                    for fp, an in all_entries: zf.write(fp, an)
            elif fmt == "7z":
                with py7zr.SevenZipFile(out_name, "w", password=pwd if pwd else None) as z:
                    for fp, an in all_entries: z.write(fp, an)
            elif fmt == "tar":
                if pwd:
                    raise ValueError('TAR şifrelemeyi desteklemiyor; ZIP veya 7z seçin.')
                with tarfile.open(out_name, "w") as tar:
                    for fp, an in all_entries: tar.add(fp, arcname=an)
            else:
                raise ValueError('Desteklenmeyen sıkıştırma biçimi.')

            self.safe_ui_update(self.lbl_status.configure, text=f"Sıkıştırma Başarılı: {out_name}", text_color="#A6E3A1")
            beep(1000, 300)
            send_notification("Beytarchiver", "Arşiv başarıyla oluşturuldu!")
        except Exception as e:
            self.safe_ui_update(self.lbl_status.configure, text=f"Hata: {e}", text_color="#F38BA8")
        finally:
            self.safe_ui_update(self.finish_compression)

    def finish_compression(self):
        self._compressing = False
        self.btn_start.configure(state='normal')

    def build_extract_view(self):
        self.extract_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.extract_drop_zone = ctk.CTkFrame(self.extract_panel, height=75, border_width=2, border_color="#A6E3A1", corner_radius=10)
        self.extract_drop_zone.pack(fill="x", pady=(0, 8))
        self.extract_drop_zone.pack_propagate(False)
        self.extract_drop_lbl = ctk.CTkLabel(self.extract_drop_zone, text=self.t("drop_extract"), font=ctk.CTkFont(size=13, weight="bold"))
        self.extract_drop_lbl.pack(expand=True)
        self.extract_drop_zone.bind("<Button-1>", lambda e: self.select_extract_file())
        self.entry_ext_pass = ctk.CTkEntry(self.extract_panel, placeholder_text=self.t("password_req"), show="*", width=160)
        self.entry_ext_pass.pack(pady=10)
        self.btn_start_extract = ctk.CTkButton(self.extract_panel, text=self.t("start_extract"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_extraction)
        self.btn_start_extract.pack(pady=5)
        
        self.extract_drop_zone.drop_target_register(DND_FILES)
        self.extract_drop_zone.dnd_bind("<<Drop>>", self.handle_extract_drop)

    def select_extract_file(self):
        selected = filedialog.askopenfilename(filetypes=[("Archives", "*.zip *.7z *.tar *.gz *.tgz *.beyt")])
        if selected:
            self.archive_to_extract = selected
            self.safe_ui_update(self.lbl_status.configure, text=f"Seçilen Arşiv: {os.path.basename(selected)}", text_color="#A6E3A1")

    def handle_extract_drop(self, event):
        files = self.tk.splitlist(event.data)
        if files and os.path.isfile(files[0].strip("{}")):
            self.archive_to_extract = files[0].strip("{}")
            self.safe_ui_update(self.lbl_status.configure, text=f"Seçilen Arşiv: {os.path.basename(self.archive_to_extract)}", text_color="#A6E3A1")

    def start_extraction(self):
        if self._extracting or not self.archive_to_extract:
            return
        archive, pwd = self.archive_to_extract, self.entry_ext_pass.get()
        self._extracting = True
        self.btn_start_extract.configure(state='disabled')
        threading.Thread(target=self.extract_engine, args=(archive, pwd), daemon=True).start()

    def extract_engine(self, archive, pwd):
        self.safe_ui_update(self.lbl_status.configure, text="Dosyalar Çıkartılıyor...", text_color="#89B4FA")
        try:
            out_dir = os.path.splitext(archive)[0] + "_extracted"
            safe_extract_archive(archive, out_dir, pwd)
                    
            self.safe_ui_update(self.lbl_status.configure, text="Çıkartma Başarılı!", text_color="#A6E3A1")
            beep(1000, 300)
            open_in_explorer(out_dir)
        except Exception as e:
            self.safe_ui_update(self.lbl_status.configure, text=f"Çıkartma Hatası: {e}", text_color="#F38BA8")
        finally:
            self.safe_ui_update(self.finish_extraction)

    def finish_extraction(self):
        self._extracting = False
        self.btn_start_extract.configure(state='normal')

    def build_vault_view(self):
        self.vault_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.vault_panel, corner_radius=12, fg_color="#1E1E2E", height=90)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="🔐 Beytarchiver Encrypted Vault (.beyt)", font=ctk.CTkFont(size=20, weight="bold"), text_color="#89B4FA").pack(pady=(15, 0))
        body = ctk.CTkFrame(self.vault_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)
        self.entry_vault_pass = ctk.CTkEntry(body, placeholder_text="Kasa İçin Güçlü Parola Girin", show="*", width=250)
        self.entry_vault_pass.pack(pady=20)
        ctk.CTkButton(body, text="🔐 Dosyaları Seç ve .beyt Kasası Oluştur", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.create_vault).pack(pady=10)
        self.lbl_vault_status = ctk.CTkLabel(body, text="Kasa İşlemi Bekleniyor", font=ctk.CTkFont(size=13))
        self.lbl_vault_status.pack(pady=15)

    def create_vault(self):
        pwd = self.entry_vault_pass.get()
        if not pwd:
            self.safe_ui_update(self.lbl_vault_status.configure, text="❌ Lütfen parola girin!", text_color="#F38BA8")
            return
        files = filedialog.askopenfilenames()
        if files: threading.Thread(target=self.vault_engine, args=(files, pwd), daemon=True).start()

    def vault_engine(self, files, pwd):
        try:
            out_name = f"secure_vault_{datetime.now().strftime('%Y%m%d_%H%M%S')}.beyt"
            with pyzipper.AESZipFile(out_name, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
                zf.setpassword(pwd.encode())
                for f in files: zf.write(f, os.path.basename(f))
            self.safe_ui_update(self.lbl_vault_status.configure, text=f"✅ Kasa Oluşturuldu: {out_name}", text_color="#A6E3A1")
            beep(1000, 300)
        except Exception as e:
            self.safe_ui_update(self.lbl_vault_status.configure, text=f"Hata: {e}", text_color="#F38BA8")

    def build_ram_view(self):
        self.ram_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.ram_panel, corner_radius=12, fg_color="#1E1E2E", height=90)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="⚡ RAM Booster & Memory Purger", font=ctk.CTkFont(size=20, weight="bold"), text_color="#A6E3A1").pack(pady=(15, 0))
        body = ctk.CTkFrame(self.ram_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)
        ctk.CTkButton(body, text="⚡ Sistem Belleğini / RAM'i Temizle", fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(size=14, weight="bold"), command=self.clean_ram).pack(pady=30)
        self.lbl_ram_status = ctk.CTkLabel(body, text="Hazır", font=ctk.CTkFont(size=13))
        self.lbl_ram_status.pack(pady=10)

    def clean_ram(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.psapi.EmptyWorkingSet(-1)
                self.safe_ui_update(self.lbl_ram_status.configure, text="✅ Sistem RAM'i başarıyla rahatlatıldı!", text_color="#A6E3A1")
                beep(1200, 200)
            except Exception as e:
                self.safe_ui_update(self.lbl_ram_status.configure, text=f"Hata: {e}", text_color="#F38BA8")

    def build_updater_view(self):
        self.updater_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.updater_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(top, text="🔍 Eski Sürüm Yazılımları Tara (winget)", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=lambda: threading.Thread(target=self.updater_engine, daemon=True).start()).pack(side="left", padx=15, pady=12)
        self.lbl_up_status = ctk.CTkLabel(top, text="Tarama Bekleniyor", font=ctk.CTkFont(size=12))
        self.lbl_up_status.pack(side="left", padx=10)
        self.up_box = ctk.CTkTextbox(self.updater_panel, height=220, corner_radius=10, state="disabled")
        self.up_box.pack(fill="both", expand=True)

    def updater_engine(self):
        self.safe_ui_update(self.lbl_up_status.configure, text="Taranıyor...", text_color="#89B4FA")
        self.safe_ui_update(self.up_box.configure, state="normal")
        self.safe_ui_update(self.up_box.delete, "1.0", "end")
        try:
            res = subprocess.run(["winget", "upgrade"], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20)
            self.safe_ui_update(self.up_box.insert, "end", res.stdout if res.stdout else "Her şey güncel!")
        except subprocess.TimeoutExpired:
            self.safe_ui_update(self.up_box.insert, "end", "Hata: İşlem zaman aşımına uğradı. Winget yanıt vermiyor.")
        except Exception as e:
            self.safe_ui_update(self.up_box.insert, "end", f"Hata: {e}")
        
        self.safe_ui_update(self.lbl_up_status.configure, text="Tamamlandı", text_color="#A6E3A1")
        self.safe_ui_update(self.up_box.configure, state="disabled")

    def build_antivirus_view(self):
        self.antivirus_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.av_hero = ctk.CTkFrame(self.antivirus_panel, height=90, corner_radius=12, fg_color="#1E1E2E")
        self.av_hero.pack(fill="x", pady=(0, 10))
        self.av_hero.pack_propagate(False)
        self.lbl_av_status = ctk.CTkLabel(self.av_hero, text=self.t("av_title"), font=ctk.CTkFont(size=22, weight="bold"), text_color="#89B4FA")
        self.lbl_av_status.pack(pady=(18, 0))
        self.lbl_av_sub = ctk.CTkLabel(self.av_hero, text=self.t("av_sub"), font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        self.lbl_av_sub.pack(pady=2)
        
        self.av_body = ctk.CTkFrame(self.antivirus_panel, corner_radius=10, fg_color="#181825")
        self.av_body.pack(fill="both", expand=True)
        self.btn_select_av_file = ctk.CTkButton(self.av_body, text=self.t("av_select"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.select_av_file)
        self.btn_select_av_file.pack(pady=15, padx=20)
        self.lbl_av_file = ctk.CTkLabel(self.av_body, text=self.t("no_file"), font=ctk.CTkFont(size=13))
        self.lbl_av_file.pack(pady=2)
        self.av_box = ctk.CTkTextbox(self.av_body, height=220, state="disabled", corner_radius=10)
        self.av_box.pack(fill="both", expand=True, padx=20, pady=15)

    def select_av_file(self):
        selected = filedialog.askopenfilename()
        if selected:
            self.lbl_av_file.configure(text=f"Seçilen: {os.path.basename(selected)}", text_color="#89B4FA")
            threading.Thread(target=self.run_custom_antivirus, args=(selected,), daemon=True).start()

    def run_custom_antivirus(self, file_path):
        self.safe_ui_update(self.av_box.configure, state="normal")
        self.safe_ui_update(self.av_box.delete, "1.0", "end")
        self.safe_ui_update(self.av_box.insert, "end", f"🛡️ BEYTARCHIVER ULTIMATE SECURITY SCAN\n")
        self.safe_ui_update(self.av_box.insert, "end", f"📄 Dosya: {os.path.basename(file_path)}\n")
        self.safe_ui_update(self.av_box.insert, "end", "=" * 60 + "\n\n")
        
        results, file_hash = self.av_engine.scan_file(file_path)
        
        if file_hash: self.safe_ui_update(self.av_box.insert, "end", f"🔑 SHA-256: {file_hash}\n\n")
        if results:
            for res in results: self.safe_ui_update(self.av_box.insert, "end", f"{res}\n")
        else: 
            self.safe_ui_update(self.av_box.insert, "end", "Bilinen test imzası veya uzantı uyarısı bulunmadı. Bu sonuç dosyanın güvenli olduğunu garanti etmez.\n")
            
        self.safe_ui_update(self.av_box.configure, state="disabled")
        beep(1000, 200)

    def build_cleaner_view(self):
        self.cleaner_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.hero_cleaner = ctk.CTkFrame(self.cleaner_panel, height=90, corner_radius=12, fg_color="#1E1E2E")
        self.hero_cleaner.pack(fill="x", pady=(0, 10))
        self.hero_cleaner.pack_propagate(False)
        self.lbl_junk_size = ctk.CTkLabel(self.hero_cleaner, text="0.00 MB", font=ctk.CTkFont(size=30, weight="bold"), text_color="#F38BA8")
        self.lbl_junk_size.pack(pady=(12, 0))
        self.lbl_hero_sub = ctk.CTkLabel(self.hero_cleaner, text=self.t("junk_sub"), font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        self.lbl_hero_sub.pack(pady=2)
        
        self.cleaner_body = ctk.CTkFrame(self.cleaner_panel, fg_color="transparent")
        self.cleaner_body.pack(fill="both", expand=True)
        self.cleaner_body.grid_columnconfigure(0, weight=3)
        self.cleaner_body.grid_columnconfigure(1, weight=1)
        self.cleaner_body.grid_rowconfigure(0, weight=1)
        
        self.clean_tree_frame = ctk.CTkFrame(self.cleaner_body, corner_radius=10, fg_color="#181825")
        self.clean_tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        columns = ("path", "size", "type")
        self.clean_tree = ttk.Treeview(self.clean_tree_frame, columns=columns, show="headings")
        self.clean_tree.heading("path", text="Yol"); self.clean_tree.heading("size", text="Boyut"); self.clean_tree.heading("type", text="Tür")
        self.clean_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        self.clean_opts = ctk.CTkFrame(self.cleaner_body, corner_radius=10, fg_color="#181825")
        self.clean_opts.grid(row=0, column=1, sticky="nsew")
        self.chk_temp = ctk.CTkCheckBox(self.clean_opts, text="Windows Temp")
        self.chk_temp.select(); self.chk_temp.pack(pady=10, padx=12, anchor="w")
        self.chk_user_temp = ctk.CTkCheckBox(self.clean_opts, text="AppData Temp")
        self.chk_user_temp.select(); self.chk_user_temp.pack(pady=10, padx=12, anchor="w")
        self.chk_recycle = ctk.CTkCheckBox(self.clean_opts, text="Geri Dönüşüm")
        if sys.platform == 'win32':
            self.chk_recycle.select()
        else:
            self.chk_recycle.configure(state='disabled')
        self.chk_recycle.pack(pady=10, padx=12, anchor="w")
        
        self.btn_scan_clean = ctk.CTkButton(self.clean_opts, text=self.t("scan"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_clean_scan)
        self.btn_scan_clean.pack(pady=15, padx=12, fill="x")
        self.btn_do_clean = ctk.CTkButton(self.clean_opts, text=self.t("clean"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), state="disabled", command=self.start_cleaning)
        self.btn_do_clean.pack(pady=5, padx=12, fill="x")

    def start_clean_scan(self):
        if self._cleaning:
            return
        scan_paths = []
        if self.chk_temp.get(): scan_paths.append((os.environ.get("TEMP"), "Windows Temp"))
        if self.chk_user_temp.get(): scan_paths.append((os.path.expanduser("~\\AppData\\Local\\Temp"), "User Temp"))
        self._cleaning = True
        self.btn_scan_clean.configure(state='disabled', text='Taranıyor...')
        self.btn_do_clean.configure(state='disabled')
        threading.Thread(target=self.scan_engine, args=(tuple(scan_paths),), daemon=True).start()

    def scan_engine(self, scan_paths):
        self.safe_ui_update(self.clear_tree, self.clean_tree)
        junk_files, total = [], 0
        for path, tag in scan_paths:
            if path and os.path.exists(path):
                try:
                    for root, dirs, files in os.walk(path):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                fsize = os.path.getsize(fp)
                                if os.path.islink(fp):
                                    continue
                                junk_files.append((fp, fsize))
                                total += fsize
                                self.safe_ui_update(self.clean_tree.insert, "", "end", values=(fp, format_size(fsize), tag))
                            except: pass
                except: pass
                
        self.safe_ui_update(self.finish_clean_scan, junk_files, total)
        beep(1000, 200)

    def finish_clean_scan(self, files, total):
        self.junk_files, self.total_junk_bytes = files, total
        self._cleaning = False
        self.lbl_junk_size.configure(text=format_size(total))
        self.btn_scan_clean.configure(state='normal', text=self.t('scan'))
        self.btn_do_clean.configure(state='normal' if files or self.chk_recycle.get() else 'disabled',
                                    text=self.t('clean'))

    def start_cleaning(self):
        if self._cleaning:
            return
        files, recycle = tuple(self.junk_files), bool(self.chk_recycle.get())
        if not messagebox.askyesno('Temizleme onayı',
                f'{len(files)} geçici dosya silinecek.' +
                (' Geri dönüşüm kutusu da boşaltılacak.' if recycle else '') +
                ' Devam edilsin mi?', default='no', parent=self):
            return
        self._cleaning = True
        self.btn_scan_clean.configure(state='disabled')
        self.btn_do_clean.configure(state='disabled', text='Temizleniyor...')
        threading.Thread(target=self.clean_engine, args=(files, recycle), daemon=True).start()

    def clean_engine(self, files, recycle):
        failures = 0
        for fp, _ in files:
            try:
                os.remove(fp)
            except OSError:
                failures += 1
        if recycle and sys.platform == 'win32':
            try:
                result = ctypes.windll.shell32.SHEmptyRecycleBinW(
                    None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
                if result:
                    failures += 1
            except OSError:
                failures += 1
        self.safe_ui_update(self.finish_cleaning, failures)

    def finish_cleaning(self, failures):
        self._cleaning = False
        self.lbl_status.configure(text=f'Temizlik tamamlandı. Başarısız işlem: {failures}')
        self.start_clean_scan()

    def build_analyzer_view(self):
        self.analyzer_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.ana_top = ctk.CTkFrame(self.analyzer_panel, corner_radius=10)
        self.ana_top.pack(fill="x", pady=(0, 8))
        self.btn_select_ana_dir = ctk.CTkButton(self.ana_top, text="📁 Taranacak Klasörü/Sürücüyü Seç", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_disk_analysis)
        self.btn_select_ana_dir.pack(side="left", padx=10, pady=10)
        self.lbl_ana_path = ctk.CTkLabel(self.ana_top, text="Klasör Seçilmedi", font=ctk.CTkFont(size=12))
        self.lbl_ana_path.pack(side="left", padx=10)
        
        self.ana_tree_frame = ctk.CTkFrame(self.analyzer_panel, corner_radius=10, fg_color="#181825")
        self.ana_tree_frame.pack(fill="both", expand=True)
        columns = ("name", "size", "path")
        self.ana_tree = ttk.Treeview(self.ana_tree_frame, columns=columns, show="headings")
        self.ana_tree.heading("name", text="En Büyük Dosya Adı"); self.ana_tree.heading("size", text="Boyut"); self.ana_tree.heading("path", text="Konumu")
        self.ana_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)

    def start_disk_analysis(self):
        selected_dir = filedialog.askdirectory()
        if selected_dir:
            self.lbl_ana_path.configure(text=f"Taranıyor: {selected_dir}", text_color="#89B4FA")
            threading.Thread(target=self.analyze_disk_engine, args=(selected_dir,), daemon=True).start()

    def analyze_disk_engine(self, target_dir):
        self.safe_ui_update(self.clear_tree, self.ana_tree)
        file_list = []
        for root, _, files in os.walk(target_dir):
            for f in files:
                try: file_list.append((f, os.path.getsize(os.path.join(root, f)), os.path.join(root, f)))
                except: pass
        
        file_list.sort(key=lambda x: x[1], reverse=True)
        top_files = file_list[:50]
        for fname, fsize, fp in top_files:
            self.safe_ui_update(self.ana_tree.insert, "", "end", values=(fname, format_size(fsize), fp))
            
        self.safe_ui_update(self.lbl_ana_path.configure, text=f"Analiz Tamamlandı: {target_dir}", text_color="#A6E3A1")
        beep(1000, 200)

    def build_duplicates_view(self):
        self.duplicates_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.duplicates_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(top, text="🔍 Klasör Seç ve Çift Dosyaları Tara", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_dup_scan).pack(side="left", padx=10, pady=10)
        self.lbl_dup_status = ctk.CTkLabel(top, text="Klasör Seçilmedi", font=ctk.CTkFont(size=12))
        self.lbl_dup_status.pack(side="left", padx=10)
        
        tree_frame = ctk.CTkFrame(self.duplicates_panel, corner_radius=10, fg_color="#181825")
        tree_frame.pack(fill="both", expand=True)
        columns = ("hash", "name", "size", "path")
        self.dup_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.dup_tree.heading("hash", text="Hash İmzası"); self.dup_tree.heading("name", text="Dosya Adı"); self.dup_tree.heading("size", text="Boyut"); self.dup_tree.heading("path", text="Konumu")
        self.dup_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)

    def start_dup_scan(self):
        target = filedialog.askdirectory()
        if target:
            self.lbl_dup_status.configure(text=f"Taranıyor: {target}", text_color="#89B4FA")
            threading.Thread(target=self.dup_scan_engine, args=(target,), daemon=True).start()

    def dup_scan_engine(self, target):
        self.safe_ui_update(self.clear_tree, self.dup_tree)
        hashes = {}
        for root, _, files in os.walk(target):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    h = self.av_engine.calculate_file_hash(fp)
                    if h:
                        if h not in hashes: hashes[h] = []
                        hashes[h].append(fp)
                except: pass
                
        count = 0
        for h, file_list in hashes.items():
            if len(file_list) > 1:
                for fp in file_list:
                    count += 1
                    sz = format_size(get_path_size(fp))
                    self.safe_ui_update(self.dup_tree.insert, "", "end", values=(h[:16] + "...", os.path.basename(fp), sz, fp))
                    
        self.safe_ui_update(self.lbl_dup_status.configure, text=f"Tarama Bitti: {count} kopya bulundu!", text_color="#A6E3A1")
        beep(1000, 200)

    def build_shredder_view(self):
        self.shredder_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.shredder_panel, corner_radius=12, fg_color="#1E1E2E", height=100)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="🔥 Dosyanın Üzerine Yaz ve Sil", font=ctk.CTkFont(size=20, weight="bold"), text_color="#F38BA8").pack(pady=(15, 0))
        
        body = ctk.CTkFrame(self.shredder_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)
        ctk.CTkButton(body, text="🔥 Kalıcı Olarak İmha Edilecek Dosyayı Seç", fg_color="#F38BA8", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_shred).pack(pady=20)
        self.lbl_shred_file = ctk.CTkLabel(body, text="Dosya Seçilmedi", font=ctk.CTkFont(size=13))
        self.lbl_shred_file.pack(pady=5)

    def start_shred(self):
        selected = filedialog.askopenfilename()
        if selected and messagebox.askyesno('Geri alınamaz işlem',
                f'{selected}\n\nBu dosyanın üzerine yazılıp dosya silinecek. '
                'İşlem geri alınamaz. SSD, yedek ve dosya sistemi kopyalarında '
                'verinin tamamen yok edildiği garanti edilemez. Devam edilsin mi?',
                default='no', parent=self):
            self.lbl_shred_file.configure(text=f"İmha Ediliyor: {os.path.basename(selected)}", text_color="#F38BA8")
            threading.Thread(target=self.shred_engine, args=(selected,), daemon=True).start()

    def shred_engine(self, path):
        try:
            overwrite_and_delete(path)
            self.safe_ui_update(self.lbl_shred_file.configure, text="✅ Dosyanın üzerine yazıldı ve dosya silindi; fiziksel silme garantisi yoktur.", text_color="#A6E3A1")
            beep(1200, 300)
        except Exception as e:
            self.safe_ui_update(self.lbl_shred_file.configure, text=f"Hata: {e}", text_color="#F38BA8")

    def build_organizer_view(self):
        self.organizer_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.organizer_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(top, text="📁 Akıllı Masaüstü ve Klasör Düzenleyici", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=15)
        
        body = ctk.CTkFrame(self.organizer_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)
        ctk.CTkButton(body, text="🖥️ Masaüstünü Düzenle", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=lambda: self.organize_dir(os.path.expanduser("~/Desktop"))).pack(pady=15)
        ctk.CTkButton(body, text="📥 İndirilenler Klasörünü Düzenle", fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=lambda: self.organize_dir(os.path.expanduser("~/Downloads"))).pack(pady=10)
        self.lbl_org_status = ctk.CTkLabel(body, text="İşlem Bekleniyor", font=ctk.CTkFont(size=13))
        self.lbl_org_status.pack(pady=15)

    def organize_dir(self, target_path):
        if not os.path.exists(target_path): return
        categories = {"Belgeler": [".pdf", ".docx", ".txt"], "Resimler": [".jpg", ".jpeg", ".png"], "Arşivler": [".zip", ".7z"]}
        moved = 0
        for item in os.listdir(target_path):
            fp = os.path.join(target_path, item)
            if os.path.isfile(fp):
                ext = os.path.splitext(item)[1].lower()
                for cat, exts in categories.items():
                    if ext in exts:
                        cat_dir = os.path.join(target_path, cat)
                        os.makedirs(cat_dir, exist_ok=True)
                        shutil.move(fp, os.path.join(cat_dir, item))
                        moved += 1; break
                        
        self.safe_ui_update(self.lbl_org_status.configure, text=f"✅ Başarılı! {moved} dosya kategorize edildi.", text_color="#A6E3A1")
        beep(1000, 200)

    def build_startup_view(self):
        self.startup_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.startup_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(top, text="🚀 Windows Başlangıç Uygulamaları", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=15, pady=10)
        
        self.start_tree_frame = ctk.CTkFrame(self.startup_panel, corner_radius=10, fg_color="#181825")
        self.start_tree_frame.pack(fill="both", expand=True)
        columns = ("name", "command")
        self.start_tree = ttk.Treeview(self.start_tree_frame, columns=columns, show="headings")
        self.start_tree.heading("name", text="Uygulama Adı"); self.start_tree.heading("command", text="Çalıştırma Komutu")
        self.start_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)

    def load_startup_apps(self):
        for item in self.start_tree.get_children(): self.start_tree.delete(item)
        if sys.platform == "win32":
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        self.start_tree.insert("", "end", values=(name, val))
                        i += 1
                    except OSError: break
                winreg.CloseKey(key)
            except Exception: pass

    def build_hash_view(self):
        self.hash_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.hash_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(top, text="🔍 Hash Hesaplanacak Dosyayı Seç", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.select_hash_file).pack(side="left", padx=15, pady=12)
        self.lbl_hash_file = ctk.CTkLabel(top, text="Dosya Seçilmedi", font=ctk.CTkFont(size=12))
        self.lbl_hash_file.pack(side="left", padx=10)
        
        self.hash_box = ctk.CTkTextbox(self.hash_panel, height=220, corner_radius=10, state="disabled")
        self.hash_box.pack(fill="both", expand=True)

    def select_hash_file(self):
        selected = filedialog.askopenfilename()
        if selected:
            self.lbl_hash_file.configure(text=os.path.basename(selected), text_color="#89B4FA")
            threading.Thread(target=self.calculate_hashes, args=(selected,), daemon=True).start()

    def calculate_hashes(self, file_path):
        md5, sha1, sha256 = hashlib.md5(), hashlib.sha1(), hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk); sha1.update(chunk); sha256.update(chunk)
        res = f"📄 Dosya: {os.path.basename(file_path)}\n\n📌 MD5:\n{md5.hexdigest()}\n\n📌 SHA-1:\n{sha1.hexdigest()}\n\n📌 SHA-256:\n{sha256.hexdigest()}\n"
        self.safe_ui_update(lambda: self.update_hash_box(res))

    def update_hash_box(self, text):
        self.hash_box.configure(state="normal")
        self.hash_box.delete("1.0", "end")
        self.hash_box.insert("end", text)
        self.hash_box.configure(state="disabled")

    def build_settings_view(self):
        self.settings_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        
        # Üst Başlık
        ctk.CTkLabel(self.settings_panel, text="⚙️ " + self.t("settings"), font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 10))

        # Şık Konteyner Kutu
        settings_container = ctk.CTkFrame(self.settings_panel, fg_color="#181825", corner_radius=15, width=400)
        settings_container.pack(pady=10, padx=20, fill="y", expand=True)
        
        # Görünüm Modu
        ctk.CTkLabel(settings_container, text=self.t("theme"), font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(30, 5))
        self.theme_menu = ctk.CTkOptionMenu(settings_container, values=["Dark", "Light", "System"], command=self.change_appearance_mode, width=200)
        self.theme_menu.pack(pady=5, padx=50)
        # Mevcut modu ayarla
        current_mode = ctk.get_appearance_mode().capitalize()
        self.theme_menu.set(current_mode if current_mode in ["Dark", "Light"] else "System")
        
        # Renk Paleti
        ctk.CTkLabel(settings_container, text=self.t("color_palette"), font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 5))
        self.palette_menu = ctk.CTkOptionMenu(settings_container, values=list(COLOR_THEMES.keys()), command=self.apply_color_palette, width=200)
        self.palette_menu.set(self.active_palette_name)
        self.palette_menu.pack(pady=5, padx=50)
        
        # Dil Seçimi
        ctk.CTkLabel(settings_container, text=self.t("language"), font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 5))
        self.lang_menu = ctk.CTkOptionMenu(settings_container, values=["TR", "EN"], command=self.change_language, width=200)
        self.lang_menu.set(self.current_lang)
        self.lang_menu.pack(pady=(5, 30), padx=50)

if __name__ == "__main__":
    app = BeytarchiverV37App()
    app.mainloop()
