import asyncio
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime

import flet as ft
import pyzipper

# Support both `python -m mobile.main` and directly opening mobile/main.py.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beyt_core import (SecurityError, format_size, inspect_zip,
                       safe_extract_archive, unique_arcname)

CHUNK_SIZE = 1024 * 64  # 64 KB (mobil RAM dostu okuma bloğu)
PROGRESS_INTERVAL = 0.15  # arayüzü saniyede en fazla ~7 kez güncelle


def get_safe_app_storage_dir(sub_folder="Exports"):
    """Android 11+ Scoped Storage için her zaman yazılabilir uygulama dizinini döndürür."""
    base_dir = (
        os.environ.get("FLET_APP_STORAGE_DATA")
        or os.environ.get("HOME")
        or tempfile.gettempdir()
    )
    safe_dir = os.path.join(base_dir, "Beytarchiver", sub_folder)
    try:
        os.makedirs(safe_dir, exist_ok=True)
    except OSError:
        safe_dir = os.path.join(tempfile.gettempdir(), "Beytarchiver", sub_folder)
        os.makedirs(safe_dir, exist_ok=True)
    return safe_dir


def is_directory_writable(dir_path):
    """Hedef klasöre yazma izni olup olmadığını test eder."""
    if not dir_path:
        return False
    try:
        os.makedirs(dir_path, exist_ok=True)
        with tempfile.TemporaryFile(prefix='.beyt-write-', dir=dir_path) as probe:
            probe.write(b'ok')
        return True
    except OSError:
        return False


def unique_dir(path):
    """Var olan bir klasörün üzerine yazmamak için 'ad (1)' biçiminde boş bir yol bulur."""
    if not os.path.lexists(path):
        return path
    n = 1
    while os.path.lexists(f"{path} ({n})"):
        n += 1
    return f"{path} ({n})"


class BeytarchiverMobileEngine:
    """ZIP denetimi, güvenli çıkartma ve oluşturma motoru (çekirdek mantık beyt_core'da)."""

    def __init__(self):
        self.cancel_event = threading.Event()
        self.is_running = False

    def inspect_and_validate_zip(self, zip_path):
        return inspect_zip(zip_path)

    def extract_verified_zip(self, zip_path, requested_dest_dir, password, progress_cb, status_cb):
        """Doğrulayarak çıkartır. Çıkartma geçici klasöre yapılır; hata/iptalde hedefte hiçbir şey kalmaz."""
        if not self.is_running:
            self.cancel_event.clear()
        self.is_running = True
        dest_dir = requested_dest_dir
        try:
            if not is_directory_writable(os.path.dirname(dest_dir)):
                archive_name = os.path.splitext(os.path.basename(zip_path))[0]
                dest_dir = os.path.join(get_safe_app_storage_dir("Extracted"), f"{archive_name}_extracted")
                status_cb("⚠️ Android Scoped Storage kısıtlaması: güvenli uygulama klasörüne çıkartılıyor...", "#FAB387")
            dest_dir = unique_dir(dest_dir)

            status_cb("🔍 Arşiv güvenlik denetiminden geçiriliyor...", "#89B4FA")
            inspect_zip(zip_path)

            last = [0.0]

            def on_progress(done, total, name):
                now = time.monotonic()
                if now - last[0] < PROGRESS_INTERVAL:
                    return
                last[0] = now
                if total > 0:
                    progress_cb(min(done / total, 1.0), f"Çıkartılıyor: {name}")

            safe_extract_archive(zip_path, dest_dir, password,
                                 progress=on_progress, cancel_event=self.cancel_event)
            status_cb(f"✅ Başarıyla çıkartıldı:\n📍 {dest_dir}", "#A6E3A1")
            progress_cb(1.0, "Tamamlandı")

        except InterruptedError:
            # Geçici klasör otomatik silindi; hedef hiç oluşturulmadı.
            status_cb("🚫 İşlem iptal edildi, hedefte dosya bırakılmadı.", "#F38BA8")
            progress_cb(0.0, "İptal Edildi")
        except zipfile.BadZipFile as e:
            status_cb(f"❌ Arşiv bozuk veya bütünlük doğrulaması başarısız: {e}", "#F38BA8")
            progress_cb(0.0, "Hata Oluştu")
        except SecurityError as e:
            status_cb(f"🚨 Güvenlik ihlali: {e}", "#F38BA8")
            progress_cb(0.0, "Engellendi")
        except Exception as e:
            status_cb(f"❌ Hata: {e}", "#F38BA8")
            progress_cb(0.0, "Hata Oluştu")
        finally:
            self.is_running = False

    def create_zip_from_files(self, file_paths, requested_out_zip, password, progress_cb, status_cb):
        """Seçilen dosyalardan çakışmasız ZIP oluşturur; iptal/hata durumunda yarım dosyayı siler."""
        if not self.is_running:
            self.cancel_event.clear()
        self.is_running = True
        out_zip_path = requested_out_zip
        created = False

        try:
            out_zip_path = os.path.abspath(out_zip_path)
            out_dir = os.path.dirname(out_zip_path)
            if not is_directory_writable(out_dir):
                safe_dir = get_safe_app_storage_dir("Archives")
                out_zip_path = os.path.join(safe_dir, os.path.basename(requested_out_zip))
                status_cb("⚠️ Seçilen dizine yazma izni yok, güvenli uygulama klasörüne kaydediliyor...", "#FAB387")

            total_bytes = 0
            for f in file_paths:
                try:
                    total_bytes += os.path.getsize(f)
                except OSError:
                    pass
            encryption = pyzipper.WZ_AES if password else None
            # Exclusive creation: a collision must never overwrite a user archive.
            with open(out_zip_path, 'xb') as output:
                created = True
                self._write_zip(output, file_paths, password, total_bytes,
                                progress_cb, status_cb, encryption)

            if self.cancel_event.is_set():
                raise InterruptedError('Sıkıştırma iptal edildi.')
            # Verify the completed stream before reporting success.
            with pyzipper.AESZipFile(out_zip_path, 'r') as archive:
                if password:
                    archive.setpassword(password.encode('utf-8'))
                for info in archive.infolist():
                    with archive.open(info) as source:
                        while True:
                            if self.cancel_event.is_set():
                                raise InterruptedError('Sıkıştırma iptal edildi.')
                            if not source.read(CHUNK_SIZE):
                                break

            status_cb(f"✅ Arşiv kaydedildi:\n📍 {out_zip_path}", "#A6E3A1")
            progress_cb(1.0, "Kayıt Başarılı")

        except InterruptedError:
            self._remove_partial(out_zip_path, created)
            status_cb("🚫 Sıkıştırma iptal edildi. Yarım kalan .zip dosyası silindi.", "#F38BA8")
            progress_cb(0.0, "İptal Edildi")
        except Exception as e:
            self._remove_partial(out_zip_path, created)
            status_cb(f"❌ Oluşturma hatası: {e}", "#F38BA8")
            progress_cb(0.0, "Hata")
        finally:
            self.is_running = False

    def _write_zip(self, output, file_paths, password, total_bytes,
                   progress_cb, status_cb, encryption):
        processed_bytes, last, used = 0, 0.0, set()
        with pyzipper.AESZipFile(output, 'w', compression=pyzipper.ZIP_DEFLATED,
                                 encryption=encryption) as zf:
            if password:
                zf.setpassword(password.encode('utf-8'))

            for fp in file_paths:
                if self.cancel_event.is_set():
                    raise InterruptedError("Sıkıştırma iptal edildi.")

                arcname = unique_arcname(os.path.basename(fp), used)
                status_cb(f"📦 Sıkıştırılıyor: {arcname}", "#89B4FA")

                # force_zip64: 2 GB üstü tek dosyalarda hata almamak için.
                with open(fp, "rb") as src, zf.open(arcname, "w", force_zip64=True) as dst:
                    while True:
                        if self.cancel_event.is_set():
                            raise InterruptedError("Sıkıştırma iptal edildi.")
                        chunk = src.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        dst.write(chunk)
                        processed_bytes += len(chunk)
                        now = time.monotonic()
                        if total_bytes > 0 and now - last >= PROGRESS_INTERVAL:
                            last = now
                            progress_cb(min(processed_bytes / total_bytes, 1.0), f"Yazılıyor: {arcname}")

    @staticmethod
    def _remove_partial(path, created):
        if created and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


# =====================================================================
# 📱 FLET ANDROID ARAYÜZÜ
# =====================================================================
async def main(page: ft.Page):
    page.title = "Beytarchiver Mobile Ultimate"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#181825"
    page.padding = 12
    page.scroll = ft.ScrollMode.AUTO

    engine = BeytarchiverMobileEngine()
    selected_files_for_zip = []
    current_zip_path = ""
    custom_output_dir = get_safe_app_storage_dir()
    loop = asyncio.get_running_loop()
    action_buttons = []
    busy = False

    lbl_lifecycle = ft.Text("🟢 Durum: Aktif (Ön Plan)", size=12, color="#A6E3A1")
    pwd_field = ft.TextField(label="Şifre (AES-256 Opsiyonel)", password=True, can_reveal_password=True,
                             height=48, text_size=13)
    lbl_output_dir = ft.Text(f"📂 Hedef Klasör: {custom_output_dir}", size=11, color="#A6ADC8")

    archive_list_view = ft.ListView(expand=True, spacing=6, padding=10)

    lbl_transfer_title = ft.Text("⚡ Aktarım & İşlem Durumu: Bekleniyor", size=14,
                                 weight=ft.FontWeight.BOLD, color="#CDD6F4")
    progress_bar = ft.ProgressBar(value=0, color="#89B4FA", bgcolor="#313244", height=10)
    lbl_status = ft.Text("Dosya veya hedef klasör seçmek için butonları kullanın.", size=12, color="#A6ADC8")

    btn_cancel = ft.Button(
        "🛑 İptal Et",
        bgcolor="#F38BA8",
        color="#11111B",
        disabled=True,
        on_click=lambda _: cancel_current_task()
    )

    def update_progress(val, text):
        def apply():
            progress_bar.value = val
            lbl_transfer_title.value = f"⚡ {text} (%{int(val * 100)})"
            page.update()
        loop.call_soon_threadsafe(apply)

    def update_status(msg, color="#CDD6F4"):
        def apply():
            lbl_status.value = msg
            lbl_status.color = color
            page.update()
        loop.call_soon_threadsafe(apply)

    async def run_task(fn, *args):
        """Reserve the job before yielding; keep widget updates on the page loop."""
        nonlocal busy
        if busy:
            return
        busy = True
        engine.cancel_event.clear()
        engine.is_running = True
        btn_cancel.disabled = False
        for button in action_buttons:
            button.disabled = True
        page.update()
        try:
            await asyncio.to_thread(fn, *args)
        finally:
            busy = False
            engine.is_running = False
            btn_cancel.disabled = True
            for button in action_buttons:
                button.disabled = False
            page.update()

    def cancel_current_task():
        if busy:
            engine.cancel_event.set()
            update_status("⏳ İptal sinyali gönderildi...", "#FAB387")

    async def on_zip_picked(_):
        nonlocal current_zip_path
        if busy:
            return
        files = await zip_picker.pick_files(file_type=ft.FilePickerFileType.CUSTOM,
                                             allowed_extensions=['zip'])
        if not files or not files[0].path:
            return
        current_zip_path = files[0].path
        archive_list_view.controls.clear()

        try:
            items, total_sz = await asyncio.to_thread(inspect_zip, current_zip_path)
            update_status(f"🛡️ Güvenlik denetimi geçti! Toplam {len(items)} öğe ({format_size(total_sz)})", "#A6E3A1")
            for item in items:
                icon = "📁" if item["is_dir"] else "📄"
                archive_list_view.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(f"{icon} {item['name']}", size=13, color="#CDD6F4", expand=True),
                            ft.Text(format_size(item["size"]), size=12, color="#89B4FA")
                        ]),
                        bgcolor="#313244", padding=8, border_radius=6
                    )
                )
        except SecurityError as ex:
            current_zip_path = ""
            update_status(f"🚨 Güvenlik ihlali: {ex}", "#F38BA8")
        except Exception as ex:
            current_zip_path = ""
            update_status(f"❌ Arşiv okunamadı: {ex}", "#F38BA8")
        page.update()

    async def on_files_picked_for_create(_):
        nonlocal selected_files_for_zip
        if busy:
            return
        files = await files_picker.pick_files(allow_multiple=True)
        if not files:
            return
        selected_files_for_zip = [f.path for f in files if f.path]
        archive_list_view.controls.clear()
        for fp in selected_files_for_zip:
            try:
                size_text = format_size(os.path.getsize(fp))
            except OSError:
                size_text = "boyut okunamadı"
            archive_list_view.controls.append(
                ft.Text(f"➕ Eklenecek: {os.path.basename(fp)} ({size_text})", color="#A6E3A1", size=13)
            )
        update_status(f"{len(selected_files_for_zip)} dosya seçildi. 'ZIP Oluştur'a basın.", "#89B4FA")
        page.update()

    async def on_output_dir_picked(_):
        nonlocal custom_output_dir
        if busy:
            return
        path = await dir_picker.get_directory_path()
        if path:
            if is_directory_writable(path):
                custom_output_dir = path
                lbl_output_dir.value = f"📂 Hedef Klasör (Yazma İzinli): {custom_output_dir}"
                lbl_output_dir.color = "#A6E3A1"
                update_status("✅ Hedef klasör doğrulandı ve yazma izni onaylandı.", "#A6E3A1")
            else:
                custom_output_dir = get_safe_app_storage_dir()
                lbl_output_dir.value = f"📂 Hedef Klasör (Güvenli Alan): {custom_output_dir}"
                lbl_output_dir.color = "#FAB387"
                update_status("⚠️ Seçilen klasöre Android Scoped Storage yazma izni vermedi! "
                              "Güvenli uygulama klasörü kullanılacak.", "#FAB387")
            page.update()

    # Flet 1.0 services register with the current page when constructed.
    zip_picker = ft.FilePicker()
    files_picker = ft.FilePicker()
    dir_picker = ft.FilePicker()

    async def start_extract_action(_):
        if not current_zip_path:
            update_status("⚠️ Önce 'ZIP Seç & Denetle' ile bir arşiv seçin!", "#FAB387")
            return
        if busy:
            return
        zip_base = os.path.splitext(os.path.basename(current_zip_path))[0]
        out_dir = os.path.join(custom_output_dir, f"{zip_base}_extracted")
        await run_task(engine.extract_verified_zip, current_zip_path, out_dir, pwd_field.value,
                       update_progress, update_status)

    async def start_create_zip_action(_):
        if not selected_files_for_zip:
            update_status("⚠️ Önce 'Dosya Seç' ile sıkıştırılacak dosyaları seçin!", "#FAB387")
            return
        if busy:
            return
        out_zip = os.path.join(custom_output_dir, f"BeytMobile_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.zip")
        await run_task(engine.create_zip_from_files, list(selected_files_for_zip), out_zip, pwd_field.value,
                       update_progress, update_status)

    def handle_lifecycle_change(e: ft.AppLifecycleStateChangeEvent):
        if e.state == ft.AppLifecycleState.PAUSED:
            if busy:
                lbl_lifecycle.value = "🟡 Arka planda: Android işlemi durdurabilir"
            else:
                lbl_lifecycle.value = "🟡 Durum: Arka Planda"
            lbl_lifecycle.color = "#FAB387"
        elif e.state == ft.AppLifecycleState.RESUMED:
            lbl_lifecycle.value = "🟢 Durum: Aktif (Ön Plan)"
            lbl_lifecycle.color = "#A6E3A1"
        elif e.state == ft.AppLifecycleState.DETACHED:
            if busy:
                engine.cancel_event.set()
        page.update()

    main_layout = ft.ResponsiveRow(spacing=12, run_spacing=12)

    def build_responsive_ui():
        pick_zip = ft.Button("🔍 ZIP Seç & Denetle", bgcolor="#89B4FA", color="#11111B",
                             expand=True, on_click=on_zip_picked)
        pick_files = ft.Button("➕ Dosya Seç", bgcolor="#CBA6F7", color="#11111B",
                               expand=True, on_click=on_files_picked_for_create)
        pick_dir = ft.Button("📁 Hedef Klasör", bgcolor="#94E2D5", color="#11111B",
                             expand=True, on_click=on_output_dir_picked)
        extract = ft.Button("📂 Doğrula & Çıkart", bgcolor="#A6E3A1", color="#11111B",
                            expand=True, on_click=start_extract_action)
        create = ft.Button("🗜️ ZIP Oluştur", bgcolor="#FAB387", color="#11111B",
                           expand=True, on_click=start_create_zip_action)
        action_buttons[:] = [pick_zip, pick_files, pick_dir, extract, create]
        archive_card = ft.Container(
            col={"xs": 12, "md": 7},
            bgcolor="#1E1E2E",
            padding=15,
            border_radius=12,
            content=ft.Column([
                ft.Row([
                    ft.Text("📦 Beytarchiver Android", size=18, weight=ft.FontWeight.BOLD, color="#89B4FA"),
                    lbl_lifecycle
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(color="#313244"),
                ft.Row([pick_zip, pick_files, pick_dir], spacing=6, wrap=True),
                lbl_output_dir,
                pwd_field,
                ft.Text("📋 Arşiv İçeriği / Seçilen Dosyalar:", size=13, color="#A6ADC8"),
                ft.Container(content=archive_list_view, height=200, bgcolor="#11111B", border_radius=8)
            ])
        )

        transfer_card = ft.Container(
            col={"xs": 12, "md": 5},
            bgcolor="#1E1E2E",
            padding=15,
            border_radius=12,
            content=ft.Column([
                ft.Text("🚀 Aktarım & Doğrulama Merkezi", size=16, weight=ft.FontWeight.BOLD, color="#A6E3A1"),
                ft.Divider(color="#313244"),
                lbl_transfer_title,
                progress_bar,
                lbl_status,
                ft.Divider(color="#313244"),
                ft.Row([extract, create], spacing=8, wrap=True),
                ft.Row([btn_cancel], alignment=ft.MainAxisAlignment.END)
            ])
        )

        main_layout.controls = [archive_card, transfer_card]
        page.update()

    page.on_app_lifecycle_state_change = handle_lifecycle_change
    page.on_resize = lambda _: page.update()

    build_responsive_ui()
    page.add(main_layout)


if __name__ == "__main__":
    ft.run(main)
    
