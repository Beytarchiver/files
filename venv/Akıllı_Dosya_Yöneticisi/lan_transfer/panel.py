"""Tk controller. All widget access stays on Tk's owner thread."""
import json
from queue import Empty, Queue
import socket
import threading
from tkinter import filedialog

import customtkinter as ctk
import psutil
import qrcode

from .protocol import ProtocolError, private_ipv4
from .server import TransferServer


def local_interfaces():
    stats = psutil.net_if_stats()
    result = {}
    for name, addresses in psutil.net_if_addrs().items():
        if name not in stats or not stats[name].isup:
            continue
        for address in addresses:
            if address.family == socket.AF_INET and private_ipv4(address.address):
                result[f'{name} — {address.address}'] = address.address
    return result


class TransferPanel(ctk.CTkFrame):
    def __init__(self, parent, dispatch, server_factory=TransferServer):
        super().__init__(parent, fg_color='transparent')
        self._dispatch, self._factory = dispatch, server_factory
        self._closing = False
        self._server = None
        self._workers = []
        self._events = Queue()
        self._paired = self._busy = self._stopping = False
        self._pending_id = self._transfer_id = None
        self._host = None
        self._ticks = 0
        self._interfaces = local_interfaces()

        ctk.CTkLabel(self, text='📱 Telefonla Aktar — 4.0 önizleme',
                     font=ctk.CTkFont(size=22, weight='bold')).pack(pady=(15, 5))
        ctk.CTkLabel(self, text='Aynı Wi-Fi • Bilgisayardan telefona • Tek dosya, en fazla 1 GiB').pack(pady=5)
        controls = ctk.CTkFrame(self)
        controls.pack(fill='x', padx=15, pady=10)
        self.interface = ctk.CTkComboBox(controls, width=330,
                                        values=list(self._interfaces) or ['Uygun özel ağ bulunamadı'],
                                        state='readonly')
        self.interface.pack(side='left', padx=8, pady=10)
        self.start_button = ctk.CTkButton(controls, text='Bağlantı Başlat', command=self.start_connection)
        self.start_button.pack(side='left', padx=5)
        self.stop_button = ctk.CTkButton(controls, text='Bağlantıyı Durdur', command=self.stop_connection,
                                        state='disabled')
        self.stop_button.pack(side='left', padx=5)
        self.qr_label = ctk.CTkLabel(self, text='Bağlantı başlatınca QR kodu burada görünür.')
        self.qr_label.pack(pady=5)
        self.address = ctk.CTkLabel(self, text='')
        self.address.pack(pady=2)
        self.status = ctk.CTkLabel(self, text='Hazır. Android uygulaması sonraki geliştirme aşamasında eklenecek.',
                                  wraplength=900)
        self.status.pack(pady=5)
        self.code = ctk.CTkLabel(self, text='', font=ctk.CTkFont(size=18, weight='bold'))
        self.code.pack(pady=5)
        actions = ctk.CTkFrame(self, fg_color='transparent')
        actions.pack(pady=5)
        self.approve_button = ctk.CTkButton(actions, text='Kodlar Aynı — Onayla', command=self.approve,
                                           state='disabled')
        self.approve_button.pack(side='left', padx=5)
        self.reject_button = ctk.CTkButton(actions, text='Reddet', command=self.reject, state='disabled')
        self.reject_button.pack(side='left', padx=5)
        self.select_button = ctk.CTkButton(actions, text='Dosya Seç', command=self.select_file, state='disabled')
        self.select_button.pack(side='left', padx=5)
        self.cancel_button = ctk.CTkButton(actions, text='Aktarımı İptal Et', command=self.cancel,
                                          state='disabled')
        self.cancel_button.pack(side='left', padx=5)
        self.progress = ctk.CTkProgressBar(self, width=600)
        self.progress.set(0)
        self.progress.pack(pady=15)
        self._timer = self.after(100, self._tick)

    def _post(self, callback, *args):
        if not self._closing:
            self._dispatch(self._deliver, callback, args)

    def _deliver(self, callback, args):
        if not self._closing:
            callback(*args)

    def _launch(self, operation):
        def run():
            try:
                operation()
            except (OSError, ValueError, ProtocolError) as exc:
                self._post(self._failed, str(exc))
        self._workers = [worker for worker in self._workers if worker.is_alive()]
        worker = threading.Thread(target=run, name='beyt-transfer-ui')
        self._workers.append(worker)
        worker.start()

    def start_connection(self):
        if self._closing or self._server is not None:
            return
        host = self._interfaces.get(self.interface.get())
        if not host:
            self._interfaces = local_interfaces()
            self.interface.configure(values=list(self._interfaces) or ['Uygun özel ağ bulunamadı'])
            if self._interfaces: self.interface.set(next(iter(self._interfaces)))
            self.status.configure(text='Wi-Fi / özel ağ bağlantısını seçip yeniden deneyin.')
            return
        self._host = host
        self._server = service = self._factory(self._events)
        self.start_button.configure(state='disabled')
        self.interface.configure(state='disabled')
        self.status.configure(text='Şifreli bağlantı hazırlanıyor...')
        def start():
            try:
                payload = service.start(host)
            except BaseException:
                service.stop()
                self._post(self._did_stop, service)
                raise
            self._post(self._started, service, payload)
        self._launch(start)

    def _started(self, service, payload):
        if self._closing or service is not self._server:
            return
        self.stop_button.configure(state='normal')
        self._render_qr(payload)

    def _render_qr(self, payload):
        image = qrcode.make(json.dumps(payload, separators=(',', ':'))).get_image().convert('RGB')
        self._qr_image = ctk.CTkImage(light_image=image, dark_image=image, size=(270, 270))
        self.qr_label.configure(image=self._qr_image, text='')
        self.address.configure(text=payload['origin'])
        self.code.configure(text='')
        self._pending_id = None
        self.approve_button.configure(state='disabled')
        self.reject_button.configure(state='disabled')
        self.status.configure(text='QR kodunu telefondan okutun. Kod 120 saniye geçerli; süresi dolunca yenilenir.')

    def _failed(self, message):
        self._busy = False
        self.status.configure(text='Hata: ' + message)
        self.select_button.configure(state='normal' if self._paired else 'disabled')
        self.cancel_button.configure(state='disabled')

    def approve(self):
        if self._closing or not self._pending_id or self._server is None:
            return
        try: self._server.approve(self._pending_id)
        except ProtocolError as exc: self._failed(str(exc))

    def reject(self):
        if self._closing or not self._pending_id or self._server is None:
            return
        try: self._server.reject(self._pending_id)
        except ProtocolError as exc: self._failed(str(exc))

    def select_file(self):
        if self._closing or not self._paired or self._busy:
            return
        source = filedialog.askopenfilename(parent=self, title='Telefona gönderilecek dosya')
        if not source:
            return
        service = self._server
        self._busy = True
        self._transfer_id = None
        self.select_button.configure(state='disabled')
        self.progress.set(0)
        self.status.configure(text='Dosya kopyası ve SHA-256 hazırlanıyor...')
        self._launch(lambda: service.offer(source))

    def cancel(self):
        if not self._closing and self._server and self._transfer_id:
            try: self._server.cancel(self._transfer_id)
            except ProtocolError as exc: self._failed(str(exc))

    def stop_connection(self):
        if self._closing or self._server is None or self._stopping:
            return
        self._stopping = True
        service = self._server
        self.stop_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.approve_button.configure(state='disabled')
        self.reject_button.configure(state='disabled')
        def stop():
            service.stop()
            self._post(self._did_stop, service)
        self._launch(stop)

    def _did_stop(self, service):
        if self._server is not service:
            return
        self._server = None
        self._paired = self._busy = self._stopping = False
        self._pending_id = self._transfer_id = None
        while not self._events.empty():
            try: self._events.get_nowait()
            except Empty: break
        self.start_button.configure(state='normal')
        self.interface.configure(state='readonly')
        self.stop_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.cancel_button.configure(state='disabled')
        self.code.configure(text='')
        self.qr_label.configure(image=None, text='Bağlantı kapalı.')
        self.address.configure(text='')
        self.status.configure(text='Bağlantı durduruldu.')

    def _event(self, event):
        kind = event['kind']
        if kind == 'pair_requested':
            self._pending_id = event['request_id']
            self.code.configure(text=f"Onay kodu: {event['code']}")
            self.status.configure(text=f"{event['device_name'] or 'Telefon'} bağlanmak istiyor. İki ekrandaki kodu karşılaştırın.")
            self.approve_button.configure(state='normal')
            self.reject_button.configure(state='normal')
        elif kind == 'qr_changed' and not self._paired:
            self._render_qr(self._server.qr())
        elif kind == 'paired':
            self._paired = True
            self._pending_id = None
            self.approve_button.configure(state='disabled')
            self.reject_button.configure(state='disabled')
            self.select_button.configure(state='normal')
            self.qr_label.configure(image=None, text='Telefon eşleşti.')
            self.code.configure(text='')
            self.status.configure(text='Telefon onaylandı. Göndermek için bir dosya seçin.')
        elif kind == 'ready':
            self._transfer_id = event['transfer_id']
            self.cancel_button.configure(state='normal')
            self.status.configure(text=f"{event['name']} ({event['size']:,} bayt) hazır; telefondan Al seçeneğini kullanın.")
        elif kind in ('progress', 'awaiting_receipt'):
            total, count = event['total'], event['bytes']
            self.progress.set(count / total if total else 1)
            self.status.configure(text='Dosya gönderildi; telefonun kayıt doğrulaması bekleniyor.'
                                  if kind == 'awaiting_receipt' else f'{count:,} / {total:,} bayt gönderildi')
        elif kind in ('completed', 'cancelled', 'error'):
            if event.get('expired'):
                self._paired = False
            self._busy = False
            self.cancel_button.configure(state='disabled')
            self.select_button.configure(state='normal' if self._paired else 'disabled')
            self.status.configure(text={'completed':'Telefon kaydı doğruladı. Aktarım tamamlandı.',
                                       'cancelled':'Aktarım iptal edildi; kısmi dosyayı yeniden gönderin.',
                                       'error':event.get('message', 'Aktarım hatası.')}[kind])

    def _tick(self):
        if self._closing:
            return
        for _ in range(100):
            try: event = self._events.get_nowait()
            except Empty: break
            if self._server is not None and not self._stopping:
                self._event(event)
        self._ticks += 1
        if self._server and not self._stopping and self._ticks % 10 == 0:
            if self._host not in local_interfaces().values():
                self.stop_connection()
        self._timer = self.after(100, self._tick)

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        self.after_cancel(self._timer)
        if self._server is not None:
            self._server.stop()
        for worker in self._workers:
            worker.join()
