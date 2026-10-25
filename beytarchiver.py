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
import urllib.request
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
from beyt_core import format_size, safe_extract_archive, unique_arcname

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
CURRENT_VERSION = "4.0.2"
VERSION_FILE = os.path.expanduser("~/.beytarchiver_version")
CONFIG_DIR = Path.home() / ".beytarchiver"
CONFIG_FILE = CONFIG_DIR / "config.json"
# GitHub depo kimliği: sürümler bu depodaki Releases bölümünden yayınlanır.
GITHUB_REPO = "Beytarchiver/files"
SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004

# --- Yardımcı Fonksiyonlar ---
def resource_path(relative_path):
    for base in (
        Path(getattr(sys, "_MEIPASS", "")),
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parents[2],
        Path.cwd(),
    ):
        if str(base):
            candidate = base / relative_path
            if candidate.exists():
                return str(candidate)
    return relative_path

def beep(freq, dur):
    if winsound:
        def _play():
            try:
                winsound.Beep(freq, dur)
            except Exception:
                pass
        if threading.current_thread() is threading.main_thread():
            threading.Thread(target=_play, daemon=True).start()
        else:
            _play()

def send_notification(title, message):
    if HAS_PLYER:
        try:
            notification.notify(title=title, message=message, app_name="Beytarchiver", timeout=5)
        except Exception:
            pass

def get_path_size(path):
    if os.path.isfile(path): return os.path.getsize(path)
    total_size = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total_size += os.path.getsize(os.path.join(dirpath, f))
            except Exception:
                pass
    return total_size


def open_in_explorer(path):
    if not os.path.exists(path): return
    if os.path.isfile(path): path = os.path.dirname(path)
    if sys.platform == "win32": os.startfile(path)
    elif sys.platform == "darwin": subprocess.Popen(["open", path])
    else: subprocess.Popen(["xdg-open", path])


def load_config():
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(data):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".beyt-config-", dir=CONFIG_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, CONFIG_FILE)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    except Exception:
        pass


def parse_version(text):
    parts = []
    for token in str(text).split(".")[:4]:
        digits = ""
        for ch in token:
            if ch.isdigit():
                digits += ch
            elif digits:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def send_to_recycle_bin(paths):
    """Windows: dosyaları Geri Dönüşüm Kutusu'na taşır (FOF_ALLOWUNDO)."""
    if sys.platform != "win32":
        raise OSError("Geri Dönüşüm Kutusu yalnızca Windows'ta desteklenir.")
    existing = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not existing:
        return 0

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.c_int),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    FO_DELETE = 0x0003
    FOF_SILENT = 0x0004
    FOF_NOCONFIRMATION = 0x0010
    FOF_ALLOWUNDO = 0x0040

    operation = SHFILEOPSTRUCTW()
    operation.wFunc = FO_DELETE
    operation.pFrom = "\0".join(existing) + "\0\0"
    operation.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result or operation.fAnyOperationsAborted:
        raise OSError(f"Geri Dönüşüm Kutusu işlemi başarısız (kod {result}).")
    return len(existing)


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
        "ram": "⚡ Bellek Azalt", "updater": "🔄 Güncelleyici", "antivirus": "🛡️ Dosya Kontrol",
        "cleaner": "🧹 Temizleyici", "analyzer": "📊 Disk Analizi", "duplicates": "👥 Çift Dosya",
        "shredder": "🔥 Güvenli Sil", "organizer": "📁 Düzenleyici", "startup": "🚀 Başlangıç",
        "hash": "🧮 Hash", "settings": "⚙️ Ayarlar", "monitor": "📈 İzleyici", "passwords": "🔑 Şifreler",
        "tb_add": "➕ Ekle", "tb_extract": "📂 Çıkart", "tb_vault": "🔐 Kasa", "tb_ram": "⚡ Bellek",
        "tb_monitor": "📈 İzleyici", "tb_transfer": "📱 Telefon", "tb_av": "🛡️ Kontrol",
        "tb_cleaner": "🧹 Temizleyici", "tb_passwords": "🔑 Şifreler", "tb_news": "📌 Yenilikler", "tb_settings": "⚙️ Ayarlar",
        "drop_compress": "Sıkıştırılacak dosya ve klasörleri buraya sürükleyin",
        "drop_extract": "Çıkartılacak arşivi (.zip, .7z, .tar, .beyt) buraya sürükleyin",
        "start_compress": "🚀 Sıkıştırmayı Başlat", "start_extract": "📂 Tümünü Çıkart",
        "password": "Şifre (Opsiyonel)", "password_req": "Şifre (Gerekliyse)",
        "theme": "Görünüm Modu:", "color_palette": "Renk Teması / Palette:", "language": "Dil / Language:",
        "junk_sub": "Temizlenebilir Sistem Çöpü", "scan": "🔍 Tara", "clean": "🧹 Temizle",
        "av_title": f"🛡️ Beytarchiver Dosya Kontrolü v{CURRENT_VERSION}",
        "av_sub": "EICAR Test İmzası & Uzantı Sezgisel Kontrolü",
        "av_select": "🔍 Taranacak Dosya Seç", "no_file": "Dosya Seçilmedi",
        "ram_title": "⚡ Uygulama Bellek Azaltıcı",
        "ram_btn": "⚡ Uygulamanın Bellek Kullanımını Azalt",
        "ram_done": "✅ Uygulamanın çalışma kümesi (RAM kullanımı) azaltıldı!",
        "monitor_title": "📈 Sistem Kaynak İzleyicisi",
        "vault_title": "🔐 Beytarchiver Encrypted Vault (.beyt)",
        "vault_btn": "🔐 Dosyaları Seç ve .beyt Kasası Oluştur",
        "updater_btn": "🔍 Eski Sürüm Yazılımları Tara (winget)",
        "analyzer_btn": "📁 Taranacak Klasörü/Sürücüyü Seç",
        "dup_btn": "🔍 Klasör Seç ve Çift Dosyaları Tara",
        "dup_select_copies": "🎯 Kopyaları Seç (Orijinal Korunur)",
        "dup_recycle": "🗑️ Geri Dönüşüme Gönder",
        "dup_perm": "🔥 Kalıcı Sil",
        "dup_delete_title": "Çift Dosya Silme Onayı",
        "dup_confirm_recycle": "Seçili {count} kopya dosya Geri Dönüşüm Kutusu'na gönderilecek. Devam edilsin mi?",
        "dup_confirm_perm": "Seçili {count} kopya dosya KALICI OLARAK silinecek (geri alınamaz). Devam edilsin mi?",
        "dup_no_selection": "Önce silinecek kopya dosyaları seçin (veya 'Kopyaları Seç' düğmesini kullanın).",
        "dup_deleted": "✅ {count} dosya silindi.",
        "dup_delete_fail": "⚠️ {count} dosya silinemedi.",
        "dup_summary": "Tarama Bitti: {groups} grup, {copies} silinebilir kopya bulundu!",
        "dup_selected": "🎯 {count} kopya seçildi (orijinaller korunuyor).",
        "dup_original_tag": "  ⭐ (orijinal)",
        "shred_title": "🔥 Dosyanın Üzerine Yaz ve Sil",
        "shred_btn": "🔥 Kalıcı Olarak İmha Edilecek Dosyayı Seç",
        "org_title": "📁 Akıllı Masaüstü ve Klasör Düzenleyici",
        "org_desktop": "🖥️ Masaüstünü Düzenle",
        "org_downloads": "📥 İndirilenler Klasörünü Düzenle",
        "org_undo": "↩️ Geri Al (Son Düzenleme)",
        "org_undo_title": "Düzenlemeyi Geri Al",
        "org_undo_confirm": "Son düzenleme işlemi geri alınacak; {count} dosya eski konumuna taşınacak. Devam edilsin mi?",
        "org_undo_progress": "Geri alınıyor...",
        "org_undo_done": "✅ Geri alma tamamlandı: {count} dosya eski konumuna döndürüldü.",
        "org_undo_fail": "⚠️ {count} dosya geri taşınamadı (hedefte çakışma veya erişim hatası).",
        "startup_title": "🚀 Windows Başlangıç Uygulamaları",
        "hash_btn": "🔍 Hash Hesaplanacak Dosyayı Seç",
        "check_update": "🔄 Güncellemeleri Kontrol Et",
        "update_checking": "Kontrol ediliyor...",
        "update_latest": "✅ Güncel sürümü kullanıyorsunuz (v{version}).",
        "update_error": "Güncelleme kontrolü başarısız: {err}",
        "update_repo_missing": "GitHub depo adresi yapılandırılmamış (koddaki GITHUB_REPO sabitini doldurun).",
        "update_available_title": "🎉 Yeni Sürüm Kullanılabilir: v{version}",
        "update_download_btn": "⬇️ Kurulum Dosyasını İndir",
        "update_downloading": "İndiriliyor: %{pct}",
        "update_downloaded": "✅ İndirildi: {path}",
        "update_no_asset": "Bu sürümde indirilebilir kurulum dosyası (.exe) bulunamadı.",
        "update_close_btn": "Daha Sonra",
        "update_title": f"🚀 Beytarchiver v{CURRENT_VERSION} Pro Güncelleme Raporu",
        "update_notes": (
            "📌 SÜRÜM GELİŞİM GEÇMİŞİ (v1.0 ➔ v4.0.2)\n"
            "══════════════════════════════════════════════════════════\n\n"
            "✨ v4.0.2 (Güncel Sürüm — 24 Ekim 2026):\n"
            "• 👥 ÇİFT DOSYA TOPLU İŞLEM: Tarama sonrası en eski dosya orijinal olarak korunur; tüm kopyalar tek tıkla seçilip Geri Dönüşüm Kutusu'na gönderilebilir veya kalıcı silinebilir.\n"
            "• ↩️ DÜZENLEYİCİ GERİ AL: Akıllı Düzenleyici son taşıma işlemini kaydeder ve tek tıkla tüm dosyaları eski konumlarına döndürür.\n"
            "• 💾 KALICI AYARLAR: Dil (TR/EN), görünüm modu (Dark/Light) ve renk teması config.json dosyasına kaydedilir; uygulama açılışında otomatik geri yüklenir.\n"
            "• 🔄 OTOMATİK GÜNCELLEME: GitHub Releases API ile yeni sürüm kontrolü ve kurulum dosyasını tek tıkla indirme desteği.\n\n"
            "✨ v4.0.1 (18 Ekim 2026):\n"
            "• 🧹 SİSTEM TEMİZLEYİCİ: Windows Temp ve AppData Temp klasörlerinin aynı dizini işaret ettiği durumlarda oluşan çift sayım hatası tamamen giderildi.\n"
            "• 📁 AKILLI DÜZENLEYİCİ: Masaüstü ve İndirilenler düzenleyicisine onay penceresi eklendi, işlem arka plan iş parçacığına taşındı ve aynı isimli dosyaların üzerine yazılması engellendi.\n"
            "• 📦 ARŞİVLEME: Arşiv dosyaları artık doğrudan kaynak dosyanın bulunduğu klasörün yanına kaydediliyor.\n"
            "• ⚡ PERFORMANS: Çift Dosya Bulucu boyuta göre ön-gruplama ile hızlandırıldı; Canlı Kaynak İzleyici sekme değiştiğinde otomatik duraklatılarak CPU tasarrufu sağlandı.\n"
            "• 🌐 ÇEVİRİ: Üst araç çubuğu, tüm alt paneller ve Telefonla Aktar modülü için eksiksiz TR/EN dil desteği tamamlandı.\n"
            "• 🧱 DAĞITIM: Nuitka yerel C derlemesi ve Inno Setup kurulum sihirbazı paketi hazırlandı.\n\n"
            "✨ v4.0 (LAN Transfer & Android Desteği):\n"
            "• 📱 TELEFONLA AKTAR: İnternete veya buluta ihtiyaç duymadan, aynı yerel ağdaki Android telefona doğrudan dosya aktarımı.\n"
            "• 🔗 GÜVENLİ EŞLEŞTİRME: 120 saniyede yenilenen QR kod, geçici TLS sertifikası sabitleme (certificate pinning) ve 6 haneli kod doğrulama.\n"
            "• ✅ UÇTAN UCA DOĞRULAMA: Aktarılan dosyada SHA-256 bütünlük kontrolü ve telefondan bilgisayara kayıt alındı onayı (receipt).\n\n"
            "✨ v3.7 (Ultimate Edition & Kararlılık):\n"
            "• 📈 CANLI İZLEYİCİ: Gerçek zamanlı grafiksel CPU ve RAM kullanım takibi.\n"
            "• 🔑 ŞİFRE YÖNETİCİSİ: scrypt + AES-256-GCM ile şifrelenen yerel kasa, 15 saniye şifre gösterimi ve sekmeden çıkınca otomatik kilitleme.\n"
            "• 🛡️ GÜVENLİ ÇIKARTMA: ZIP, 7z ve TAR arşivlerinde Path Traversal (../), sembolik link ve zip bombası korumaları.\n"
            "• 🔥 GÜVENLİ SİLİCİ (SHREDDER): Dosya üzerine 3 geçişli rastgele bayt yazarak kalıcı imha.\n"
            "• 🛠️ THREAD-SAFE UI QUEUE: Arka plan işlerinin arayüzü kilitlemesini ve çökmesini engelleyen kuyruk mimarisi.\n\n"
            "✨ v3.5 (Görsel Yenilikler & Özel Temalar):\n"
            "• 🖼️ LOGO & İKON: Yeni uygulama logosu ve Windows görev çubuğu / pencere ikonu entegrasyonu.\n"
            "• 🎨 11 RENK TEMASI: Catppuccin, Emerald, Cyberpunk, Nordic, Dracula, Sunset dahil 11 özel renk paleti ve Koyu/Açık mod uyumu.\n"
            "• 🔐 GİZLİ KASA (.beyt): Hassas dosyaları şifreleyerek tek bir güvenli .beyt kasasında saklama desteği.\n"
            "• ⚡ BELLEK AZALTICI: Uygulama çalışma kümesini tek tıkla boşaltma (EmptyWorkingSet).\n"
            "• 🔄 GÜNCELLEYİCİ: Windows Package Manager (winget) entegrasyonuyla eski yazılımları tarama.\n\n"
            "✨ v3.0 (Performans & Gelişmiş Araçlar):\n"
            "• 👥 ÇİFT DOSYA BULUCU: MD5 ve SHA-256 imzalarıyla yinelenen dosyaları tespit etme.\n"
            "• 📊 DİSK ANALİZİ: Seçilen klasördeki en büyük 50 dosyayı boyutuna göre listeleme.\n"
            "• 🚀 BAŞLANGIÇ YÖNETİCİSİ: Windows başlangıcında otomatik çalışan uygulamaları görüntüleme.\n\n"
            "✨ v2.5 & v2.0 (Güvenlik & Çoklu Format):\n"
            "• 📦 ÇOKLU ARŞİV: ZIP, 7z, TAR, GZ formatlarında sıkıştırma ve çıkarma motoru.\n"
            "• 🛡️ YEREL DOSYA KONTROLÜ: Şüpheli çift uzantıları (.pdf.exe) ve test imzalarını tespit eden sezgisel analiz motoru.\n"
            "• 🧮 HASH HESAPLAYICI: MD5, SHA-1 ve SHA-256 özetlerini tek tıkla çıkarma.\n\n"
            "✨ v1.0 (İlk Temel Sürüm):\n"
            "• Temel dosya arşivleme, modern Tkinter kullanıcı arayüzü ve ilk masaüstü yöneticisi mimarisi."
        ),
        "btn_close_update": "Harika, Başlayalım! 🚀"
    },
    "EN": {
        "transfer": "📱 Phone Transfer",
        "compress": "📦 Compress", "extract": "📂 Extract", "vault": "🔐 Vault",
        "ram": "⚡ Trim Memory", "updater": "🔄 Updater", "antivirus": "🛡️ File Check",
        "cleaner": "🧹 Cleaner", "analyzer": "📊 Disk Analyzer", "duplicates": "👥 Duplicates",
        "shredder": "🔥 Shredder", "organizer": "📁 Organizer", "startup": "🚀 Startup",
        "hash": "🧮 Hash", "settings": "⚙️ Settings", "monitor": "📈 Monitor", "passwords": "🔑 Passwords",
        "tb_add": "➕ Add", "tb_extract": "📂 Extract", "tb_vault": "🔐 Vault", "tb_ram": "⚡ Memory",
        "tb_monitor": "📈 Monitor", "tb_transfer": "📱 Phone", "tb_av": "🛡️ Check",
        "tb_cleaner": "🧹 Cleaner", "tb_passwords": "🔑 Passwords", "tb_news": "📌 Changelog", "tb_settings": "⚙️ Settings",
        "drop_compress": "Drag files and folders to compress here",
        "drop_extract": "Drag archive (.zip, .7z, .tar, .beyt) here",
        "start_compress": "🚀 Start Compression", "start_extract": "📂 Extract All",
        "password": "Password (Optional)", "password_req": "Password (If Required)",
        "theme": "Appearance Mode:", "color_palette": "Color Theme / Palette:", "language": "Language / Dil:",
        "junk_sub": "Cleanable System Junk", "scan": "🔍 Scan", "clean": "🧹 Clean",
        "av_title": f"🛡️ Beytarchiver File Check v{CURRENT_VERSION}",
        "av_sub": "EICAR Test Signature & Extension Heuristic Check",
        "av_select": "🔍 Select File to Scan", "no_file": "No File Selected",
        "ram_title": "⚡ Application Memory Trimmer",
        "ram_btn": "⚡ Reduce Application Memory Usage",
        "ram_done": "✅ Application working set (memory usage) reduced!",
        "monitor_title": "📈 System Resource Monitor",
        "vault_title": "🔐 Beytarchiver Encrypted Vault (.beyt)",
        "vault_btn": "🔐 Select Files and Create .beyt Vault",
        "updater_btn": "🔍 Scan Outdated Software (winget)",
        "analyzer_btn": "📁 Select Folder/Drive to Scan",
        "dup_btn": "🔍 Select Folder and Scan Duplicates",
        "dup_select_copies": "🎯 Select Copies (Keep Original)",
        "dup_recycle": "🗑️ Send to Recycle Bin",
        "dup_perm": "🔥 Delete Permanently",
        "dup_delete_title": "Duplicate Deletion Confirmation",
        "dup_confirm_recycle": "{count} selected duplicate file(s) will be sent to the Recycle Bin. Continue?",
        "dup_confirm_perm": "{count} selected duplicate file(s) will be PERMANENTLY deleted (irreversible). Continue?",
        "dup_no_selection": "Select duplicate files to delete first (or use the 'Select Copies' button).",
        "dup_deleted": "✅ {count} file(s) deleted.",
        "dup_delete_fail": "⚠️ {count} file(s) could not be deleted.",
        "dup_summary": "Scan Complete: {groups} group(s), {copies} deletable duplicate(s) found!",
        "dup_selected": "🎯 {count} duplicate(s) selected (originals kept).",
        "dup_original_tag": "  ⭐ (original)",
        "shred_title": "🔥 Overwrite and Delete File",
        "shred_btn": "🔥 Select File to Permanently Shred",
        "org_title": "📁 Smart Desktop and Folder Organizer",
        "org_desktop": "🖥️ Organize Desktop",
        "org_downloads": "📥 Organize Downloads",
        "org_undo": "↩️ Undo (Last Organize)",
        "org_undo_title": "Undo Organize",
        "org_undo_confirm": "The last organize operation will be undone; {count} file(s) will be moved back to their original locations. Continue?",
        "org_undo_progress": "Undoing...",
        "org_undo_done": "✅ Undo complete: {count} file(s) restored to their original locations.",
        "org_undo_fail": "⚠️ {count} file(s) could not be moved back (target conflict or access error).",
        "startup_title": "🚀 Windows Startup Applications",
        "hash_btn": "🔍 Select File to Calculate Hash",
        "check_update": "🔄 Check for Updates",
        "update_checking": "Checking...",
        "update_latest": "✅ You are on the latest version (v{version}).",
        "update_error": "Update check failed: {err}",
        "update_repo_missing": "GitHub repository is not configured (fill in the GITHUB_REPO constant in the code).",
        "update_available_title": "🎉 New Version Available: v{version}",
        "update_download_btn": "⬇️ Download Installer",
        "update_downloading": "Downloading: {pct}%",
        "update_downloaded": "✅ Downloaded: {path}",
        "update_no_asset": "No downloadable installer (.exe) found for this release.",
        "update_close_btn": "Later",
        "update_title": f"🚀 Beytarchiver v{CURRENT_VERSION} Pro Changelog",
        "update_notes": (
            "📌 VERSION CHANGELOG (v1.0 ➔ v4.0.2)\n"
            "══════════════════════════════════════════════════════════\n\n"
            "✨ v4.0.2 (Current Release — October 24, 2026):\n"
            "• 👥 DUPLICATE BULK ACTIONS: After a scan, the oldest file is kept as the original; all copies can be selected with one click and sent to the Recycle Bin or deleted permanently.\n"
            "• ↩️ ORGANIZER UNDO: The Smart Organizer now records the last move operation and restores every file to its original location with one click.\n"
            "• 💾 PERSISTENT SETTINGS: Language (TR/EN), appearance mode (Dark/Light), and color theme are saved to config.json and restored automatically on startup.\n"
            "• 🔄 AUTO UPDATE CHECK: New-version detection via the GitHub Releases API with one-click installer download.\n\n"
            "✨ v4.0.1 (October 18, 2026):\n"
            "• 🧹 SYSTEM CLEANER: Fixed duplicate counting between Windows Temp and AppData Temp when paths overlap.\n"
            "• 📁 SMART ORGANIZER: Added confirmation prompt, background worker thread, and safe duplicate renaming ( (1), (2)).\n"
            "• 📦 ARCHIVING: Archives now output directly next to the source folder.\n"
            "• ⚡ PERFORMANCE: Size-grouped duplicate scanner for faster scans; tab-scoped Resource Monitor pauses in background.\n"
            "• 🌐 LOCALIZATION: Full Turkish & English bilingual translation across toolbar, panels, and Phone Transfer.\n"
            "• 🧱 DISTRIBUTION: Native C compilation via Nuitka and one-click Inno Setup installer package.\n\n"
            "✨ v4.0 (LAN Transfer & Android Client):\n"
            "• 📱 PHONE TRANSFER: Direct PC-to-Android file transfer over local network without cloud servers or accounts.\n"
            "• 🔗 SECURE PAIRING: 120-second rotating QR code, ephemeral TLS certificate pinning, and 6-digit verification code.\n"
            "• ✅ INTEGRITY VERIFICATION: End-to-end SHA-256 verification and client delivery receipt acknowledgement.\n\n"
            "✨ v3.7 (Ultimate Edition & Hardened Security):\n"
            "• 📈 RESOURCE MONITOR: Live CPU and RAM usage tracking.\n"
            "• 🔑 PASSWORD MANAGER: Master-password protected (scrypt + AES-256-GCM) vault with 15-second reveal and auto-lock.\n"
            "• 🛡️ HARDENED EXTRACTION: Path Traversal (../), symlink, and zip-bomb rejection across ZIP, 7z, and TAR.\n"
            "• 🔥 FILE SHREDDER: 3-pass secure overwrite and delete engine.\n"
            "• 🛠️ THREAD-SAFE UI QUEUE: Eliminates Tkinter race conditions and freezes during intensive scans.\n\n"
            "✨ v3.5 (Visuals & Custom Themes):\n"
            "• 🖼️ LOGO & ICONS: In-app brand logo and Windows taskbar / title bar icon integration.\n"
            "• 🎨 11 COLOR THEMES: Catppuccin, Emerald, Cyberpunk, Nordic, Dracula, Sunset palettes with Dark/Light modes.\n"
            "• 🔐 ENCRYPTED VAULT (.beyt): AES-256 encrypted multi-file container creation and extraction.\n"
            "• ⚡ MEMORY TRIMMER: Working set reduction (EmptyWorkingSet) with single click.\n"
            "• 🔄 SOFTWARE UPDATER: Integrated winget engine for outdated software scans.\n\n"
            "✨ v3.0 (Performance & Advanced Utilities):\n"
            "• 👥 DUPLICATE FINDER: MD5 and SHA-256 duplicate file detector.\n"
            "• 📊 DISK ANALYZER: Identifies top 50 largest files in any folder or drive.\n"
            "• 🚀 STARTUP MANAGER: Lists Windows startup registry entries.\n\n"
            "✨ v2.5 & v2.0 (Multi-Format & Security Engines):\n"
            "• 📦 MULTI-ARCHIVE: ZIP, 7z, TAR, GZ compression and decompression engines with Drag & Drop.\n"
            "• 🛡️ FILE CHECK: Heuristic engine detecting masked extensions (.pdf.exe) and test signatures.\n"
            "• 🧮 HASH CALCULATOR: Instant MD5, SHA-1, and SHA-256 calculation.\n\n"
            "✨ v1.0 (Initial Release):\n"
            "• Core file archiving, modern Tkinter GUI, and foundational desktop manager framework."
        ),
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
        except Exception:
            return None

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
class BeytarchiverApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"Beytarchiver v{CURRENT_VERSION} Pro Enterprise")
        self.geometry("1300x900")
        self.minsize(1100, 800)

        ico_path = resource_path("logo.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        # --- Kalıcı Ayarları Yükle (config.json) ---
        self.config_data = load_config()
        saved_lang = self.config_data.get("language")
        self.current_lang = saved_lang if saved_lang in LANGUAGES else "TR"
        saved_palette = self.config_data.get("palette")
        self.active_palette_name = saved_palette if saved_palette in COLOR_THEMES else "Catppuccin (Varsayılan)"
        saved_mode = str(self.config_data.get("appearance_mode", "dark")).lower()
        ctk.set_appearance_mode(saved_mode if saved_mode in ("dark", "light", "system") else "dark")
        ctk.set_default_color_theme("blue")

        self.av_engine = BeytNativeAntivirus()

        # Thread-Safe UI Queue (Parametre çökmelerini kesin engelleyen yapı)
        self.ui_queue = Queue()
        self._closing = False
        self._queue_after = None
        self._password_after = None
        self._reveal_after = None
        self._password_sites = {}
        self.monitor_running = False
        self._downloading_update = False
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
        self._organizing = False
        self._undo_moves = []
        self.dup_groups = []
        self.dup_item_paths = {}

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

        self.lbl_stats = ctk.CTkLabel(self.status_bar, text=f"Beytarchiver v{CURRENT_VERSION} Pro Enterprise Active", font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        self.lbl_stats.pack(side="right", padx=10)

        self.show_view("compress")
        self.after(500, self.check_first_launch_update)
        self.after(3000, lambda: self.check_for_updates(silent=True))

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
        self.persist_settings()
        self.transfer_panel.shutdown()
        self.monitor_running = False
        self.lock_passwords()
        if self._queue_after is not None:
            self.after_cancel(self._queue_after)
        self.destroy()

    def t(self, key):
        return LANGUAGES.get(self.current_lang, {}).get(key, key)

    def persist_settings(self):
        self.config_data.update({
            "language": self.current_lang,
            "appearance_mode": str(ctk.get_appearance_mode()).lower(),
            "palette": self.active_palette_name,
        })
        save_config(self.config_data)

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
        self.persist_settings()

    def change_appearance_mode(self, new_mode):
        ctk.set_appearance_mode(new_mode.lower())
        self.apply_color_palette()

    def check_first_launch_update(self):
        last_version = ""
        if os.path.exists(VERSION_FILE):
            try:
                with open(VERSION_FILE, "r", encoding="utf-8") as f:
                    last_version = f.read().strip()
            except Exception:
                pass
        if last_version != CURRENT_VERSION: self.show_update_notes_dialog()

    def show_update_notes_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title(self.t("update_title"))
        dialog.geometry("720x560")
        dialog.minsize(600, 480)
        dialog.transient(self)
        dialog.grab_set()

        lbl_title = ctk.CTkLabel(dialog, text=self.t("update_title"), font=ctk.CTkFont(size=20, weight="bold"), text_color="#89B4FA")
        lbl_title.pack(pady=(20, 10))

        txt_box = ctk.CTkTextbox(dialog, corner_radius=10, font=ctk.CTkFont(size=13))
        txt_box.pack(pady=10, padx=20, fill="both", expand=True)
        txt_box.insert("end", self.t("update_notes"))
        txt_box.configure(state="disabled")

        def close_and_save():
            try:
                with open(VERSION_FILE, "w", encoding="utf-8") as f:
                    f.write(CURRENT_VERSION)
            except Exception:
                pass
            dialog.destroy()

        btn_ok = ctk.CTkButton(dialog, text=self.t("btn_close_update"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(size=14, weight="bold"), height=38, command=close_and_save)
        btn_ok.pack(pady=(5, 20))

    # ==========================================
    # 🔄 OTOMATİK GÜNCELLEME KONTROLÜ (GitHub Releases)
    # ==========================================
    def check_for_updates(self, silent=False):
        if self._downloading_update:
            return
        if not silent:
            self.lbl_update_status.configure(text=self.t("update_checking"), text_color="#89B4FA")
        threading.Thread(target=self.update_check_engine, args=(silent,), daemon=True).start()

    def update_check_engine(self, silent):
        if not GITHUB_REPO or "/" not in GITHUB_REPO:
            if not silent:
                self.safe_ui_update(self.lbl_update_status.configure,
                                    text=self.t("update_repo_missing"), text_color="#F38BA8")
            return
        try:
            request = urllib.request.Request(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"User-Agent": f"Beytarchiver/{CURRENT_VERSION}",
                         "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(request, timeout=15) as response:
                release = json.loads(response.read().decode("utf-8"))
            tag = str(release.get("tag_name", "")).lstrip("vV")
            if parse_version(tag) > parse_version(CURRENT_VERSION):
                asset_url, asset_name = "", ""
                for asset in release.get("assets", []):
                    name = str(asset.get("name", ""))
                    if name.lower().endswith(".exe"):
                        asset_url = str(asset.get("browser_download_url", ""))
                        asset_name = name
                        break
                self.safe_ui_update(self.show_update_available_dialog, tag,
                                    str(release.get("body", ""))[:4000], asset_url, asset_name)
            elif not silent:
                self.safe_ui_update(self.lbl_update_status.configure,
                                    text=self.t("update_latest").format(version=CURRENT_VERSION),
                                    text_color="#A6E3A1")
        except Exception as exc:
            if not silent:
                self.safe_ui_update(self.lbl_update_status.configure,
                                    text=self.t("update_error").format(err=exc), text_color="#F38BA8")

    def show_update_available_dialog(self, tag, body, asset_url, asset_name):
        dialog = ctk.CTkToplevel(self)
        dialog.title(self.t("update_available_title").format(version=tag))
        dialog.geometry("640x480")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=self.t("update_available_title").format(version=tag),
                     font=ctk.CTkFont(size=18, weight="bold"), text_color="#A6E3A1").pack(pady=(20, 5))

        txt_box = ctk.CTkTextbox(dialog, corner_radius=10, font=ctk.CTkFont(size=13))
        txt_box.pack(pady=10, padx=20, fill="both", expand=True)
        txt_box.insert("end", body or "—")
        txt_box.configure(state="disabled")

        def start_download():
            dialog.destroy()
            self.download_update_asset(asset_url, asset_name or f"beytarchiver_v{tag}_setup.exe")

        if asset_url:
            ctk.CTkButton(dialog, text=self.t("update_download_btn"), fg_color="#A6E3A1",
                          text_color="#11111B", font=ctk.CTkFont(size=14, weight="bold"),
                          height=38, command=start_download).pack(pady=(5, 5))
        else:
            ctk.CTkLabel(dialog, text=self.t("update_no_asset"),
                         font=ctk.CTkFont(size=12), text_color="#F9E2AF").pack(pady=(5, 0))
        ctk.CTkButton(dialog, text=self.t("update_close_btn"), fg_color="#313244",
                      height=32, command=dialog.destroy).pack(pady=(0, 15))

    def download_update_asset(self, url, filename):
        if self._downloading_update:
            return
        safe_name = "".join(ch for ch in ntpath.basename(filename)
                            if ch.isalnum() or ch in "._- ") or "beytarchiver_update.exe"
        self._downloading_update = True
        self.lbl_update_status.configure(text=self.t("update_downloading").format(pct=0),
                                         text_color="#89B4FA")
        threading.Thread(target=self.download_update_engine, args=(url, safe_name), daemon=True).start()

    def download_update_engine(self, url, filename):
        try:
            dest = Path.home() / "Downloads" / filename
            request = urllib.request.Request(url, headers={"User-Agent": f"Beytarchiver/{CURRENT_VERSION}"})
            with urllib.request.urlopen(request, timeout=60) as response, open(dest, "wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = min(100, int(done * 100 / total))
                        self.safe_ui_update(self.lbl_update_status.configure,
                                            text=self.t("update_downloading").format(pct=pct),
                                            text_color="#89B4FA")
            self.safe_ui_update(self.finish_update_download, dest)
        except Exception as exc:
            self.safe_ui_update(self.lbl_update_status.configure,
                                text=self.t("update_error").format(err=exc), text_color="#F38BA8")
        finally:
            self._downloading_update = False

    def finish_update_download(self, dest):
        self.lbl_update_status.configure(text=self.t("update_downloaded").format(path=dest),
                                         text_color="#A6E3A1")
        beep(1200, 300)
        send_notification("Beytarchiver", self.t("update_downloaded").format(path=dest.name))
        open_in_explorer(dest)

    def change_language(self, new_lang):
        self.current_lang = new_lang
        self.update_ui_language()
        self.persist_settings()

    def update_ui_language(self):
        for key, btn in self.nav_btns.items(): btn.configure(text=self.t(key))
        for key, btn in getattr(self, "tb_btns", {}).items(): btn.configure(text=self.t(key))
        self.drop_lbl.configure(text=self.t("drop_compress"))
        self.extract_drop_lbl.configure(text=self.t("drop_extract"))
        self.btn_start.configure(text=self.t("start_compress"))
        self.btn_start_extract.configure(text=self.t("start_extract"))
        self.entry_pass.configure(placeholder_text=self.t("password"))
        self.entry_ext_pass.configure(placeholder_text=self.t("password_req"))
        self.lbl_av_status.configure(text=self.t("av_title"))
        self.lbl_av_sub.configure(text=self.t("av_sub"))
        self.btn_select_av_file.configure(text=self.t("av_select"))
        self.lbl_hero_sub.configure(text=self.t("junk_sub"))
        if not self._cleaning:
            self.btn_scan_clean.configure(text=self.t("scan"))
            self.btn_do_clean.configure(text=self.t("clean"))
        self.lbl_ram_title.configure(text=self.t("ram_title"))
        self.btn_clean_ram.configure(text=self.t("ram_btn"))
        self.lbl_monitor_title.configure(text=self.t("monitor_title"))
        self.lbl_vault_title.configure(text=self.t("vault_title"))
        self.btn_create_vault.configure(text=self.t("vault_btn"))
        self.btn_scan_updater.configure(text=self.t("updater_btn"))
        self.btn_select_ana_dir.configure(text=self.t("analyzer_btn"))
        self.btn_scan_dup.configure(text=self.t("dup_btn"))
        self.btn_dup_select.configure(text=self.t("dup_select_copies"))
        self.btn_dup_recycle.configure(text=self.t("dup_recycle"))
        self.btn_dup_perm.configure(text=self.t("dup_perm"))
        self.lbl_shred_title.configure(text=self.t("shred_title"))
        self.btn_shred_select.configure(text=self.t("shred_btn"))
        self.lbl_org_title.configure(text=self.t("org_title"))
        self.btn_org_desktop.configure(text=self.t("org_desktop"))
        self.btn_org_downloads.configure(text=self.t("org_downloads"))
        self.btn_org_undo.configure(text=self.t("org_undo"))
        self.lbl_startup_title.configure(text=self.t("startup_title"))
        self.btn_select_hash.configure(text=self.t("hash_btn"))
        self.lbl_settings_header.configure(text="⚙️ " + self.t("settings"))
        self.lbl_theme_title.configure(text=self.t("theme"))
        self.lbl_palette_title.configure(text=self.t("color_palette"))
        self.lbl_lang_title.configure(text=self.t("language"))
        self.btn_check_update.configure(text=self.t("check_update"))
        if hasattr(self, "transfer_panel") and hasattr(self.transfer_panel, "set_language"):
            self.transfer_panel.set_language(self.current_lang)

    def build_toolbar(self):
        self.toolbar = ctk.CTkFrame(self, height=65, corner_radius=0, fg_color="#1E1E2E")
        self.toolbar.grid(row=0, column=0, sticky="ew")

        png_path = resource_path("logo.png")
        if HAS_PIL and os.path.exists(png_path):
            try:
                img = Image.open(png_path)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(38, 38))
                lbl_logo = ctk.CTkLabel(self.toolbar, image=ctk_img, text="")
                lbl_logo.pack(side="left", padx=(12, 5), pady=10)
            except Exception:
                pass
        else:
            lbl_logo_text = ctk.CTkLabel(self.toolbar, text=f"⚡ BEYT v{CURRENT_VERSION}", font=ctk.CTkFont(size=16, weight="bold"), text_color="#89B4FA")
            lbl_logo_text.pack(side="left", padx=(15, 10), pady=10)

        self.tb_btns = {
            "tb_add": self.create_tb_btn(self.t("tb_add"), self.select_compress_files),
            "tb_extract": self.create_tb_btn(self.t("tb_extract"), lambda: self.show_view("extract")),
            "tb_vault": self.create_tb_btn(self.t("tb_vault"), lambda: self.show_view("vault")),
            "tb_ram": self.create_tb_btn(self.t("tb_ram"), lambda: self.show_view("ram")),
            "tb_monitor": self.create_tb_btn(self.t("tb_monitor"), lambda: self.show_view("monitor")),
            "tb_transfer": self.create_tb_btn(self.t("tb_transfer"), lambda: self.show_view("transfer")),
            "tb_av": self.create_tb_btn(self.t("tb_av"), lambda: self.show_view("antivirus")),
            "tb_cleaner": self.create_tb_btn(self.t("tb_cleaner"), lambda: self.show_view("cleaner")),
            "tb_passwords": self.create_tb_btn(self.t("tb_passwords"), lambda: self.show_view("passwords")),
            "tb_news": self.create_tb_btn(self.t("tb_news"), self.show_update_notes_dialog),
            "tb_settings": self.create_tb_btn(self.t("tb_settings"), lambda: self.show_view("settings")),
        }

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
        if view_name != 'monitor':
            self.monitor_running = False
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
        self.lbl_monitor_title = ctk.CTkLabel(top, text=self.t("monitor_title"), font=ctk.CTkFont(size=20, weight="bold"), text_color="#89B4FA")
        self.lbl_monitor_title.pack(pady=(15, 0))

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
                except Exception:
                    pass
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
            if getattr(self, "_closing", True) is False and hasattr(self, "tk"):
                if not messagebox.askyesno("Şifre Silme Onayı", f"'{site}' kaydı kalıcı olarak silinsin mi?", default="no", parent=self):
                    return
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
            first_parent = Path(files[0]).resolve().parent if files else Path.cwd()
            target_dir = first_parent if first_parent.is_dir() and os.access(first_parent, os.W_OK) else Path.cwd()
            out_name = str(target_dir / f"beyt_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}")
            used_names = set()
            all_entries = []
            
            for item in files:
                if os.path.isfile(item):
                    arcname = unique_arcname(os.path.basename(item), used_names)
                    all_entries.append((item, arcname))
                elif os.path.isdir(item):
                    for root, _, dir_files in os.walk(item):
                        for f in dir_files:
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
        self.lbl_vault_title = ctk.CTkLabel(top, text=self.t("vault_title"), font=ctk.CTkFont(size=20, weight="bold"), text_color="#89B4FA")
        self.lbl_vault_title.pack(pady=(15, 0))
        body = ctk.CTkFrame(self.vault_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)
        self.entry_vault_pass = ctk.CTkEntry(body, placeholder_text="Kasa İçin Güçlü Parola Girin", show="*", width=250)
        self.entry_vault_pass.pack(pady=20)
        self.btn_create_vault = ctk.CTkButton(body, text=self.t("vault_btn"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.create_vault)
        self.btn_create_vault.pack(pady=10)
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
            first_parent = Path(files[0]).resolve().parent if files else Path.cwd()
            target_dir = first_parent if first_parent.is_dir() and os.access(first_parent, os.W_OK) else Path.cwd()
            out_name = str(target_dir / f"secure_vault_{datetime.now().strftime('%Y%m%d_%H%M%S')}.beyt")
            used_names = set()
            with pyzipper.AESZipFile(out_name, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
                zf.setpassword(pwd.encode())
                for f in files:
                    zf.write(f, unique_arcname(os.path.basename(f), used_names))
            self.safe_ui_update(self.lbl_vault_status.configure, text=f"✅ Kasa Oluşturuldu: {out_name}", text_color="#A6E3A1")
            beep(1000, 300)
        except Exception as e:
            self.safe_ui_update(self.lbl_vault_status.configure, text=f"Hata: {e}", text_color="#F38BA8")

    def build_ram_view(self):
        self.ram_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.ram_panel, corner_radius=12, fg_color="#1E1E2E", height=90)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)
        self.lbl_ram_title = ctk.CTkLabel(top, text=self.t("ram_title"), font=ctk.CTkFont(size=20, weight="bold"), text_color="#A6E3A1")
        self.lbl_ram_title.pack(pady=(15, 0))
        body = ctk.CTkFrame(self.ram_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)
        self.btn_clean_ram = ctk.CTkButton(body, text=self.t("ram_btn"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(size=14, weight="bold"), command=self.clean_ram)
        self.btn_clean_ram.pack(pady=30)
        self.lbl_ram_status = ctk.CTkLabel(body, text="Hazır", font=ctk.CTkFont(size=13))
        self.lbl_ram_status.pack(pady=10)

    def clean_ram(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.psapi.EmptyWorkingSet(-1)
                self.safe_ui_update(self.lbl_ram_status.configure, text=self.t("ram_done"), text_color="#A6E3A1")
                beep(1200, 200)
            except Exception as e:
                self.safe_ui_update(self.lbl_ram_status.configure, text=f"Hata: {e}", text_color="#F38BA8")

    def build_updater_view(self):
        self.updater_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.updater_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 10))
        self.btn_scan_updater = ctk.CTkButton(top, text=self.t("updater_btn"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=lambda: threading.Thread(target=self.updater_engine, daemon=True).start())
        self.btn_scan_updater.pack(side="left", padx=15, pady=12)
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
        self.safe_ui_update(self.av_box.insert, "end", f"🛡️ BEYTARCHIVER DOSYA KONTROLÜ\n")
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
        seen_dirs = set()
        candidates = []
        if self.chk_temp.get():
            sys_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
            candidates.append((os.path.join(sys_root, "Temp"), "Windows Temp"))
        if self.chk_user_temp.get():
            user_tmp = os.environ.get("TEMP") or os.path.expanduser(r"~\AppData\Local\Temp")
            candidates.append((user_tmp, "AppData Temp"))
        for raw_path, tag in candidates:
            if raw_path:
                norm_dir = os.path.normcase(os.path.abspath(raw_path))
                if norm_dir not in seen_dirs:
                    seen_dirs.add(norm_dir)
                    scan_paths.append((raw_path, tag))
        self._cleaning = True
        self.btn_scan_clean.configure(state='disabled', text='Taranıyor...')
        self.btn_do_clean.configure(state='disabled')
        threading.Thread(target=self.scan_engine, args=(tuple(scan_paths),), daemon=True).start()

    def scan_engine(self, scan_paths):
        self.safe_ui_update(self.clear_tree, self.clean_tree)
        junk_files, total = [], 0
        seen_files = set()
        for path, tag in scan_paths:
            if path and os.path.exists(path):
                try:
                    for root, dirs, dir_files in os.walk(path):
                        for f in dir_files:
                            fp = os.path.join(root, f)
                            norm_fp = os.path.normcase(os.path.abspath(fp))
                            if norm_fp in seen_files:
                                continue
                            try:
                                if os.path.islink(fp):
                                    continue
                                fsize = os.path.getsize(fp)
                                seen_files.add(norm_fp)
                                junk_files.append((fp, fsize))
                                total += fsize
                                self.safe_ui_update(self.clean_tree.insert, "", "end", values=(fp, format_size(fsize), tag))
                            except Exception:
                                pass
                except Exception:
                    pass
                
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
        self.btn_select_ana_dir = ctk.CTkButton(self.ana_top, text=self.t("analyzer_btn"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_disk_analysis)
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
        for root, _, dir_files in os.walk(target_dir):
            for f in dir_files:
                try:
                    file_list.append((f, os.path.getsize(os.path.join(root, f)), os.path.join(root, f)))
                except Exception:
                    pass
        
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
        self.btn_scan_dup = ctk.CTkButton(top, text=self.t("dup_btn"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_dup_scan)
        self.btn_scan_dup.pack(side="left", padx=10, pady=10)
        self.lbl_dup_status = ctk.CTkLabel(top, text="Klasör Seçilmedi", font=ctk.CTkFont(size=12))
        self.lbl_dup_status.pack(side="left", padx=10)

        actions = ctk.CTkFrame(self.duplicates_panel, corner_radius=10)
        actions.pack(fill="x", pady=(0, 8))
        self.btn_dup_select = ctk.CTkButton(actions, text=self.t("dup_select_copies"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(size=12, weight="bold"), command=self.select_dup_copies)
        self.btn_dup_select.pack(side="left", padx=10, pady=8)
        self.btn_dup_recycle = ctk.CTkButton(actions, text=self.t("dup_recycle"), fg_color="#F9E2AF", text_color="#11111B", font=ctk.CTkFont(size=12, weight="bold"), command=lambda: self.delete_selected_duplicates(permanent=False))
        self.btn_dup_recycle.pack(side="left", padx=5, pady=8)
        self.btn_dup_perm = ctk.CTkButton(actions, text=self.t("dup_perm"), fg_color="#F38BA8", text_color="#11111B", font=ctk.CTkFont(size=12, weight="bold"), command=lambda: self.delete_selected_duplicates(permanent=True))
        self.btn_dup_perm.pack(side="left", padx=5, pady=8)

        tree_frame = ctk.CTkFrame(self.duplicates_panel, corner_radius=10, fg_color="#181825")
        tree_frame.pack(fill="both", expand=True)
        columns = ("hash", "name", "size", "path")
        self.dup_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        self.dup_tree.heading("hash", text="Hash İmzası"); self.dup_tree.heading("name", text="Dosya Adı"); self.dup_tree.heading("size", text="Boyut"); self.dup_tree.heading("path", text="Konumu")
        self.dup_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        dup_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.dup_tree.yview)
        self.dup_tree.configure(yscroll=dup_scrollbar.set)
        dup_scrollbar.pack(side="right", fill="y")

    def start_dup_scan(self):
        target = filedialog.askdirectory()
        if target:
            self.lbl_dup_status.configure(text=f"Taranıyor: {target}", text_color="#89B4FA")
            threading.Thread(target=self.dup_scan_engine, args=(target,), daemon=True).start()

    def reset_dup_tree(self):
        self.clear_tree(self.dup_tree)
        self.dup_item_paths.clear()
        self.dup_groups = []

    def populate_dup_tree(self, groups):
        self.dup_groups = groups
        copies = 0
        for _hash, fsize, file_list in groups:
            sz = format_size(fsize)
            for idx, fp in enumerate(file_list):
                is_original = idx == 0
                name = os.path.basename(fp) + (self.t("dup_original_tag") if is_original else "")
                iid = self.dup_tree.insert("", "end", values=(_hash[:16] + "...", name, sz, fp))
                self.dup_item_paths[iid] = fp
                if not is_original:
                    copies += 1
        self.lbl_dup_status.configure(
            text=self.t("dup_summary").format(groups=len(groups), copies=copies),
            text_color="#A6E3A1")
        beep(1000, 200)

    def dup_scan_engine(self, target):
        self.safe_ui_update(self.reset_dup_tree)
        by_size = {}
        for root, _, dir_files in os.walk(target):
            for f in dir_files:
                fp = os.path.join(root, f)
                try:
                    if os.path.islink(fp):
                        continue
                    fsize = os.path.getsize(fp)
                    by_size.setdefault(fsize, []).append(fp)
                except Exception:
                    pass

        hashes = {}
        for fsize, candidates in by_size.items():
            if len(candidates) < 2:
                continue
            for fp in candidates:
                try:
                    h = self.av_engine.calculate_file_hash(fp)
                    if h:
                        hashes.setdefault((fsize, h), []).append(fp)
                except Exception:
                    pass

        groups = []
        for (fsize, h), file_list in hashes.items():
            if len(file_list) > 1:
                # En eski dosya orijinal kabul edilir ve korunur.
                try:
                    file_list.sort(key=os.path.getmtime)
                except OSError:
                    pass
                groups.append((h, fsize, file_list))
        groups.sort(key=lambda g: g[1], reverse=True)
        self.safe_ui_update(self.populate_dup_tree, groups)

    def select_dup_copies(self):
        originals = {group[2][0] for group in self.dup_groups if group[2]}
        iids = [iid for iid, path in self.dup_item_paths.items() if path not in originals]
        if not iids:
            return
        self.dup_tree.selection_set(iids)
        self.dup_tree.focus(iids[0])
        self.lbl_dup_status.configure(
            text=self.t("dup_selected").format(count=len(iids)), text_color="#89B4FA")

    def delete_selected_duplicates(self, permanent):
        iids = [iid for iid in self.dup_tree.selection() if iid in self.dup_item_paths]
        if not iids:
            messagebox.showinfo(self.t("dup_delete_title"), self.t("dup_no_selection"), parent=self)
            return
        confirm_key = "dup_confirm_perm" if permanent else "dup_confirm_recycle"
        if not messagebox.askyesno(self.t("dup_delete_title"),
                                   self.t(confirm_key).format(count=len(iids)),
                                   default="no", parent=self):
            return
        paths = [self.dup_item_paths[iid] for iid in iids]
        self.btn_dup_recycle.configure(state="disabled")
        self.btn_dup_perm.configure(state="disabled")
        threading.Thread(target=self.dup_delete_engine, args=(tuple(iids), tuple(paths), permanent), daemon=True).start()

    def dup_delete_engine(self, iids, paths, permanent):
        deleted, failed = [], 0
        if permanent:
            for iid, path in zip(iids, paths):
                try:
                    os.remove(path)
                    deleted.append(iid)
                except OSError:
                    failed += 1
        else:
            try:
                send_to_recycle_bin(paths)
                deleted = [iid for iid, path in zip(iids, paths) if not os.path.exists(path)]
            except OSError:
                pass
            failed = len(iids) - len(deleted)
        self.safe_ui_update(self.finish_dup_delete, deleted, failed)

    def finish_dup_delete(self, deleted, failed):
        for iid in deleted:
            self.dup_item_paths.pop(iid, None)
            if self.dup_tree.exists(iid):
                self.dup_tree.delete(iid)
        self.btn_dup_recycle.configure(state="normal")
        self.btn_dup_perm.configure(state="normal")
        msg = self.t("dup_deleted").format(count=len(deleted))
        if failed:
            msg += "  " + self.t("dup_delete_fail").format(count=failed)
        self.lbl_dup_status.configure(text=msg, text_color="#A6E3A1" if not failed else "#F38BA8")
        beep(1200, 200)

    def build_shredder_view(self):
        self.shredder_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.shredder_panel, corner_radius=12, fg_color="#1E1E2E", height=100)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)
        self.lbl_shred_title = ctk.CTkLabel(top, text=self.t("shred_title"), font=ctk.CTkFont(size=20, weight="bold"), text_color="#F38BA8")
        self.lbl_shred_title.pack(pady=(15, 0))
        
        body = ctk.CTkFrame(self.shredder_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)
        self.btn_shred_select = ctk.CTkButton(body, text=self.t("shred_btn"), fg_color="#F38BA8", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_shred)
        self.btn_shred_select.pack(pady=20)
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
        self.lbl_org_title = ctk.CTkLabel(top, text=self.t("org_title"), font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_org_title.pack(pady=15)
        
        body = ctk.CTkFrame(self.organizer_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)
        self.btn_org_desktop = ctk.CTkButton(body, text=self.t("org_desktop"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=lambda: self.organize_dir(os.path.expanduser("~/Desktop")))
        self.btn_org_desktop.pack(pady=15)
        self.btn_org_downloads = ctk.CTkButton(body, text=self.t("org_downloads"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=lambda: self.organize_dir(os.path.expanduser("~/Downloads")))
        self.btn_org_downloads.pack(pady=10)
        self.btn_org_undo = ctk.CTkButton(body, text=self.t("org_undo"), fg_color="#F9E2AF", text_color="#11111B", font=ctk.CTkFont(weight="bold"), state="disabled", command=self.undo_organize)
        self.btn_org_undo.pack(pady=10)
        self.lbl_org_status = ctk.CTkLabel(body, text="İşlem Bekleniyor", font=ctk.CTkFont(size=13))
        self.lbl_org_status.pack(pady=15)

    def organize_dir(self, target_path):
        if getattr(self, "_organizing", False):
            return
        if not os.path.exists(target_path):
            self.safe_ui_update(self.lbl_org_status.configure, text=f"Klasör bulunamadı: {target_path}", text_color="#F38BA8")
            return
        if hasattr(self, "tk"):
            if not messagebox.askyesno("Klasör Düzenleme Onayı",
                    f"{target_path}\n\nBu klasördeki dosyalar alt klasörlere (Belgeler, Resimler, Arşivler) taşınacak. Devam edilsin mi?",
                    default="no", parent=self):
                return
        self._organizing = True
        self.safe_ui_update(self.lbl_org_status.configure, text="Düzenleniyor...", text_color="#89B4FA")
        threading.Thread(target=self.organize_dir_engine, args=(target_path,), daemon=True).start()

    def organize_dir_engine(self, target_path):
        categories = {"Belgeler": [".pdf", ".docx", ".txt"], "Resimler": [".jpg", ".jpeg", ".png"], "Arşivler": [".zip", ".7z"]}
        moved, skipped = 0, 0
        moves = []
        try:
            for item in os.listdir(target_path):
                fp = os.path.join(target_path, item)
                if os.path.isfile(fp) and not os.path.islink(fp):
                    ext = os.path.splitext(item)[1].lower()
                    for cat, exts in categories.items():
                        if ext in exts:
                            cat_dir = os.path.join(target_path, cat)
                            os.makedirs(cat_dir, exist_ok=True)
                            base, ext_part = os.path.splitext(item)
                            dest = os.path.join(cat_dir, item)
                            n = 1
                            while os.path.lexists(dest):
                                dest = os.path.join(cat_dir, f"{base} ({n}){ext_part}")
                                n += 1
                            try:
                                shutil.move(fp, dest)
                                moves.append((fp, dest))
                                moved += 1
                            except OSError:
                                skipped += 1
                            break
            msg = f"✅ Başarılı! {moved} dosya kategorize edildi." + (f" ({skipped} atlandı)" if skipped else "")
            self.safe_ui_update(self.finish_organize, moves, msg)
            beep(1000, 200)
        except Exception as e:
            self.safe_ui_update(self.finish_organize, moves, f"Hata: {e}", True)
        finally:
            self._organizing = False

    def finish_organize(self, moves, msg, is_error=False):
        self._undo_moves = list(moves)
        self.btn_org_undo.configure(state="normal" if self._undo_moves else "disabled")
        self.lbl_org_status.configure(text=msg, text_color="#F38BA8" if is_error else "#A6E3A1")

    def undo_organize(self):
        if self._organizing or not self._undo_moves:
            return
        moves = list(self._undo_moves)
        if not messagebox.askyesno(self.t("org_undo_title"),
                                   self.t("org_undo_confirm").format(count=len(moves)),
                                   default="no", parent=self):
            return
        self._organizing = True
        self.btn_org_undo.configure(state="disabled")
        self.lbl_org_status.configure(text=self.t("org_undo_progress"), text_color="#89B4FA")
        threading.Thread(target=self.undo_organize_engine, args=(tuple(moves),), daemon=True).start()

    def undo_organize_engine(self, moves):
        restored, failed = 0, 0
        try:
            for src, dest in reversed(moves):
                try:
                    if os.path.exists(dest) and not os.path.lexists(src):
                        os.makedirs(os.path.dirname(src), exist_ok=True)
                        shutil.move(dest, src)
                        restored += 1
                    else:
                        failed += 1
                except OSError:
                    failed += 1
        finally:
            self._organizing = False
        self.safe_ui_update(self.finish_undo_organize, restored, failed)

    def finish_undo_organize(self, restored, failed):
        self._undo_moves = []
        self.btn_org_undo.configure(state="disabled")
        msg = self.t("org_undo_done").format(count=restored)
        if failed:
            msg += "  " + self.t("org_undo_fail").format(count=failed)
        self.lbl_org_status.configure(text=msg, text_color="#A6E3A1" if not failed else "#F9E2AF")
        beep(1000, 200)

    def build_startup_view(self):
        self.startup_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top = ctk.CTkFrame(self.startup_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 8))
        self.lbl_startup_title = ctk.CTkLabel(top, text=self.t("startup_title"), font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_startup_title.pack(side="left", padx=15, pady=10)
        
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
        self.btn_select_hash = ctk.CTkButton(top, text=self.t("hash_btn"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.select_hash_file)
        self.btn_select_hash.pack(side="left", padx=15, pady=12)
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
        try:
            md5, sha1, sha256 = hashlib.md5(), hashlib.sha1(), hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    md5.update(chunk); sha1.update(chunk); sha256.update(chunk)
            res = f"📄 Dosya: {os.path.basename(file_path)}\n\n📌 MD5:\n{md5.hexdigest()}\n\n📌 SHA-1:\n{sha1.hexdigest()}\n\n📌 SHA-256:\n{sha256.hexdigest()}\n"
        except Exception as e:
            res = f"❌ Dosya okunamadı ({os.path.basename(file_path)}):\n{e}\n"
        self.safe_ui_update(self.update_hash_box, res)

    def update_hash_box(self, text):
        self.hash_box.configure(state="normal")
        self.hash_box.delete("1.0", "end")
        self.hash_box.insert("end", text)
        self.hash_box.configure(state="disabled")

    def build_settings_view(self):
        self.settings_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        
        # Üst Başlık
        self.lbl_settings_header = ctk.CTkLabel(self.settings_panel, text="⚙️ " + self.t("settings"), font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_settings_header.pack(pady=(20, 10))

        # Şık Konteyner Kutu
        settings_container = ctk.CTkFrame(self.settings_panel, fg_color="#181825", corner_radius=15, width=400)
        settings_container.pack(pady=10, padx=20, fill="y", expand=True)
        
        # Görünüm Modu
        self.lbl_theme_title = ctk.CTkLabel(settings_container, text=self.t("theme"), font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_theme_title.pack(pady=(30, 5))
        self.theme_menu = ctk.CTkOptionMenu(settings_container, values=["Dark", "Light", "System"], command=self.change_appearance_mode, width=200)
        self.theme_menu.pack(pady=5, padx=50)
        # Mevcut modu ayarla
        current_mode = ctk.get_appearance_mode().capitalize()
        self.theme_menu.set(current_mode if current_mode in ["Dark", "Light"] else "System")
        
        # Renk Paleti
        self.lbl_palette_title = ctk.CTkLabel(settings_container, text=self.t("color_palette"), font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_palette_title.pack(pady=(20, 5))
        self.palette_menu = ctk.CTkOptionMenu(settings_container, values=list(COLOR_THEMES.keys()), command=self.apply_color_palette, width=200)
        self.palette_menu.set(self.active_palette_name)
        self.palette_menu.pack(pady=5, padx=50)
        
        # Dil Seçimi
        self.lbl_lang_title = ctk.CTkLabel(settings_container, text=self.t("language"), font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_lang_title.pack(pady=(20, 5))
        self.lang_menu = ctk.CTkOptionMenu(settings_container, values=["TR", "EN"], command=self.change_language, width=200)
        self.lang_menu.set(self.current_lang)
        self.lang_menu.pack(pady=5, padx=50)

        # Uygulama Güncellemesi (GitHub Releases)
        self.btn_check_update = ctk.CTkButton(settings_container, text=self.t("check_update"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(size=13, weight="bold"), command=lambda: self.check_for_updates(silent=False))
        self.btn_check_update.pack(pady=(20, 5), padx=50)
        self.lbl_update_status = ctk.CTkLabel(settings_container, text="", font=ctk.CTkFont(size=12), wraplength=340, justify="center")
        self.lbl_update_status.pack(pady=(0, 25), padx=20)

if __name__ == "__main__":
    app = BeytarchiverApp()
    app.mainloop()
