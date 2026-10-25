# Geliştirme ve klasör düzeni

## Dosya haritası

| Yol | Görev |
| --- | --- |
| `beytarchiver.py` | Aktif CustomTkinter masaüstü uygulaması |
| `beyt_core.py` | Arayüzden bağımsız arşiv denetimi ve çıkartma yardımcıları |
| `lan_transfer/` | Masaüstü uygulamasının eşleştirme, TLS ve dosya aktarım paketi |
| `mobile/main.py` | Flet 1.0.5 arşiv uygulamasının giriş noktası |
| `android/` | Ayrı Kotlin/Compose Android aktarım uygulaması |
| `tests/` | Python testleri; `lan/` alt klasöründe LAN testleri ve JVM birlikte çalışabilirlik sunucusu |
| `tests/protocol/` | Python ve Kotlin tarafından kullanılan protokol örnekleri |
| `scripts/` | Windows derleme, kurulum ve bakım betikleri |
| `docs/` | Web sitesi, geliştirme belgeleri ve mevcut tasarım/planlar |
| `drafts/desktop/` | Korunan alternatif masaüstü kaynak taslağı |
| `.venv/`, `build/`, `dist/`, `Output/` | Yerel ortam ve üretilmiş dosyalar; Git dışında tutulur |

Logo dosyaları, uygulama ve kurulum betiklerinin beklediği kök dizinde tutulur.
Flet uygulaması ile Kotlin Android projesi ayrı uygulamalardır. Kotlin projesine
ait önceki bağımsız arşiv tasarımının tamamlanması bu bakım çalışmasının parçası değildir.

## Python ortamı

PowerShell komutlarını deponun kök dizininde çalıştırın. Mevcut `.venv` varsa ilk
komutu atlayın. Masaüstü kaynak kodu Python 3.10+ içindir; Flet ve güncel sabitlenmiş
paketlerle tüm geliştirme/test kurulumu için Python 3.12+ kullanın.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Yalnız masaüstü uygulaması için `requirements.txt`, yalnız Flet arayüzü için
`mobile/requirements.txt` kullanılabilir. Masaüstü bağımlılıklarının sabit sürümleri
`scripts/beytarchiver-requirements.txt` dosyasında korunur.

```powershell
# Masaüstü
.\.venv\Scripts\python.exe .\beytarchiver.py

# Flet arşiv uygulaması
.\.venv\Scripts\python.exe -m mobile.main
```

Flet ilk masaüstü çalıştırmada kendi Flutter istemcisini indirmeyi isteyebilir.
Bu Flet uygulaması yerel dosya yollarını kullanır; tarayıcıda dosya yükleme akışı
uygulanmamıştır. Android'de gerçek cihaz, dosya sağlayıcısı ve depolama izinleri
ayrıca doğrulanmalıdır. Bu bakım bir APK üretildiği anlamına gelmez.

## Testler

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

`pytest.ini`, test keşfini `tests/` ile sınırlar. Mobil testler gerçek ZIP/AES
işlemlerini ve gerçek Flet kontrolleriyle arayüz oluşturmayı sınar; dosya seçici
sonuçları testlerde taklit edilir, Flutter penceresi açılmaz.

Windows hesabında sembolik bağlantı oluşturma yetkisi yoksa yalnız o yeteneğe
bağlı testler gerekçesiyle atlanır. Sabit bağlantı ve iptal testleri ayrı çalışır;
sabit bağlantı oluşturmayı engelleyen Windows sandbox/dosya sistemi ortamında
o test de gerekçesiyle atlanır.
Mevcut Tk arayüz testleri `DISPLAY` yoksa atlanır. Linux CI bunları Xvfb ile çalıştırır.

## Arşiv davranışı

- Ortak çıkartma kodu en çok 2 GiB açılmış veri ve 10.000 girdi kabul eder.
- ZIP incelemesi yol geçişlerini, özel dosya/bağlantıları ve çakışan adları reddeder.
  50 MiB üzerindeki bir ZIP girdisinde 100 kat üzeri sıkıştırma oranı da reddedilir;
  bu sınır çok iyi sıkışan meşru verileri de etkileyebilir.
- Listeleme yalnız meta veriyi doğrular. CRC/AES bütünlüğü çıkarma sırasında akışın
  tamamı okunarak denetlenir. Hatalı çıkarma geçici alanda temizlenir.
- Mobil ZIP oluşturma mevcut hedefi ezmez; hata veya iptalde yalnız kendi çıktısını
  kaldırır. AES parolaları boşluklar dahil aynen kullanılır.
- Flet aynı anda tek arşiv işi yürütür; kontroller ana olay döngüsünde güncellenir.
  İşletim sisteminin arka planda işi sürdürmesi garanti edilmez.

## Windows derlemesi

```powershell
# Paket yüklemez veya çıktı silmez; gerekli dosya yollarını denetler.
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1 -Check

# Nuitka/PyInstaller derlemesi; paket indirir ve build/nuitka_mod alanını yeniden oluşturur.
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

Betik kendi konumundan depo kökünü bulur ve çağıranın çalışma dizinini geri yükler.
EXE çıktısı `dist/Beytarchiver/Beytarchiver.exe` olur. EXE doğrulandıktan sonra
`scripts/setup_scriss.iss`, Inno Setup ile derlenir; varsayılan kök betiğin üst
dizinidir. Bu bakım sırasında EXE ve kurulum paketi derlenmemiştir.

## Kotlin Android derlemesi

JDK 17 ve Android SDK 35/build-tools 34.0.0 hazır olmalıdır. Python birlikte
çalışabilirlik testi için mevcut sanal ortamı gösterin:

```powershell
$env:BEYT_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
Push-Location android
try {
    .\gradlew.bat --no-daemon testDebugUnitTest lintDebug assembleDebug
} finally {
    Pop-Location
}
```

Alternatif olarak mevcut `Android debug APK` GitHub Actions iş akışı aynı Python
testlerini, Kotlin testlerini, lint ve APK derlemesini çalıştırır.

## Bakım ve yayın

`Bakim_Modu_Ac_Kapat.bat` ve `scripts/set_maintenance.ps1` site durumunu uzaktan
değiştirebilir. Geliştirme veya test için bu betikleri çalıştırmak gerekmez.
Mevcut `docs/status.json` kullanıcı değişikliği korunmuştur.

## API kaynakları

- [Flet 1.0 geçiş rehberi](https://flet.dev/docs/updates/migrate-to-1-0/)
- [Flet FilePicker](https://flet.dev/docs/services/filepicker/)
- [Python dosya zaman damgaları](https://docs.python.org/3.14/library/os.html#os.stat_result)
- [Inno Setup SourcePath](https://jrsoftware.org/ishelp/topic_predefinedvars.htm)
