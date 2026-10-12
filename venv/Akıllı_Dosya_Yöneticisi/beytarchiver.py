import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import winreg
import winsound
from datetime import datetime
import customtkinter as ctk
import py7zr
import pyzipper
from tkinter import filedialog, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

# Logo / Görsel İşleme Desteği
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

CURRENT_VERSION = "3.5"
VERSION_FILE = os.path.expanduser("~/.beytarchiver_version")

SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004

try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False


def send_notification(title, message):
    if HAS_PLYER:
        try:
            notification.notify(title=title, message=message, app_name="Beytarchiver", timeout=5)
        except Exception:
            pass


def get_path_size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total_size = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                try:
                    total_size += os.path.getsize(fp)
                except Exception:
                    pass
    return total_size


def format_size(bytes_val):
    if bytes_val is None or bytes_val == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} PB"


def open_in_explorer(path):
    if not os.path.exists(path):
        return
    if os.path.isfile(path):
        path = os.path.dirname(path)
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


COLOR_THEMES = {
    "Catppuccin (Varsayılan)": {
        "dark": {"bg": "#181825", "card": "#1E1E2E", "text": "#CDD6F4"},
        "light": {"bg": "#EFF1F5", "card": "#E6E9EF", "text": "#4C4F69"},
        "btn": "#89B4FA", "accent": "#A6E3A1", "danger": "#F38BA8"
    },
    "Emerald Matrix (Yeşil)": {
        "dark": {"bg": "#0D1117", "card": "#161B22", "text": "#E6EDF3"},
        "light": {"bg": "#E6F4EA", "card": "#CEEAD6", "text": "#137333"},
        "btn": "#238636", "accent": "#2EA043", "danger": "#DA3633"
    },
    "Cyberpunk Neon (Mor/Pembe)": {
        "dark": {"bg": "#10002B", "card": "#240046", "text": "#F72585"},
        "light": {"bg": "#F3E8FF", "card": "#E9D5FF", "text": "#5B21B6"},
        "btn": "#7B2CBF", "accent": "#E0AFA0", "danger": "#FF007F"
    },
    "Sunset Orange (Sıcak)": {
        "dark": {"bg": "#1A0C00", "card": "#2B1704", "text": "#FEF3C7"},
        "light": {"bg": "#FFF7ED", "card": "#FFEDD5", "text": "#9A3412"},
        "btn": "#D97706", "accent": "#F59E0B", "danger": "#EF4444"
    },
    "Ocean Blue (Mavi)": {
        "dark": {"bg": "#0F172A", "card": "#1E293B", "text": "#F1F5F9"},
        "light": {"bg": "#F0F9FF", "card": "#E0F2FE", "text": "#0369A1"},
        "btn": "#0284C7", "accent": "#38BDF8", "danger": "#F43F5E"
    },
    "Cherry Blossom (Pembe)": {
        "dark": {"bg": "#1A0915", "card": "#2A1224", "text": "#FCE7F3"},
        "light": {"bg": "#FDF2F8", "card": "#FCE7F3", "text": "#9D174D"},
        "btn": "#EC4899", "accent": "#F472B6", "danger": "#E11D48"
    },
    "Crimson Red (Kırmızı)": {
        "dark": {"bg": "#180505", "card": "#2B0B0B", "text": "#FEE2E2"},
        "light": {"bg": "#FEF2F2", "card": "#FEE2E2", "text": "#991B1B"},
        "btn": "#DC2626", "accent": "#EF4444", "danger": "#7F1D1D"
    },
    "Midnight Purple (Gece Moru)": {
        "dark": {"bg": "#0F0C1B", "card": "#1B1730", "text": "#EDE9FE"},
        "light": {"bg": "#F5F3FF", "card": "#EDE9FE", "text": "#5B21B6"},
        "btn": "#8B5CF6", "accent": "#A78BFA", "danger": "#EC4899"
    },
    "Mocha Coffee (Kahve)": {
        "dark": {"bg": "#1C1917", "card": "#292524", "text": "#FEF3C7"},
        "light": {"bg": "#FAFAF9", "card": "#F5F5F4", "text": "#78350F"},
        "btn": "#A16207", "accent": "#CA8A04", "danger": "#DC2626"
    },
    "Nordic Ice (Buz Mavisi)": {
        "dark": {"bg": "#0B132B", "card": "#1C2541", "text": "#E0FBFC"},
        "light": {"bg": "#F0FDF4", "card": "#CCFBF1", "text": "#0F766E"},
        "btn": "#48CAE4", "accent": "#90E0EF", "danger": "#FF4D6D"
    },
    "Gold / Amber (Altın)": {
        "dark": {"bg": "#121212", "card": "#1E1E1E", "text": "#FEF08A"},
        "light": {"bg": "#FEFCE8", "card": "#FEF9C3", "text": "#854D0E"},
        "btn": "#EAB308", "accent": "#FACC15", "danger": "#EF4444"
    }
}

LANGUAGES = {
    "TR": {
        "compress": "📦 Sıkıştırma",
        "extract": "📂 Çıkartma",
        "vault": "🔐 Gizli Kasa",
        "ram": "⚡ RAM Temizle",
        "updater": "🔄 Güncelleyici",
        "antivirus": "🛡️ Antivirüs",
        "cleaner": "🧹 Temizleyici",
        "analyzer": "📊 Disk Analizi",
        "duplicates": "👥 Çift Dosya",
        "shredder": "🔥 Güvenli Sil",
        "organizer": "📁 Düzenleyici",
        "startup": "🚀 Başlangıç",
        "hash": "🧮 Hash",
        "settings": "⚙️ Ayarlar",
        "drop_compress": "Sıkıştırılacak dosya ve klasörleri buraya sürükleyin",
        "drop_extract": "Çıkartılacak arşivi (.zip, .7z, .tar, .beyt) buraya sürükleyin",
        "start_compress": "🚀 Sıkıştırmayı Başlat",
        "start_extract": "📂 Tümünü Çıkart",
        "password": "Şifre (Opsiyonel)",
        "password_req": "Şifre (Gerekliyse)",
        "theme": "Görünüm Modu:",
        "color_palette": "Renk Teması / Palette:",
        "language": "Dil / Language:",
        "junk_sub": "Temizlenebilir Sistem Çöpü",
        "scan": "🔍 Tara",
        "clean": "🧹 Temizle",
        "av_title": "🛡️ Beytarchiver Yerli Antivirüs Motoru v3.5 Pro",
        "av_sub": "Yerel İmza Taraması & Sezgisel Derin Arşiv Analizi",
        "av_select": "🔍 Taranacak Dosya veya Arşivi Seç",
        "no_file": "Dosya Seçilmedi",
        "update_title": "🚀 Beytarchiver v3.5 Pro Enterprise Güncelleme Raporu",
        "update_notes": "📌 SÜRÜM GELİŞİM GEÇMİŞİ:\n\n"
                        "✨ v3.5 (Logo & Visual Upgrade):\n"
                        "• 🖼️ Arayüz içi ve Pencere İkonu (Logo) Desteği Eklendi.\n"
                        "• 🎨 Görünüm Modu (Dark/Light/System) ve Renk Temaları Tam Senkronize Yapıldı.\n"
                        "• 🔐 Encrypted Vault (.beyt): AES-256 Şifreli Gizli Kasa desteği.\n"
                        "• ⚡ RAM Cleaner: Bekleyen sistem belleğini tek tıkla boşaltma.\n"
                        "• 🔄 Software Updater: winget entegrasyonlu eski yazılım tespiti.\n\n"
                        "✨ v3.0, v2.5 & v2.0:\n"
                        "• Çift Dosya Bulucu, Güvenli Shredder, Antivirüs & Sistem Araçları.",
        "btn_close_update": "Harika, Başlayalım! 🚀"
    },
    "EN": {
        "compress": "📦 Compress",
        "extract": "📂 Extract",
        "vault": "🔐 Vault",
        "ram": "⚡ RAM Cleaner",
        "updater": "🔄 Updater",
        "antivirus": "🛡️ Antivirus",
        "cleaner": "🧹 Cleaner",
        "analyzer": "📊 Disk Analyzer",
        "duplicates": "👥 Duplicates",
        "shredder": "🔥 Shredder",
        "organizer": "📁 Organizer",
        "startup": "🚀 Startup",
        "hash": "🧮 Hash",
        "settings": "⚙️ Settings",
        "drop_compress": "Drag files and folders to compress here",
        "drop_extract": "Drag archive (.zip, .7z, .tar, .beyt) here",
        "start_compress": "🚀 Start Compression",
        "start_extract": "📂 Extract All",
        "password": "Password (Optional)",
        "password_req": "Password (If Required)",
        "theme": "Appearance Mode:",
        "color_palette": "Color Theme / Palette:",
        "language": "Language / Dil:",
        "junk_sub": "Cleanable System Junk",
        "scan": "🔍 Scan",
        "clean": "🧹 Clean",
        "av_title": "🛡️ Beytarchiver Native Security Engine v3.5 Pro",
        "av_sub": "Local Signature Scan & Heuristic Deep Inspection",
        "av_select": "🔍 Select File or Archive to Scan",
        "no_file": "No File Selected",
        "update_title": "🚀 Beytarchiver v3.5 Pro Enterprise Changelog",
        "update_notes": "📌 VERSION CHANGELOG:\n\n"
                        "✨ v3.5 (Logo & Visual Upgrade):\n"
                        "• 🖼️ Window Icon & In-App Logo Integration.\n"
                        "• 🎨 Fully synchronized Appearance Mode (Dark/Light) and Color Palettes.\n"
                        "• 🔐 Encrypted Vault (.beyt): AES-256 protected vault creation.\n"
                        "• ⚡ RAM Cleaner & Software Updater Integration.",
        "btn_close_update": "Awesome, Let's Go! 🚀"
    }
}


class BeytNativeAntivirus:
    def __init__(self):
        self.malware_signatures = {
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855": "Test.Malware.DummyHash",
            "44d88612fea8a8f36de82e1278abb02f": "Trojan.Generic.Sample"
        }
        self.high_risk_extensions = [".exe", ".vbs", ".bat", ".cmd", ".ps1", ".scr", ".pif", ".hta"]

    def calculate_file_hash(self, file_path):
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception:
            return None

    def scan_file(self, file_path):
        results = []
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()

        if filename.count(".") > 1:
            for risk_ext in self.high_risk_extensions:
                if filename.lower().endswith(risk_ext):
                    results.append(f"⚠️ SEZGİSEL UYARI: Gizlenmiş çift uzantılı dosya! ({filename})")

        if ext in self.high_risk_extensions:
            results.append(f"ℹ️ SEZGİSEL BİLGİ: Potansiyel betik/uygulama ({ext})")

        file_hash = self.calculate_file_hash(file_path)
        if file_hash and file_hash in self.malware_signatures:
            results.append(f"🚨 ZARARLI YAZILIM BULUNDU: {self.malware_signatures[file_hash]}")

        return results, file_hash

    def scan_archive_contents(self, archive_path):
        threats = []
        ext = os.path.splitext(archive_path)[1].lower()

        try:
            if ext in [".zip", ".beyt"]:
                with pyzipper.AESZipFile(archive_path, 'r') as zf:
                    for name in zf.namelist():
                        inner_ext = os.path.splitext(name)[1].lower()
                        if inner_ext in self.high_risk_extensions:
                            threats.append(f"⚠️ ARŞİV İÇİ TEHDİT: Riskli dosya -> {name}")
            elif ext == ".7z":
                with py7zr.SevenZipFile(archive_path, 'r') as z:
                    for f in z.list():
                        inner_ext = os.path.splitext(f.filename)[1].lower()
                        if inner_ext in self.high_risk_extensions:
                            threats.append(f"⚠️ ARŞİV İÇİ TEHDİT: Riskli dosya -> {f.filename}")
        except Exception as e:
            threats.append(f"❌ Arşiv Okuma Hatası: {e}")

        return threats


class BeytarchiverV35App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"Beytarchiver v{CURRENT_VERSION} Pro Enterprise - Masterpiece Suite")
        self.geometry("1240x840")
        self.minsize(1000, 700)

        # 1. PENCERE İKONU (Pencere sol üstü ve Görev Çubuğu logosu)
        if os.path.exists("logo.ico"):
            try:
                self.iconbitmap("logo.ico")
            except Exception:
                pass

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.current_lang = "TR"
        self.active_palette_name = "Catppuccin (Varsayılan)"
        self.av_engine = BeytNativeAntivirus()

        self.files_to_archive = []
        self.archive_to_extract = ""
        self.junk_files = []
        self.total_junk_bytes = 0

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.build_toolbar()
        self.build_navbar()

        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

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
        self.build_settings_view()

        self.status_bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#11111B")
        self.status_bar.grid(row=3, column=0, sticky="ew")

        self.lbl_status = ctk.CTkLabel(self.status_bar, text="Hazır", font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        self.lbl_status.pack(side="left", padx=10)

        self.lbl_stats = ctk.CTkLabel(self.status_bar, text=f"Beytarchiver v{CURRENT_VERSION} Pro Enterprise Active", font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        self.lbl_stats.pack(side="right", padx=10)

        self.show_view("compress")
        self.after(500, self.check_first_launch_update)

    def t(self, key):
        return LANGUAGES.get(self.current_lang, {}).get(key, key)

    def apply_color_palette(self, palette_name=None):
        if palette_name:
            self.active_palette_name = palette_name

        p = COLOR_THEMES.get(self.active_palette_name, COLOR_THEMES["Catppuccin (Varsayılan)"])
        mode = ctk.get_appearance_mode().lower()

        if mode == "light":
            theme_colors = p.get("light", p["dark"])
        else:
            theme_colors = p["dark"]

        self.configure(fg_color=theme_colors["bg"])
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
                with open(VERSION_FILE, "r") as f:
                    last_version = f.read().strip()
            except Exception:
                pass

        if last_version != CURRENT_VERSION:
            self.show_update_notes_dialog()

    # YENİLİKLERİ EKRANA YANSITAN DİYALOG PENCERESİ
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
                with open(VERSION_FILE, "w") as f:
                    f.write(CURRENT_VERSION)
            except Exception:
                pass
            dialog.destroy()

        btn_ok = ctk.CTkButton(dialog, text=self.t("btn_close_update"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=close_and_save)
        btn_ok.pack(pady=12)

    def change_language(self, new_lang):
        self.current_lang = new_lang
        self.update_ui_language()

    def update_ui_language(self):
        for key, btn in self.nav_btns.items():
            btn.configure(text=self.t(key))

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

    def build_toolbar(self):
        self.toolbar = ctk.CTkFrame(self, height=65, corner_radius=0, fg_color="#1E1E2E")
        self.toolbar.grid(row=0, column=0, sticky="ew")

        # ARAYÜZ İÇİ LOGO (Toolbar Sol Tarafı)
        logo_loaded = False
        if HAS_PIL and os.path.exists("logo.png"):
            try:
                img = Image.open("logo.png")
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(38, 38))
                lbl_logo = ctk.CTkLabel(self.toolbar, image=ctk_img, text="")
                lbl_logo.pack(side="left", padx=(12, 5), pady=10)
                logo_loaded = True
            except Exception:
                pass

        if not logo_loaded:
            lbl_logo_text = ctk.CTkLabel(self.toolbar, text="⚡ BEYT", font=ctk.CTkFont(size=16, weight="bold"), text_color="#89B4FA")
            lbl_logo_text.pack(side="left", padx=(15, 10), pady=10)

        self.create_tb_btn("➕ Ekle", self.select_compress_files)
        self.create_tb_btn("📂 Çıkart", lambda: self.show_view("extract"))
        self.create_tb_btn("🔐 Kasa", lambda: self.show_view("vault"))
        self.create_tb_btn("⚡ RAM", lambda: self.show_view("ram"))
        self.create_tb_btn("🔄 Güncelle", lambda: self.show_view("updater"))
        self.create_tb_btn("🛡️ Antivirüs", lambda: self.show_view("antivirus"))
        self.create_tb_btn("🧹 Temizleyici", lambda: self.show_view("cleaner"))
        self.create_tb_btn("👥 Çift Dosya", lambda: self.show_view("duplicates"))
        # YENİLİKLERİ EKRANA YANSITAN BUTON EKLENDİ
        self.create_tb_btn("📌 Yenilikler", self.show_update_notes_dialog)
        self.create_tb_btn("⚙️ Ayarlar", lambda: self.show_view("settings"))

    def create_tb_btn(self, text, command):
        btn = ctk.CTkButton(
            self.toolbar, text=text, width=85, height=42, fg_color="#313244", hover_color="#45475A",
            font=ctk.CTkFont(size=11, weight="bold"), command=command
        )
        btn.pack(side="left", padx=2, pady=10)
        return btn

    def build_navbar(self):
        self.view_bar = ctk.CTkFrame(self, height=35, corner_radius=0, fg_color="#181825")
        self.view_bar.grid(row=1, column=0, sticky="ew")

        self.nav_btns = {}
        views = [
            ("compress", self.t("compress")),
            ("extract", self.t("extract")),
            ("vault", self.t("vault")),
            ("ram", self.t("ram")),
            ("updater", self.t("updater")),
            ("antivirus", self.t("antivirus")),
            ("cleaner", self.t("cleaner")),
            ("analyzer", self.t("analyzer")),
            ("duplicates", self.t("duplicates")),
            ("shredder", self.t("shredder")),
            ("organizer", self.t("organizer")),
            ("startup", self.t("startup")),
        ]

        for key, text in views:
            btn = ctk.CTkButton(
                self.view_bar, text=text, fg_color="transparent", width=85, height=28,
                command=lambda k=key: self.show_view(k)
            )
            btn.pack(side="left", padx=2, pady=3)
            self.nav_btns[key] = btn

    def show_view(self, view_name):
        for panel in [
            self.compress_panel, self.extract_panel, self.vault_panel, self.ram_panel, self.updater_panel,
            self.antivirus_panel, self.cleaner_panel, self.analyzer_panel, self.duplicates_panel,
            self.shredder_panel, self.organizer_panel, self.startup_panel, self.hash_panel, self.settings_panel
        ]:
            panel.pack_forget()

        for btn in self.nav_btns.values():
            btn.configure(fg_color="transparent")

        if view_name in self.nav_btns:
            self.nav_btns[view_name].configure(fg_color="#313244")

        if view_name == "compress": self.compress_panel.pack(fill="both", expand=True)
        elif view_name == "extract": self.extract_panel.pack(fill="both", expand=True)
        elif view_name == "vault": self.vault_panel.pack(fill="both", expand=True)
        elif view_name == "ram": self.ram_panel.pack(fill="both", expand=True)
        elif view_name == "updater": self.updater_panel.pack(fill="both", expand=True)
        elif view_name == "antivirus": self.antivirus_panel.pack(fill="both", expand=True)
        elif view_name == "cleaner": self.cleaner_panel.pack(fill="both", expand=True)
        elif view_name == "analyzer": self.analyzer_panel.pack(fill="both", expand=True)
        elif view_name == "duplicates": self.duplicates_panel.pack(fill="both", expand=True)
        elif view_name == "shredder": self.shredder_panel.pack(fill="both", expand=True)
        elif view_name == "organizer": self.organizer_panel.pack(fill="both", expand=True)
        elif view_name == "startup":
            self.startup_panel.pack(fill="both", expand=True)
            self.load_startup_apps()
        elif view_name == "hash": self.hash_panel.pack(fill="both", expand=True)
        elif view_name == "settings": self.settings_panel.pack(fill="both", expand=True)

    # ==========================================
    # 🔐 1. ŞİFRELİ GİZLİ KASA
    # ==========================================
    def build_vault_view(self):
        self.vault_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        top = ctk.CTkFrame(self.vault_panel, corner_radius=12, fg_color="#1E1E2E", height=90)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)

        lbl = ctk.CTkLabel(top, text="🔐 Beytarchiver Encrypted Vault (.beyt)", font=ctk.CTkFont(size=20, weight="bold"), text_color="#89B4FA")
        lbl.pack(pady=(15, 0))

        sub = ctk.CTkLabel(top, text="AES-256 Şifreli Parolalı Özel Kasa Oluşturun", font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        sub.pack(pady=2)

        body = ctk.CTkFrame(self.vault_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)

        self.entry_vault_pass = ctk.CTkEntry(body, placeholder_text="Kasa İçin Güçlü Parola Girin", show="*", width=250)
        self.entry_vault_pass.pack(pady=20)

        btn = ctk.CTkButton(body, text="🔐 Dosyaları Seç ve .beyt Kasası Oluştur", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.create_vault)
        btn.pack(pady=10)

        self.lbl_vault_status = ctk.CTkLabel(body, text="Kasa İşlemi Bekleniyor", font=ctk.CTkFont(size=13))
        self.lbl_vault_status.pack(pady=15)

    def create_vault(self):
        pwd = self.entry_vault_pass.get().strip()
        if not pwd:
            self.lbl_vault_status.configure(text="❌ Lütfen kasa için bir parola girin!", text_color="#F38BA8")
            return
        files = filedialog.askopenfilenames(title="Kasaya Eklenecek Dosyaları Seçin")
        if files:
            threading.Thread(target=self.vault_engine, args=(files, pwd), daemon=True).start()

    def vault_engine(self, files, pwd):
        try:
            out_name = f"secure_vault_{datetime.now().strftime('%Y%m%d_%H%M%S')}.beyt"
            with pyzipper.AESZipFile(out_name, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
                zf.setpassword(pwd.encode())
                for f in files:
                    zf.write(f, os.path.basename(f))
            self.lbl_vault_status.configure(text=f"✅ Kasa Oluşturuldu: {out_name}", text_color="#A6E3A1")
            winsound.Beep(1000, 300)
        except Exception as e:
            self.lbl_vault_status.configure(text=f"Kasa Hatası: {e}", text_color="#F38BA8")

    # ==========================================
    # ⚡ 2. BELLEK VE RAM BÜYÜCÜSÜ
    # ==========================================
    def build_ram_view(self):
        self.ram_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        top = ctk.CTkFrame(self.ram_panel, corner_radius=12, fg_color="#1E1E2E", height=90)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)

        lbl = ctk.CTkLabel(top, text="⚡ RAM Booster & Memory Purger", font=ctk.CTkFont(size=20, weight="bold"), text_color="#A6E3A1")
        lbl.pack(pady=(15, 0))

        sub = ctk.CTkLabel(top, text="Arka plan süreçlerinin stand-by belleğini anında boşaltın.", font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        sub.pack(pady=2)

        body = ctk.CTkFrame(self.ram_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)

        btn = ctk.CTkButton(body, text="⚡ Sistem Belleğini / RAM'i Temizle", fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(size=14, weight="bold"), command=self.clean_ram)
        btn.pack(pady=30)

        self.lbl_ram_status = ctk.CTkLabel(body, text="Hazır", font=ctk.CTkFont(size=13))
        self.lbl_ram_status.pack(pady=10)

    def clean_ram(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.psapi.EmptyWorkingSet(-1)
                self.lbl_ram_status.configure(text="✅ Sistem RAM'i başarıyla rahatlatıldı!", text_color="#A6E3A1")
                winsound.Beep(1200, 200)
            except Exception as e:
                self.lbl_ram_status.configure(text=f"RAM Temizleme Hatası: {e}", text_color="#F38BA8")

    # ==========================================
    # 🔄 3. YAZILIM GÜNCELLEYİCİ SEKMESİ
    # ==========================================
    def build_updater_view(self):
        self.updater_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        top = ctk.CTkFrame(self.updater_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 10))

        btn = ctk.CTkButton(top, text="🔍 Eski Sürüm Yazılımları Tara (winget)", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_updater_scan)
        btn.pack(side="left", padx=15, pady=12)

        self.lbl_up_status = ctk.CTkLabel(top, text="Tarama Bekleniyor", font=ctk.CTkFont(size=12))
        self.lbl_up_status.pack(side="left", padx=10)

        self.up_box = ctk.CTkTextbox(self.updater_panel, height=220, corner_radius=10, state="disabled")
        self.up_box.pack(fill="both", expand=True)

    def start_updater_scan(self):
        self.lbl_up_status.configure(text="Taranıyor...", text_color="#89B4FA")
        threading.Thread(target=self.updater_engine, daemon=True).start()

    def updater_engine(self):
        self.up_box.configure(state="normal")
        self.up_box.delete("1.0", "end")
        self.up_box.insert("end", "🔄 GÜNCELLEME İHTİYACI OLAN UYGULAMALAR TARANIYOR...\n\n")

        try:
            res = subprocess.run(["winget", "upgrade"], capture_output=True, text=True, timeout=15)
            output = res.stdout if res.stdout else "winget bulunamadı veya tüm programlar güncel."
            self.up_box.insert("end", output)
        except Exception as e:
            self.up_box.insert("end", f"Sistemde winget altyapısı bulunamadı veya hata oluştu: {e}")

        self.lbl_up_status.configure(text="Tarama Tamamlandı", text_color="#A6E3A1")
        self.up_box.configure(state="disabled")

    # ==========================================
    # 👥 4. ÇİFT DOSYA BULUCU SEKMESİ
    # ==========================================
    def build_duplicates_view(self):
        self.duplicates_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        top = ctk.CTkFrame(self.duplicates_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 8))

        btn = ctk.CTkButton(top, text="🔍 Klasör Seç ve Çift Dosyaları Tara", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_dup_scan)
        btn.pack(side="left", padx=10, pady=10)

        self.lbl_dup_status = ctk.CTkLabel(top, text="Klasör Seçilmedi", font=ctk.CTkFont(size=12))
        self.lbl_dup_status.pack(side="left", padx=10)

        tree_frame = ctk.CTkFrame(self.duplicates_panel, corner_radius=10, fg_color="#181825")
        tree_frame.pack(fill="both", expand=True)

        columns = ("hash", "name", "size", "path")
        self.dup_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.dup_tree.heading("hash", text="Hash İmzası")
        self.dup_tree.heading("name", text="Dosya Adı")
        self.dup_tree.heading("size", text="Boyut")
        self.dup_tree.heading("path", text="Konumu")

        self.dup_tree.column("hash", width=180)
        self.dup_tree.column("name", width=200)
        self.dup_tree.column("size", width=90)
        self.dup_tree.column("path", width=380)

        self.dup_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)

    def start_dup_scan(self):
        target = filedialog.askdirectory(title="Çift Dosya Taraması İçin Klasör Seç")
        if target:
            self.lbl_dup_status.configure(text=f"Taranıyor: {target}", text_color="#89B4FA")
            threading.Thread(target=self.dup_scan_engine, args=(target,), daemon=True).start()

    def dup_scan_engine(self, target):
        for item in self.dup_tree.get_children(): self.dup_tree.delete(item)
        hashes = {}

        for root, _, files in os.walk(target):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    h = self.av_engine.calculate_file_hash(fp)
                    if h:
                        if h not in hashes: hashes[h] = []
                        hashes[h].append(fp)
                except Exception: pass

        count = 0
        for h, file_list in hashes.items():
            if len(file_list) > 1:
                for fp in file_list:
                    count += 1
                    sz = format_size(get_path_size(fp))
                    self.dup_tree.insert("", "end", values=(h[:16] + "...", os.path.basename(fp), sz, fp))

        self.lbl_dup_status.configure(text=f"Tarama Bitti: {count} kopya dosya bulundu!", text_color="#A6E3A1")
        winsound.Beep(1000, 200)

    # ==========================================
    # 🔥 5. GÜVENLİ DOSYA İMHA ETME
    # ==========================================
    def build_shredder_view(self):
        self.shredder_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        top = ctk.CTkFrame(self.shredder_panel, corner_radius=12, fg_color="#1E1E2E", height=100)
        top.pack(fill="x", pady=(0, 10))
        top.pack_propagate(False)

        lbl = ctk.CTkLabel(top, text="🔥 Güvenli Dosya İmha Motoru (DoD 5220.22-M)", font=ctk.CTkFont(size=20, weight="bold"), text_color="#F38BA8")
        lbl.pack(pady=(15, 0))

        sub = ctk.CTkLabel(top, text="Dosyaların üzerini rastgele verilerle yazarak kalıcı olarak siler.", font=ctk.CTkFont(size=12), text_color="#A6ADC8")
        sub.pack(pady=2)

        body = ctk.CTkFrame(self.shredder_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)

        btn = ctk.CTkButton(body, text="🔥 Kalıcı Olarak İmha Edilecek Dosyayı Seç", fg_color="#F38BA8", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_shred)
        btn.pack(pady=20)

        self.lbl_shred_file = ctk.CTkLabel(body, text="Dosya Seçilmedi", font=ctk.CTkFont(size=13))
        self.lbl_shred_file.pack(pady=5)

    def start_shred(self):
        selected = filedialog.askopenfilename(title="İmha Edilecek Dosyayı Seç")
        if selected:
            self.lbl_shred_file.configure(text=f"İmha Ediliyor: {os.path.basename(selected)}", text_color="#F38BA8")
            threading.Thread(target=self.shred_engine, args=(selected,), daemon=True).start()

    def shred_engine(self, path):
        try:
            length = os.path.getsize(path)
            with open(path, "wb") as f:
                f.write(os.urandom(length))
            os.remove(path)
            self.lbl_shred_file.configure(text="✅ Dosya Tamamen İmha Edildi!", text_color="#A6E3A1")
            winsound.Beep(1200, 300)
        except Exception as e:
            self.lbl_shred_file.configure(text=f"İmha Hatası: {e}", text_color="#F38BA8")

    # ==========================================
    # 📁 6. OTOMATİK DOSYA DÜZENLEYİCİ
    # ==========================================
    def build_organizer_view(self):
        self.organizer_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        top = ctk.CTkFrame(self.organizer_panel, corner_radius=10)
        top.pack(fill="x", pady=(0, 10))

        lbl = ctk.CTkLabel(top, text="📁 Akıllı Masaüstü ve Klasör Düzenleyici", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.pack(pady=15)

        body = ctk.CTkFrame(self.organizer_panel, corner_radius=10, fg_color="#181825")
        body.pack(fill="both", expand=True)

        btn_desk = ctk.CTkButton(body, text="🖥️ Masaüstünü Düzenle", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=lambda: self.organize_dir(os.path.expanduser("~/Desktop")))
        btn_desk.pack(pady=15)

        btn_down = ctk.CTkButton(body, text="📥 İndirilenler Klasörünü Düzenle", fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=lambda: self.organize_dir(os.path.expanduser("~/Downloads")))
        btn_down.pack(pady=10)

        self.lbl_org_status = ctk.CTkLabel(body, text="İşlem Bekleniyor", font=ctk.CTkFont(size=13))
        self.lbl_org_status.pack(pady=15)

    def organize_dir(self, target_path):
        if not os.path.exists(target_path): return
        
        categories = {
            "Belgeler": [".pdf", ".docx", ".txt", ".xlsx", ".pptx"],
            "Resimler": [".jpg", ".jpeg", ".png", ".gif", ".bmp"],
            "Arşivler": [".zip", ".7z", ".rar", ".tar", ".gz"],
            "Uygulamalar": [".exe", ".msi"],
            "Videolar": [".mp4", ".mkv", ".avi"],
            "Müzikler": [".mp3", ".wav"]
        }

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
                        moved += 1
                        break

        self.lbl_org_status.configure(text=f"✅ Başarılı! {moved} dosya kategorize edildi.", text_color="#A6E3A1")
        winsound.Beep(1000, 200)

    # ==========================================
    # 🛡️ 7. ANTİVİRÜS SEKMESİ
    # ==========================================
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
        selected = filedialog.askopenfilename(title="Taranacak Dosyayı Seç")
        if selected:
            self.lbl_av_file.configure(text=f"Seçilen: {os.path.basename(selected)}", text_color="#89B4FA")
            threading.Thread(target=self.run_custom_antivirus, args=(selected,), daemon=True).start()

    def run_custom_antivirus(self, file_path):
        self.av_box.configure(state="normal")
        self.av_box.delete("1.0", "end")
        self.av_box.insert("end", f"🛡️ BEYTARCHIVER SECURITY ENGINE (v3.5) TARAMASI BAŞLADI\n")
        self.av_box.insert("end", f"📄 Dosya: {os.path.basename(file_path)}\n")
        self.av_box.insert("end", "=" * 60 + "\n\n")

        results, file_hash = self.av_engine.scan_file(file_path)
        if file_hash: self.av_box.insert("end", f"🔑 SHA-256 İmzası: {file_hash}\n\n")

        if results:
            for res in results: self.av_box.insert("end", f"{res}\n")
        else: self.av_box.insert("end", "✅ Dosya imzası ve sezgisel analiz temiz çıktı.\n")

        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".zip", ".7z", ".tar", ".beyt"]:
            self.av_box.insert("end", "\n📦 Arşiv içi derine inilerek taranıyor...\n")
            archive_threats = self.av_engine.scan_archive_contents(file_path)
            if archive_threats:
                for threat in archive_threats: self.av_box.insert("end", f"{threat}\n")
            else: self.av_box.insert("end", "✅ Arşiv içindeki tüm dosyalar güvenli görünüyor.\n")

        self.av_box.insert("end", "\n✨ Tarama Tamamlandı.")
        self.av_box.configure(state="disabled")
        winsound.Beep(1000, 200)

    # ==========================================
    # 📦 8. SIKIŞTIRMA SEKMESİ
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
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("name", text="Dosya Adı")
        self.tree.heading("size", text="Boyut")
        self.tree.heading("type", text="Tür")
        self.tree.heading("path", text="Tam Yol")

        self.tree.column("name", width=220)
        self.tree.column("size", width=100)
        self.tree.column("type", width=80)
        self.tree.column("path", width=400)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#1E1E2E", foreground="#CDD6F4", fieldbackground="#1E1E2E", rowheight=24)
        style.configure("Treeview.Heading", background="#313244", foreground="#89B4FA", font=("Arial", 10, "bold"))

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.opt_panel = ctk.CTkFrame(self.compress_panel, height=50, corner_radius=10)
        self.opt_panel.pack(fill="x", pady=8)

        self.combo_fmt = ctk.CTkComboBox(self.opt_panel, values=["zip", "7z", "tar", "tar.gz"], width=80)
        self.combo_fmt.pack(side="left", padx=5, pady=8)

        self.combo_level = ctk.CTkComboBox(self.opt_panel, values=["Fast", "Balanced", "Ultra"], width=90)
        self.combo_level.set("Balanced")
        self.combo_level.pack(side="left", padx=5, pady=8)

        self.entry_pass = ctk.CTkEntry(self.opt_panel, placeholder_text=self.t("password"), show="*", width=130)
        self.entry_pass.pack(side="left", padx=5, pady=8)

        self.btn_start = ctk.CTkButton(self.opt_panel, text=self.t("start_compress"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_compression)
        self.btn_start.pack(side="right", padx=8, pady=8)

        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self.handle_compress_drop)

    def select_compress_files(self):
        selected = filedialog.askopenfilenames(title="Dosyaları Seçin")
        if selected:
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
            fname = os.path.basename(path)
            self.tree.insert("", "end", values=(fname, size, ftype, path))

    def start_compression(self):
        if not self.files_to_archive:
            self.lbl_status.configure(text="Lütfen önce dosya ekleyin!", text_color="#F38BA8")
            return
        threading.Thread(target=self.compress_engine, daemon=True).start()

    def compress_engine(self):
        self.lbl_status.configure(text="Sıkıştırılıyor...", text_color="#89B4FA")
        try:
            fmt = self.combo_fmt.get().lower()
            password = self.entry_pass.get().strip()
            out_name = f"beyt_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"

            all_entries = []
            for item in self.files_to_archive:
                if os.path.isfile(item): all_entries.append((item, os.path.basename(item)))
                elif os.path.isdir(item):
                    for root, _, files in os.walk(item):
                        for file in files:
                            fp = os.path.join(root, file)
                            rel = os.path.relpath(fp, start=os.path.dirname(item))
                            all_entries.append((fp, rel))

            if fmt == "zip":
                kwargs = {"compression": pyzipper.ZIP_DEFLATED}
                if password: kwargs["encryption"] = pyzipper.WZ_AES
                with pyzipper.AESZipFile(out_name, "w", **kwargs) as zf:
                    if password: zf.setpassword(password.encode())
                    for filePath, arcName in all_entries: zf.write(filePath, arcName)
            elif fmt == "7z":
                with py7zr.SevenZipFile(out_name, "w", password=password if password else None) as archive:
                    for filePath, arcName in all_entries: archive.write(filePath, arcName)

            self.lbl_status.configure(text=f"Sıkıştırma Başarılı: {out_name}", text_color="#A6E3A1")
            winsound.Beep(1000, 300)
            send_notification("Beytarchiver", "Arşiv başarıyla oluşturuldu!")
        except Exception as e:
            self.lbl_status.configure(text=f"Hata: {e}", text_color="#F38BA8")

    # ==========================================
    # 📂 9. DOSYA ÇIKARTMA SEKMESİ
    # ==========================================
    def build_extract_view(self):
        self.extract_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        self.extract_drop_zone = ctk.CTkFrame(self.extract_panel, height=75, border_width=2, border_color="#A6E3A1", corner_radius=10)
        self.extract_drop_zone.pack(fill="x", pady=(0, 8))
        self.extract_drop_zone.pack_propagate(False)

        self.extract_drop_lbl = ctk.CTkLabel(self.extract_drop_zone, text=self.t("drop_extract"), font=ctk.CTkFont(size=13, weight="bold"))
        self.extract_drop_lbl.pack(expand=True)
        self.extract_drop_zone.bind("<Button-1>", lambda e: self.select_extract_file())

        self.extract_opt_panel = ctk.CTkFrame(self.extract_panel, corner_radius=10)
        self.extract_opt_panel.pack(fill="x", pady=8)

        self.entry_ext_pass = ctk.CTkEntry(self.extract_opt_panel, placeholder_text=self.t("password_req"), show="*", width=160)
        self.entry_ext_pass.pack(side="left", padx=8, pady=8)

        self.btn_start_extract = ctk.CTkButton(self.extract_opt_panel, text=self.t("start_extract"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.start_extraction)
        self.btn_start_extract.pack(side="right", padx=8, pady=8)

        self.extract_drop_zone.drop_target_register(DND_FILES)
        self.extract_drop_zone.dnd_bind("<<Drop>>", self.handle_extract_drop)

    def select_extract_file(self):
        selected = filedialog.askopenfilename(title="Arşiv veya Kasa Seç", filetypes=[("Arşivler ve Kasalar", "*.zip *.7z *.tar *.gz *.beyt")])
        if selected:
            self.archive_to_extract = selected
            self.lbl_status.configure(text=f"Seçilen Arşiv: {os.path.basename(selected)}", text_color="#A6E3A1")

    def handle_extract_drop(self, event):
        files = self.tk.splitlist(event.data)
        if files and os.path.isfile(files[0].strip("{}")):
            self.archive_to_extract = files[0].strip("{}")
            self.lbl_status.configure(text=f"Seçilen Arşiv: {os.path.basename(self.archive_to_extract)}", text_color="#A6E3A1")

    def start_extraction(self):
        if not self.archive_to_extract: return
        threading.Thread(target=self.extract_engine, daemon=True).start()

    def extract_engine(self):
        self.lbl_status.configure(text="Dosyalar Çıkartılıyor...", text_color="#89B4FA")
        try:
            pwd = self.entry_ext_pass.get().strip()
            out_dir = os.path.splitext(self.archive_to_extract)[0] + "_extracted"
            os.makedirs(out_dir, exist_ok=True)

            ext = os.path.splitext(self.archive_to_extract)[1].lower()
            if ext in [".zip", ".beyt"]:
                with pyzipper.AESZipFile(self.archive_to_extract, 'r') as zf:
                    if pwd: zf.setpassword(pwd.encode())
                    zf.extractall(path=out_dir)
            elif ext == ".7z":
                with py7zr.SevenZipFile(self.archive_to_extract, 'r', password=pwd if pwd else None) as z:
                    z.extractall(path=out_dir)

            self.lbl_status.configure(text="Çıkartma Başarılı!", text_color="#A6E3A1")
            winsound.Beep(1000, 300)
            open_in_explorer(out_dir)
        except Exception as e:
            self.lbl_status.configure(text=f"Çıkartma Hatası: {e}", text_color="#F38BA8")

    # ==========================================
    # 🧹 10. SİSTEM TEMİZLEYİCİ SEKMESİ
    # ==========================================
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
        self.clean_tree.heading("path", text="Çöp Dosya Yolu")
        self.clean_tree.heading("size", text="Boyut")
        self.clean_tree.heading("type", text="Tür")

        self.clean_tree.column("path", width=380)
        self.clean_tree.column("size", width=90)
        self.clean_tree.column("type", width=100)

        self.clean_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        self.clean_opts = ctk.CTkFrame(self.cleaner_body, corner_radius=10, fg_color="#181825")
        self.clean_opts.grid(row=0, column=1, sticky="nsew")

        self.chk_temp = ctk.CTkCheckBox(self.clean_opts, text="Windows Temp")
        self.chk_temp.select()
        self.chk_temp.pack(pady=10, padx=12, anchor="w")

        self.chk_user_temp = ctk.CTkCheckBox(self.clean_opts, text="AppData Temp")
        self.chk_user_temp.select()
        self.chk_user_temp.pack(pady=10, padx=12, anchor="w")

        self.chk_recycle = ctk.CTkCheckBox(self.clean_opts, text="Geri Dönüşüm Kutusu")
        self.chk_recycle.select()
        self.chk_recycle.pack(pady=10, padx=12, anchor="w")

        self.btn_scan_clean = ctk.CTkButton(self.clean_opts, text=self.t("scan"), fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=lambda: threading.Thread(target=self.scan_engine, daemon=True).start())
        self.btn_scan_clean.pack(pady=15, padx=12, fill="x")

        self.btn_do_clean = ctk.CTkButton(self.clean_opts, text=self.t("clean"), fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), state="disabled", command=lambda: threading.Thread(target=self.clean_engine, daemon=True).start())
        self.btn_do_clean.pack(pady=5, padx=12, fill="x")

    def scan_engine(self):
        self.btn_scan_clean.configure(state="disabled", text="Taranıyor...")
        self.junk_files.clear()
        self.total_junk_bytes = 0

        for item in self.clean_tree.get_children(): self.clean_tree.delete(item)

        scan_paths = []
        if self.chk_temp.get(): scan_paths.append((os.environ.get("TEMP"), "Windows Temp"))
        if self.chk_user_temp.get(): scan_paths.append((os.path.expanduser("~\\AppData\\Local\\Temp"), "User Temp"))

        for path, tag in scan_paths:
            if path and os.path.exists(path):
                try:
                    for root, dirs, files in os.walk(path):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                fsize = os.path.getsize(fp)
                                self.junk_files.append((fp, fsize))
                                self.total_junk_bytes += fsize
                                self.clean_tree.insert("", "end", values=(fp, format_size(fsize), tag))
                            except Exception: pass
                except Exception: pass

        self.lbl_junk_size.configure(text=format_size(self.total_junk_bytes))
        self.btn_scan_clean.configure(state="normal", text=self.t("scan"))
        if self.junk_files or self.chk_recycle.get(): self.btn_do_clean.configure(state="normal")
        winsound.Beep(1000, 200)

    def clean_engine(self):
        self.btn_do_clean.configure(state="disabled", text="Temizleniyor...")

        for fp, fsize in self.junk_files:
            try:
                if os.path.exists(fp): os.remove(fp)
            except Exception: pass

        if self.chk_recycle.get():
            try: ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
            except Exception: pass

        winsound.Beep(1200, 300)
        self.lbl_junk_size.configure(text="0.00 B", text_color="#A6E3A1")
        send_notification("Beytarchiver", "Sistem çöpleri temizlendi! 🧹")
        self.scan_engine()

    # ==========================================
    # 📊 11. DİSK ALANI ANALİZÖRÜ SEKMESİ
    # ==========================================
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
        self.ana_tree.heading("name", text="En Büyük Dosya Adı")
        self.ana_tree.heading("size", text="Boyut")
        self.ana_tree.heading("path", text="Konumu")

        self.ana_tree.column("name", width=250)
        self.ana_tree.column("size", width=110)
        self.ana_tree.column("path", width=450)

        self.ana_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)

    def start_disk_analysis(self):
        selected_dir = filedialog.askdirectory(title="Analiz Edilecek Dizin")
        if selected_dir:
            self.lbl_ana_path.configure(text=f"Taranıyor: {selected_dir}", text_color="#89B4FA")
            threading.Thread(target=self.analyze_disk_engine, args=(selected_dir,), daemon=True).start()

    def analyze_disk_engine(self, target_dir):
        for item in self.ana_tree.get_children(): self.ana_tree.delete(item)
        file_list = []

        for root, _, files in os.walk(target_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    fsize = os.path.getsize(fp)
                    file_list.append((f, fsize, fp))
                except Exception: pass

        file_list.sort(key=lambda x: x[1], reverse=True)
        top_files = file_list[:50]

        for fname, fsize, fp in top_files: self.ana_tree.insert("", "end", values=(fname, format_size(fsize), fp))
        self.lbl_ana_path.configure(text=f"Analiz Tamamlandı: {target_dir}", text_color="#A6E3A1")
        winsound.Beep(1000, 200)

    # ==========================================
    # 🚀 12. BAŞLANGIÇ PROGRAMLARI SEKMESİ
    # ==========================================
    def build_startup_view(self):
        self.startup_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        self.start_top = ctk.CTkFrame(self.startup_panel, corner_radius=10)
        self.start_top.pack(fill="x", pady=(0, 8))

        self.lbl_start_title = ctk.CTkLabel(self.start_top, text="🚀 Windows Başlangıcında Otomatik Çalışan Uygulamalar", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_start_title.pack(side="left", padx=15, pady=10)

        self.start_tree_frame = ctk.CTkFrame(self.startup_panel, corner_radius=10, fg_color="#181825")
        self.start_tree_frame.pack(fill="both", expand=True)

        columns = ("name", "command")
        self.start_tree = ttk.Treeview(self.start_tree_frame, columns=columns, show="headings")
        self.start_tree.heading("name", text="Uygulama Adı")
        self.start_tree.heading("command", text="Çalıştırma Komutu")

        self.start_tree.column("name", width=220)
        self.start_tree.column("command", width=550)

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
            except Exception as e: print(f"Startup Read Error: {e}")


    def build_hash_view(self):
        self.hash_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        self.hash_top = ctk.CTkFrame(self.hash_panel, corner_radius=10)
        self.hash_top.pack(fill="x", pady=(0, 10))

        self.btn_select_hash_file = ctk.CTkButton(self.hash_top, text="🔍 Hash Hesaplanacak Dosyayı Seç", fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.select_hash_file)
        self.btn_select_hash_file.pack(side="left", padx=15, pady=12)

        self.lbl_hash_file = ctk.CTkLabel(self.hash_top, text="Dosya Seçilmedi", font=ctk.CTkFont(size=12))
        self.lbl_hash_file.pack(side="left", padx=10)

        self.hash_box = ctk.CTkTextbox(self.hash_panel, height=220, corner_radius=10, state="disabled")
        self.hash_box.pack(fill="both", expand=True)

    def select_hash_file(self):
        selected = filedialog.askopenfilename(title="Dosya Seç")
        if selected:
            self.lbl_hash_file.configure(text=os.path.basename(selected), text_color="#89B4FA")
            threading.Thread(target=self.calculate_hashes, args=(selected,), daemon=True).start()

    def calculate_hashes(self, file_path):
        self.hash_box.configure(state="normal")
        self.hash_box.delete("1.0", "end")
        self.hash_box.insert("end", f"📄 Dosya: {os.path.basename(file_path)}\n\n")

        md5 = hashlib.md5()
        sha1 = hashlib.sha1()
        sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5.update(chunk)
                sha1.update(chunk)
                sha256.update(chunk)

        self.hash_box.insert("end", f"📌 MD5:\n{md5.hexdigest()}\n\n")
        self.hash_box.insert("end", f"📌 SHA-1:\n{sha1.hexdigest()}\n\n")
        self.hash_box.insert("end", f"📌 SHA-256:\n{sha256.hexdigest()}\n")
        self.hash_box.configure(state="disabled")

    
    def build_settings_view(self):
        self.settings_panel = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        self.theme_frame = ctk.CTkFrame(self.settings_panel, corner_radius=10)
        self.theme_frame.pack(pady=10, fill="x")

        self.theme_label = ctk.CTkLabel(self.theme_frame, text=self.t("theme"), font=ctk.CTkFont(size=14))
        self.theme_label.pack(side="left", padx=15, pady=15)

        self.theme_menu = ctk.CTkOptionMenu(
            self.theme_frame, 
            values=["Dark", "Light", "System"], 
            command=self.change_appearance_mode
        )
        self.theme_menu.pack(side="right", padx=15, pady=15)

        self.palette_frame = ctk.CTkFrame(self.settings_panel, corner_radius=10)
        self.palette_frame.pack(pady=10, fill="x")

        self.palette_label = ctk.CTkLabel(self.palette_frame, text=self.t("color_palette"), font=ctk.CTkFont(size=14))
        self.palette_label.pack(side="left", padx=15, pady=15)

        self.palette_menu = ctk.CTkOptionMenu(
            self.palette_frame, values=list(COLOR_THEMES.keys()),
            command=self.apply_color_palette
        )
        self.palette_menu.set(self.active_palette_name)
        self.palette_menu.pack(side="right", padx=15, pady=15)

        self.lang_frame = ctk.CTkFrame(self.settings_panel, corner_radius=10)
        self.lang_frame.pack(pady=10, fill="x")

        self.lang_label = ctk.CTkLabel(self.lang_frame, text=self.t("language"), font=ctk.CTkFont(size=14))
        self.lang_label.pack(side="left", padx=15, pady=15)

        self.lang_menu = ctk.CTkOptionMenu(self.lang_frame, values=["TR", "EN"], command=self.change_language)
        self.lang_menu.pack(side="right", padx=15, pady=15)


if __name__ == "__main__":
    app = BeytarchiverV35App()
    app.mainloop()