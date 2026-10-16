# Beytarchiver 4.0 LAN Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Native execution is proposed; implementation starts after user review.

**Goal:** Windows'tan aynı ağdaki Android telefona QR ve yerel onay sonrasında tek dosyayı TLS ile gönderip kaydını doğrulamak; Android Studio gerektirmeden CI'da test APK'sı üretmek.

**Architecture:** Android bilgisayardaki HTTPS servisine bağlanır. QR geçici sertifika parmak izini taşır; bilgisayar yalnızca kullanıcı onayından sonra seçilmiş dosyanın değişmez kopyasını sunar. Tkinter, aktarım işçileriyle mevcut UI kuyruğu üzerinden iletişim kurar.

**Tech Stack:** Python 3.10+, cryptography, qrcode, Kotlin / Compose, OkHttp, Android SAF, Gradle ve GitHub Actions. Aday Android sürümleri teknik tasarımda sabitlenmiştir; ilk derleme ile doğrulanacaktır.

**Spec:** [Teknik tasarım](../specs/2026-10-16-beytarchiver-4-lan-prototype.md)

## Global Constraints

- İlk prototip: aynı yerel ağ, Windows → Android, tek telefon ve aynı anda tek dosya.
- En fazla 1 GiB (1.073.741.824 bayt), 128 KiB bloklar; sıfır bayt desteklenir.
- QR 120 saniye; onay 60 saniye; oturum 15 dakika. Sunucuda monotonic saat.
- TLS ≥1.2; tam DER sertifikasının SHA-256 pini ve IP / SAN doğrulaması.
- Üç ayrı 256 bit token; bearer token'lar loglara, URL'lere ve diske yazılmaz.
- POST gövdesi ≤4096 bayt; en fazla 4 bağlantı; 30 saniye ilerlemesiz I/O zaman aşımı.
- Eşleştirme IP başına 10/dakika; durum sorgusu istemci başına 2/saniye.
- Android min SDK 26, compile / target SDK 35, Java 17; paket `com.beytarchiver.mobile`.
- Test uygulaması `4.0.0-alpha.1`, `versionCode=1`; masaüstü 3.7 ve mevcut kayıtlar korunur.
- Kalıcı eşleştirme, telefon → PC, arka plan aktarımı ve resume bu planda yoktur.
- Genel disk erişimi, trust-all TLS, HTTP fallback ve güvenlik duvarını kapatma yoktur.
- Mevcut checkout kullanılır; kullanıcı istemedikçe worktree oluşturulmaz. Commit / push ve yayın ancak o aşama yetkilendirildiğinde yapılır.

## Review Focus

1. Kaynak dosya hazırlık sırasında değişirse yanlış içerik sunulmaması — Task 2.
2. Yanlış sertifika, yönlendirme ve QR'ı kopyalayan ikinci istemci — Tasks 1, 2, 4.
3. Android hedef sağlayıcısı yarıda yazma / silme hatası verirse başarı denmemesi — Task 4.
4. Token veya oturum süresi aktarım sırasında dolarsa her iki uçta tutarlı iptal — Tasks 2, 4.
5. APK imzası değiştiğinde kullanıcıya veri kaybı yaratacak sessiz güncelleme varsayılmaması — Task 5.

## Dosya yerleşimi

Mevcut dosya `venv/Akıllı_Dosya_Yöneticisi/beytarchiver.py` korunur. Python transfer
paketi aynı kaynak klasöründe `lan_transfer/` altında yer alır; böylece doğrudan
çalıştırma ve PyInstaller importları aynı şekilde işler. Bu tarihsel `venv/` bir
kaynak dizinidir. Yeni modüller `.gitignore` nedeniyle commit aşamasında yalnızca
tam dosya yollarıyla `git add -f` gerektirebilir; tüm `venv/` eklenmez.

Python testleri `tests/lan/`; Android proje / testleri `android/`; iş akışı
`.github/workflows/android-debug.yml`. Protokol örnekleri ve ortak test verileri
`protocol/lan-v1-fixtures.json` dosyasında sır içermeyen sabit test değerleriyle tutulur.

## Task 1 — Protokol ve eşleştirme durum makinesi

**Files:**
- Create: `venv/Akıllı_Dosya_Yöneticisi/lan_transfer/__init__.py`
- Create: `venv/Akıllı_Dosya_Yöneticisi/lan_transfer/protocol.py`
- Create: `venv/Akıllı_Dosya_Yöneticisi/lan_transfer/session.py`
- Create: `protocol/lan-v1-fixtures.json`
- Create: `tests/lan/conftest.py`, `tests/lan/test_session.py`

**Interfaces:**
- `validate_qr(payload: str) -> dict`: Tasarımdaki QR alanlarını doğrular; yanlış veri `ValueError`.
- `PairingSession(clock: Callable[[], float] = time.monotonic)`: bir iş parçacığı kilidiyle korunan oturum.
- `qr_payload(origin: str, cert_sha256: str) -> dict`, `request_pair(payload: dict, peer_ip: str) -> dict`.
- `approve(request_id: str) -> None`, `reject(request_id: str) -> None`, `pair_status(request_id: str, poll_token: str) -> dict`.
- `authorize(access_token: str) -> None`, `stop() -> None`; `ProtocolError(status: int, code: str)` HTTP'ye çevrilebilir hata taşır.

- [ ] Test fixture'larında kontrol edilebilir `FakeClock`, kaynak klasörünü Python import yoluna ekleyen test kurulumu ve sabit geçerli / geçersiz QR örnekleri oluştur.
- [ ] `test_qr_rejects_bad_origin` için HTTP, userinfo, query, genel IP, loopback ve büyük JSON'un her birinde `ValueError` bekle. Geçerli özel IPv4 örneğinin aynı alanlarla döndüğünü doğrula.
- [ ] `test_approval_required` içinde pending isteğin dosya yetkisi alamadığını; approve sonrasında yalnızca doğru access token'ın geçtiğini doğrula.
- [ ] `test_expiry_and_replay` için FakeClock'u 120, 60 ve 900 saniye eşiklerine taşı; yeniden kullanımın reddini, reject sonrası yeni QR token'ını ve ikinci eşzamanlı istemcinin `409` almasını doğrula.
- [ ] `test_pair_rate_limit` içinde 11. denemenin `429` aldığını, sonraki zaman penceresinde sınırın sıfırlandığını doğrula.
- [ ] `python -m pytest tests/lan/test_session.py -q` çalıştır; eksik davranış nedeniyle başarısızlığı gör.
- [ ] Protokol ve oturum kodunu uygula; testleri tekrar çalıştır. Token'lar `secrets` ile üretilsin; karşılaştırma `hmac.compare_digest` kullansın.

**Bitiş:** Dosya servisi olmadan onay, red, yetki ve süre kuralları testlerle çalışır.

## Task 2 — HTTPS dosya sunucusu ve değişmez kaynak

**Files:**
- Create: `venv/Akıllı_Dosya_Yöneticisi/lan_transfer/tls.py`, `files.py`, `server.py`
- Create: `tests/lan/test_server.py`, `tests/lan/test_files.py`

**Interfaces:**
- `create_identity(host: str, directory: Path) -> TlsIdentity`: cert/key yolları ve DER `cert_sha256` alanı; SAN host ile eşleşir.
- `prepare_offer(source: Path, work_dir: Path, cancel: Event) -> PreparedOffer`: `transfer_id`, `name`, `size`, `sha256`, `staged_path` alanları.
- `TransferServer.start(host: str) -> dict`: geçici portta servis ve QR payload; `approve(request_id)`, `reject(request_id)`, `offer(source)`, `cancel(transfer_id)`, `stop()`.
- `TransferServer(events: Queue)` Tk'dan bağımsızdır; olaylar `kind`, `request_id` / `transfer_id`, `bytes`, `total`, `message` alanlarını gerektiğinde taşır. Token ve key olay loguna eklenmez.

- [ ] `test_prepare_offer_snapshot` değişmez kopyanın hash'ini doğrulasın; kopyalama sırasında kaynağı değiştirince / okuyamayınca teklifin oluşmadığını ve geçici dosyanın temizlendiğini göstersin.
- [ ] `test_transfer_sizes` 0 bayt, 10 MiB ve 1 GiB üzeri boyutu kapsasın. Büyük boyut sınırı gerçek 1 GiB RAM ayırmadan seyrek dosyayla veya stat fixture'ıyla doğrulansın; testler dosyanın tamamını belleğe okumasın.
- [ ] Gerçek yerel TLS soketleriyle doğru pin / SAN kabulü, yanlış pin ve host reddi, auth olmadan metadata alamama ve iki indirmeden birinin `409` almasını test et.
- [ ] `test_receipt_is_required_and_idempotent` yanlış hash'i reddetsin; yalnızca doğru alındı bildirimi completed yapsın; bildirimin tekrarını kabul etsin.
- [ ] `test_disconnect_cancel_expiry` istemci kopuşu, stop, süre sonu ve read timeout'ta soket / geçici dosya temizliğini doğrulasın. `test_request_limits` gövde ve bağlantı limitlerini doğrulasın.
- [ ] Yeni testleri çalıştırıp eksik davranışları gör; sonra `ssl.SSLContext` ve sınırlı işçi sayılı HTTP handler'larını uygula. Dosya yollarını URL'den üretme; dosya yalnızca transfer ID ile çözülsün.
- [ ] Yeni sunucu testlerini ve `python -m pytest -q` ile mevcut paketi çalıştır; grafik testinin atlandığı bir çalışma gerçek UI doğrulaması sayılmasın.

**Bitiş:** HTTPS üzerinden gerçek dosya akışı ve yaşam döngüsü mevcut GUI'den bağımsız doğrulanır.

## Task 3 — Windows arayüzüne bağlama

**Files:**
- Create: `venv/Akıllı_Dosya_Yöneticisi/lan_transfer/panel.py`
- Modify: `venv/Akıllı_Dosya_Yöneticisi/beytarchiver.py`
- Modify: `beytarchiver-requirements.txt`, `BEYTARCHIVER.md`
- Create: `tests/lan/test_panel.py`

**Interfaces:**
- `TransferPanel(parent, dispatch: Callable, server_factory=TransferServer)` mevcut Tk arayüzüne eklenir.
- `shutdown() -> None` sunucuyu ve işçileri kapatır; ana pencerenin `close_app()` yolu çağırır.
- Ağ arayüzleri mevcut `psutil` ile listelenir; QR JSON'u Task 1'in encoder / validator sözleşmesine bağlıdır.

- [ ] İşçi thread'inden Tk `.get()` / `.configure()` çağrısının hata verdiği testle bütün girdilerin ana thread'de alındığını doğrula.
- [ ] İkinci bağlantı başlatmanın, etkin aktarım sırasında dosya değiştirmenin ve pencereyi kapattıktan sonra callback gelmesinin kontrol edildiği panel testlerini önce çalıştır.
- [ ] `qrcode` için Python 3.10+ ile uyumlu sürümü doğrula ve tam sürüm olarak bağımlılık dosyasına ekle; Pillow zaten mevcut.
- [ ] Paneli toolbar, navbar, view listesi ve kapanış yoluna bağla. Kod karşılaştırmasını gerektiren onay penceresi ekle; cihaz adına güvenerek otomatik onaylama yapma.
- [ ] Grafik ekranında mevcut testler ve panel testlerini çalıştır. Özel ağ arabirimi seçimi, QR süre sonu ve stop için görsel smoke test yap.
- [ ] Windows notlarına özel ağ güvenlik duvarı izni ve PyInstaller'da QR paketlemesi adımlarını ekle; gerçek Windows EXE çalıştırması yapılmadıysa açıkça belirt.

**Bitiş:** Masaüstü uygulaması mevcut işlevleri koruyarak telefon istemcisini kabul edecek akışı sunar.

## Task 4 — Android istemcisi, eşleştirme ve doğrulanmış kayıt

**Files:**
- Create: `android/settings.gradle.kts`, `build.gradle.kts`, `gradle.properties`
- Create: `android/gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties`, `gradle-wrapper.jar`
- Create: `android/app/build.gradle.kts`, `android/app/src/main/AndroidManifest.xml`
- Create under `android/app/src/main/java/com/beytarchiver/mobile/`:
  `MainActivity.kt`, `PairingPayload.kt`, `PinnedClient.kt`, `TransferRepository.kt`,
  `ReceiveStore.kt`, `TransferViewModel.kt`, `TransferScreen.kt`
- Create matching tests under `android/app/src/test/java/com/beytarchiver/mobile/`.

**Interfaces:**
- `PairingPayload.parse(json: String): PairingPayload` Task 1'in ortak fixture'larını tüketir.
- `PinnedClient.create(payload: PairingPayload): OkHttpClient` yalnızca o origin / sertifikaya güvenen istemci üretir.
- `TransferRepository` Task 2 uçlarını kullanır; `StateFlow<TransferState>` ile Idle, Pairing, AwaitingApproval, Offered, Receiving, Saving, Complete, Cancelled, Error durumlarını sunar.
- `ReceiveStore` uygulama özel staging alanı ve SAF hedef URI yazımını yönetir; ağdan gelen `name` yalnızca önerilen dosya adıdır.
- `TransferViewModel.cancel()` coroutine ve aktif HTTP çağrısını iptal eder; foreground kaybı aynı iptal yolunu çağırır.

- [ ] Aday araç zincirini resmi uyumluluk tablosuyla kontrol et; wrapper'ı resmi Gradle dağıtım checksum'u ile üret ve JAR'ı doğrula. Yerelde SDK yoksa ilk derleme Task 5 CI akışı üzerinden yapılır.
- [ ] Ortak QR fixture'ları için JVM testleri yaz: Python ile aynı kabul / red sonuçları beklenir.
- [ ] `PinnedClientTest` gerçek TLS fixture sunucusuyla yanlış pin, yanlış host, HTTP, 302 yönlendirme ve farklı origin'e token sızmasını reddetsin.
- [ ] `TransferRepositoryTest` approve öncesi dosya istemesin; kesilen, eksik / fazla uzunluklu, hash'i yanlış ve süresi dolan indirmeyi Complete yapmasın. Sıfır bayt yüzdesi hata vermesin.
- [ ] `ReceiveStoreTest` disk dolması, hedef sağlayıcının yazma hatası, kısmi belgeyi silememe ve kullanıcı dosya seçimini iptal etme durumlarını kapsasın. Başarı ancak hedef kopyanın hash'i eşleşince oluşsun.
- [ ] Testleri çalıştırıp başarısızlığı gördükten sonra protokol, transport ve store'u uygula. Kamera izin reddi ekranı ve SAF seçicisi ekle; Android sürümüne bağlı LAN izinlerini güncel resmi belgeyle doğrula.
- [ ] QR okuyucuyu ve Compose ekranlarını bağla. Her bağlantıda yeni istemci kur; token'ları yalnızca bellekte tut. İptal / arka plana geçiş / process yeniden açılışında kalmış özel geçici dosyaları temizle.
- [ ] `cd android` ardından `./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug` çalıştır veya CI'da aynı sonuçları doğrula.

**Bitiş:** Android uygulaması derlenir; ağ / doğrulama / kayıt hata yolları test edilir. Henüz gerçek cihaz kabulü iddia edilmez.

## Task 5 — GitHub Actions APK ve çapraz istemci doğrulaması

**Files:**
- Create: `.github/workflows/android-debug.yml`
- Create: `tests/lan/serve_fixture.py`
- Create: `android/app/src/test/java/com/beytarchiver/mobile/PythonInteropTest.kt`
- Create: `docs/android-install-and-test.md`

**Interfaces:**
- `serve_fixture.py --ready-file <path>` yerel gerçek Python sunucusunu başlatır; test IP, port, pin ve fixture dosya bilgisini hazır dosyasına yazar. Bunlar yalnızca test sırlarıdır.
- `PythonInteropTest` test sürecinden başlatılan fixture'ı sonlandırır; gerçek OkHttp istemcisini kullanır. QR parser testleri ayrı tutulur; loopback TLS fixture'ı üretim QR adres kısıtını gevşetmez.
- Actions artifact adı `beytarchiver-android-4.0.0-alpha.1-<short-sha>`; APK + SHA256SUMS + test / lint raporları; saklama 14 gün.

- [ ] Workflow için Java 17 / SDK 35 kurulumunu, Python bağımlılıklarını, resmi wrapper doğrulamasını ve doğrulanmış SHA'ya sabitlenmiş Actions adımlarını oluştur.
- [ ] Tetikleyiciler: `workflow_dispatch`, ilgili Android / protokol / transfer kaynaklarının push / PR değişiklikleri. `permissions: contents: read`; pull_request_target ve APK / Release otomatik yayımlama kullanılmaz.
- [ ] `PythonInteropTest` gerçek Python servisiyle onay, dosya indirme, SHA-256 ve receipt turunu çalıştırsın. Yanlış pin / token ve iptal negatif senaryolarını da koşsun.
- [ ] Tek CI çalışmasında wrapper doğrulama, Python testleri, Gradle JVM testleri, lint ve assemble geçsin. APK yoksa artifact adımı başarısız olsun; raporlar test başarısızlığında da yüklensin.
- [ ] APK SHA-256 değerini dosyadan hesapla ve artifact'e koy. Gradle wrapper JAR'ını ve manifest'i secret / log / cleartext açısından kontrol et.
- [ ] Actions ilk çalışmasını repo sahibi erişimiyle tetikle; başarıyı sonuç ekranından doğrula. API veya ağ engelinde yalnızca YAML yazılmış olduğunu raporla, APK üretildi deme.
- [ ] Kullanıcıya Actions artifact indirme / ZIP açma / APK kurma adımlarını yaz. Debug anahtarı değişirse yeniden kurulum gerekebileceğini, kaldırmanın uygulama verisini silebileceğini ve Play Protect'i kapatmanın gerekli olmadığını açıkla.

**Bitiş:** Başarılı Actions çalışmasından indirilebilir, checksum'u belli test APK'sı vardır. İmzalı public Release ayrı aşamadır.

## Task 6 — Kullanıcıyla gerçek cihaz kabulü

**Files:**
- Update: `docs/android-install-and-test.md` — sonuç tablosu ve cihaz / sürüm bilgileri.

- [ ] Windows derlemesini ve APK'yı aynı commit'ten hazırla; iki cihazın aynı özel ağa bağlı olduğunu kontrol et.
- [ ] Android sürümünü ve Windows sürümünü kaydet. Kamera izni, QR, iki ekrandaki kod ve Windows onayını doğrula.
- [ ] 0 bayt ve en az 10 MiB dosyayı aktar; bilgisayarda PowerShell `Get-FileHash -Algorithm SHA256` sonucu ile telefonda doğrulanan hash'i karşılaştır.
- [ ] Aktarımı iptal et, Wi-Fi'ı kes ve uygulamayı arka plana al; hedef / staging temizliği ile sonuç ekranlarının doğru olduğunu kaydet. Süresi dolan QR'ın yenilenmesini ve reddedilen eşleştirmenin dosya alamamasını kontrol et.
- [ ] İlk kurulum ve debug APK güncelleme deneyimini doğrula. Yapılamayan cihaz kontrollerini «bekliyor» bırak; CI ile geçmiş sayma.
- [ ] Kabul testleri geçerse 4.0 geliştirmesinde sonraki kapsamı seç: çift yön, resume veya arşivleyerek gönderme. Prototipi otomatik olarak public 4.0 Release diye yayımlama.

## Yürütme önerisi

Bu planı aynı oturumda adım adım benim uygulamam uygun: eşleştirme, HTTPS ve Android
istemcisi ortak bir sözleşmeye bağlı. İlk somut teslim Windows oturumu / HTTPS
testleri, ikinci teslim indirilebilir APK, son teslim gerçek cihazdaki doğrulanmış
aktarımı gösteren sonuç tablosudur. Yazılı tasarım ve plan kullanıcı incelemesinden
sonra uygulamaya geçilir; bu belgelerin varlığı çalışan APK anlamına gelmez.
