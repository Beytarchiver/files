# Beytarchiver 4.0 — Windows / Android aktarım prototipi

Durum: Kullanıcı incelemesi için tasarım önerisi. Henüz uygulanmadı.

## Amaç ve kabul edilen kapsam

Kullanıcı Android Studio kurmadan, GitHub Actions'tan aldığı APK ile Windows
Beytarchiver uygulamasından Android telefonuna aynı yerel ağda bir dosya alabilsin.
QR eşleştirmesi bilgisayardan onaylansın, bağlantı şifreli olsun ve alınan dosyanın
bütünlüğü doğrulansın. Hesap, internet üzerinden aktarım ve bulut sunucusu gerekmez.
GitHub erişimi yalnızca geliştirme, derleme ve APK indirmek için gerekir.

İlk prototip tek bilgisayar, tek telefon ve aynı anda tek dosya destekler. Mobil
uygulama aktarım boyunca ön planda kalır. Kaynak kod sürümü 3.7 korunur; ürün 4.0
olarak yayımlanmadan önce gerçek Windows / Android kabul testi tamamlanır.

Sonraki aşamalar: telefondan bilgisayara gönderme, çoklu dosya, arşivleyerek
gönderme, kesilen aktarıma devam etme, kalıcı güvenilen cihazlar, arka plan servisi,
aktarım geçmişi ve otomatik cihaz keşfi. Bunlar ilk prototipin kabul şartı değildir.

## Seçilen yapı ve alternatifler

- Android: Kotlin, Jetpack Compose, OkHttp ve QR okuyucu. Yerel dosyaya kaydetmek
  için Android sistem dosya seçicisi (Storage Access Framework).
- Windows: mevcut Python / Tkinter uygulamasına «Telefonla Aktar» bölümü;
  Python standart kütüphanesiyle sınırlı bir HTTPS servisi. Sertifika üretimi için
  mevcut `cryptography`, QR görüntüsü için yeni `qrcode` bağımlılığı.
- Telefon HTTPS istemcisi olur; bilgisayara bağlanıp onaylanan dosyayı indirir.
  Telefonda sunucu açılmaz. WebSocket veya genel amaçlı dosya gezme API'si gerekmez.
- İlk sürümde tarayıcı istemcisi yerine kullanıcının istediği Android uygulaması
  seçildi. Windows'u da yeniden yazmak yerine mevcut arşivleme uygulaması korunur.

HTTPS için kendi şifreleme protokolümüzü yazmayacağız. Standart TLS ve QR üzerinden
sertifika sabitleme kullanılacak. Genel sistem güven deposu değiştirilmeyecek.

## Kullanıcı akışı

1. Windows'ta «Telefonla Aktar → Bağlantı Başlat» seçilir. Birden fazla uygun ağ
   arabirimi varsa kullanıcı aynı Wi-Fi'a bağlı arabirimi seçer.
2. Ekranda IP / port, 120 saniyelik QR ve «Bağlantıyı Durdur» görünür.
3. Android'de «Bilgisayara Bağlan» ile kamera izni istenir ve QR okunur.
4. İki ekranda aynı altı haneli onay kodu görünür. Kullanıcı kodları karşılaştırıp
   Windows'ta isteği onaylar. Telefonun gönderdiği cihaz adı kimlik kanıtı değildir.
5. Windows'ta kullanıcı tek dosya seçer. Boyut kontrolü ve SHA-256 hazırlığı
   arayüzü kilitlemeden yapılır; telefon dosya adı ve boyutunu görür.
6. Telefonda «Al» seçilir ve sistem seçicisinden yerel bir hedef belirlenir.
   İptal edilirse indirme başlamaz. Sistem seçicisinin verdiği URI kullanılır;
   sunucunun dosya adı hiçbir zaman yerel dosya yolu olarak kullanılmaz.
7. İndirme sırasında yüzde, aktarılan boyut ve iptal görünür. Telefon veriyi
   uygulama özel geçici alanına yazar, boyut ve SHA-256 değerlerini doğrular.
8. Doğrulanan dosya seçilen hedefe kopyalanır. Kopya da hash / boyut açısından
   kontrol edilir. Ancak bundan sonra telefon «Tamamlandı» gösterir ve bilgisayara
   alındı bildirimi gönderir. Bildirim ulaşmazsa bilgisayar «Onay bekleniyor» der.

## Eşleştirme ve ağ sözleşmesi

### QR biçimi

En fazla 2048 UTF-8 bayt JSON:

```json
{"v":1,"origin":"https://192.168.1.20:48123","session_id":"<rastgele-kimlik>","cert_sha256":"<64-küçük-hex>","pair_token":"<256-bit-base64url>","expires_at":"<UTC-RFC3339>"}
```

IPv4 özel adresi (RFC1918), açık port 1–65535 ve yalnızca HTTPS kabul edilir.
URL'de kullanıcı bilgisi, yol, query ve fragment reddedilir. DNS adı, loopback,
genel IP, IPv6 ve 169.254/16 ilk prototipte desteklenmez. Bozuk, büyük, süresi
geçmiş veya farklı protokol sürümlü QR istek yapılmadan reddedilir.

Windows seçilen LAN IPv4 adresine ve işletim sisteminin seçtiği boş porta bağlanır;
varsayılan olarak tüm arabirimlerde dinlemez. Arayüz IP değişimini algıladığında
oturum kapanır ve yeni QR gerekir. Sunucu internete port açmaz, UPnP kullanmaz.
Misafir ağındaki istemci izolasyonu ve VPN yönlendirmesi bağlantıyı engelleyebilir.

### TLS ve yetkilendirme

- Her bağlantı başlatıldığında geçici ECDSA P-256 anahtarı ve kendinden imzalı
  sertifika üretilir. SAN alanı seçilen IP'yi içerir. TLS en az 1.2'dir.
  Anahtar yalnızca kullanıcıya özel geçici dizinde, POSIX'te 0600 dosya izniyle;
  Windows'ta kullanıcı profili altındaki kısıtlı ACL'leri koruyarak tutulur.
- Android yalnızca QR'daki SHA-256 DER sertifika parmak izini taşıyan sertifikayı
  kabul eder; sertifika geçerlilik zamanı ve IP / SAN kontrolü de yapılır.
  Genel `trust-all`, koşulsuz hostname verifier ve HTTP'ye geri dönüş yoktur.
- HTTP yönlendirmeleri izlenmez. Bir oturum için oluşturulan istemci başka bir
  origin'e token gönderemez. Proxy kullanımı kapalıdır; bağlantı doğrudan LAN'adır.
- Eşleştirme, durum sorgulama ve aktarım için birbirinden bağımsız 256 bit
  `secrets` token'ları üretilir. Token'lar URL'de, loglarda veya diskte saklanmaz.
- QR en fazla 120 saniye, onay isteği 60 saniye, onaylı oturum 15 dakika yaşar.
  Süre kontrolü sunucuda monotonic saatle yapılır. Android QR süresini ayrıca
  kontrol eder; yanlış telefon saati için anlaşılır bir hata gösterir.
- Bir QR yalnızca bir bekleyen istek açabilir. Altı haneli kod sunucuda rastgele
  üretilir; onay yalnızca yerel Windows arayüzünden verilir. Kod API yetkisi değildir.
  İstek reddedilince veya zaman aşımında QR token'ı yenilenir.
- Onaylanmamış istemci dosya metadatası alamaz. Rastgele dosya yolu içeren istek
  desteklenmez. Süre dolması, durdurma veya pencere kapanması bütün yetkileri iptal eder.

### HTTP v1 uçları

| İstek | Yetki / giriş | Sonuç |
|---|---|---|
| `POST /v1/pair` | JSON: `session_id`, `pair_token`, `device_name` | `202`: `request_id`, `poll_token`, altı haneli `code` |
| `GET /v1/pair/{request_id}` | Bearer `poll_token` | pending / rejected / approved; approved ise `access_token` |
| `GET /v1/offer` | Bearer `access_token` | `204` veya `200`: `transfer_id`, `name`, `size`, `sha256` |
| `GET /v1/files/{transfer_id}` | Bearer `access_token` | `200`: sabit `Content-Length` ile dosya baytları |
| `POST /v1/receipt` | Bearer `access_token`; JSON: `transfer_id`, `size`, `sha256` | Eşleşirse `200`; tekrarı aynı sonuçla kabul edilir |
| `POST /v1/cancel` | Bearer `access_token`; JSON: `transfer_id` | Aktif işi iptal et; aynı kimlikle tekrar çağrı güvenlidir |

Token karşılaştırmaları sabit zamanlı yapılır. Yanlış token `401`, süresi dolan
bilinen oturum `410`, çakışan işlem `409`, bilinmeyen kaynak `404`, büyük gövde
`413`, hız sınırı `429` döndürür. POST gövdesi en fazla 4096 bayttır; eksik veya
geçersiz `Content-Length` ve chunked istek gövdeleri reddedilir. Eşleştirme IP
başına dakikada en fazla 10 deneme, durum sorgusu istemci başına saniyede en fazla
2 istek kabul eder. En fazla 4 eşzamanlı bağlantı ve bağlantı başına 30 saniye
ilerlemesiz okuma / yazma zaman aşımı uygulanır. GET dosya için Range desteklenmez.
`device_name` en fazla 80 karakterdir; kontrol karakterleri reddedilir. Altı
haneli kod JSON'da string olarak taşınır; başındaki sıfırlar korunur.

## Dosya yaşam döngüsü ve hata davranışı

- Azami dosya boyutu 1 GiB (1.073.741.824 bayt); sıfır baytlık dosya desteklenir.
  Okuma / yazma 128 KiB bloklarla yapılır; dosyanın tamamı RAM'e alınmaz.
- Windows yalnızca kullanıcının seçtiği normal dosyayı uygulama özel geçici
  alana kopyalar; hash bu değişmez kopyadan hesaplanır. Kaynak hazırlanırken
  değişirse / okunamazsa teklif oluşmaz. Kaynak silinmez veya değiştirilmez.
- Windows'ta hazırlık kopyası için yeterli disk alanı gerekir. Android'de özel
  geçici dosya ve hedef kopya için yerel depolamada yaklaşık iki dosya boyutu
  kadar alan kontrol edilir. Sağlayıcı kapasitesi ölçülemiyorsa garanti verilmez;
  yazma hatası yakalanır. Sistem seçicisinde yerel hedef istenir.
- Aktif transfer kimliği tek kaynağa bağlıdır; seçim değişikliği çalışan aktarımı
  başka dosyaya yönlendiremez. Aynı anda ikinci indirme `409` alır.
- Yanlış hash, eksik / fazla gövde, ağ kopması, iptal, ekranın arka plana geçmesi
  veya süre dolması işlemi tamamlanmamış yapar. İlk prototipte yeniden başlatılır;
  kesilen yerden sürdürme ve arka planda devam etme vaat edilmez.
- Başarısız indirme özel geçici alandan temizlenir. Hedefe kopya başarısızsa
  oluşturulan belge silinmeye çalışılır; sağlayıcı silmeyi reddederse kısmi belgenin
  adıyla uyarı gösterilir. Mevcut bir dosya sessizce değiştirilmez. SAF sağlayıcıları
  genel olarak atomik dosya yayınlama garantisi vermediğinden bu sınır açıkça belirtilir.
- Teklif / aktarım durumları: hazırlık → hazır → indiriliyor → alındı onayı
  bekleniyor → tamamlandı; hata ve iptal ayrı son durumlardır. Android başarı
  ekranı yalnızca hedef kaydını da doğruladıktan sonra gösterilir. Bildirim kaybı
  için aynı alındı bildirimi oturum bitene kadar yeniden gönderilebilir.
- Durdurma ve kapanış aktif soketleri kapatır, işçi süreçlerini sonlandırır,
  geçici dosyaları ve sertifika anahtarını temizler. Başlangıçta yalnızca bu
  uygulamanın sahipsiz geçici dosyaları temizlenir; kullanıcı hedeflerine dokunulmaz.

## Arayüz ve izinler

Windows'ta yeni panel mevcut `safe_ui_update` kuyruğunu kullanır. Ağ / disk işçileri
Tk bileşeni okumaz veya güncellemez. Durumlar ve QR ana iş parçacığında gösterilir.
«Bağlantıyı Durdur», «Onayla / Reddet», «Dosya Seç», ilerleme ve sonuç görünür.

Android ekranları: Bağlan → QR Tara → Windows Onayı → Dosya Teklifi → Hedef Seç →
Aktarım → Sonuç. Kamera izni QR taranırken istenir; reddedilince geri dönülebilir.
`INTERNET` manifest izni ve kullanıcı seçimiyle SAF erişimi kullanılır. Genel disk
erişimi (`MANAGE_EXTERNAL_STORAGE`), konum ve tüm galeri izinleri istenmez.
Android sürümüne bağlı yerel ağ izin / kısıtlamaları gerçek cihazda kontrol edilir;
izin reddi veya ağ engeli anlaşılır şekilde gösterilir. Cihaz adı isteğe bağlı
görünen addır; kalıcı donanım kimliği veya kişi bilgisi toplanmaz.

Windows güvenlik duvarında uygulamaya yalnızca özel ağ erişimi verilmesi kullanıcı
kurulum notlarında anlatılır. Uygulama güvenlik duvarını kapatmaz veya otomatik
yönetici komutu çalıştırmaz.

## Derleme ve dağıtım

Android projesi depo kökünde `android/` altında olacak. Paket kimliği
`com.beytarchiver.mobile`, görünen ad `Beytarchiver`, test sürümü `4.0.0-alpha.1`,
`versionCode=1`. Min SDK 26, compile / target SDK 35, Java 17 seçildi. Bu bir
sideload prototipidir; Play Store yayımlama uygunluğu ayrıca değerlendirilecektir.

Başlangıç araç zinciri: AGP 8.7.3, Gradle 8.9, Kotlin / Compose compiler plugin
2.0.21, Compose BOM 2024.12.01, OkHttp 4.12.0, Coroutines 1.9.0, QR için
ZXing Android Embedded 4.3.0. Bunlar aday sabitlemelerdir; ilk CI adımı resmi
uyumluluk notları ve gerçek Gradle derlemesiyle doğrulamalı, gerekirse belgelerle
birlikte güncellemelidir. Dinamik `+` / latest sürümleri kullanılmaz.

`workflow_dispatch` ve ilgili dosyalara gelen push / PR için bir Actions akışı:
Java / SDK kurulumu → Gradle wrapper checksum doğrulama → `testDebugUnitTest`
→ `lintDebug` → `assembleDebug` → debug APK, SHA-256 ve test raporlarını artifact
olarak yükleme. Akış izinleri `contents: read`; publish / release ve kişisel
secret gerektirmez. Wrapper JAR depoda tutulur; çalışma biti korunur. Actions
adımları uygulanırken doğrulanmış tam commit SHA'larına sabitlenir.

Artifact 14 gün tutulur. Her CI ortamında debug anahtarı değişebilir; dolayısıyla
yeni APK önceki kurulumun üzerine kurulamayabilir. İlk prototipte uygulamayı
kaldırıp yeniden yüklemek gerekebilir. Kalıcı dağıtım anahtarı ve güncellemede
veri koruma public sürüm öncesi ayrı iştir. Test APK'sı üretim sürümü diye sunulmaz.

Kullanıcı Android Studio kurmaz: GitHub → Actions → başarılı çalıştırma → Artifacts
→ ZIP'i indir → APK'yı telefona al → ilgili kaynağa kurulum izni ver → kur.
Artifact indirme erişimi için GitHub oturumu gerekebilir.

## Doğrulama ve tamamlanma ölçütü

1. Python: mevcut testler korunur; QR, oturum, TLS, auth, süreler, iptal, değişen
   kaynak, boyut sınırı ve alındı bildirimi için yeni testler geçer.
2. Android: QR / pin, durum yönetimi, streaming hash, limit, iptal ve kısmi hedef
   davranışı için JVM testleri; `lintDebug` ve debug derleme geçer.
3. Entegrasyon: Python HTTPS sunucusu ile Android'in gerçek istemci kütüphanesi
   JVM testinde konuşur. Yanlış pin / token reddedilir; gerçek akışın hash'i eşleşir.
4. Donanım: Windows 11 ve Android 8+ gerçek telefonda APK kurulumu, QR / onay,
   0 bayt ve en az 10 MiB dosya aktarımı, eşleşen SHA-256, kamera izni reddi,
   Wi-Fi kopması, iptal ve uygulama arka plana geçmesi denenir. Kullanıcının
   telefonundaki Android sürümü bu aşamada kaydedilir; daha fazla sürüm destek
   iddiası test matrisine göre genişletilir.

CI başarısı gerçek cihaz aktarımını veya Windows EXE paketlemesini kanıtlamaz.
İlk üç madde tamamlanıp dördüncü madde kullanıcıyla doğrulanmadan prototip
«uçtan uca hazır» ya da «4.0 yayımlandı» olarak tanımlanmaz.

## Uygulama sırasında başvurulacak resmi belgeler

- Android Gradle Plugin: https://developer.android.com/build/releases/past-releases/agp-8-7-0-release-notes
- Dosya seçicisi: https://developer.android.com/training/data-storage/shared/documents-files
- Yerel ağ kısıtlamaları: https://developer.android.com/privacy-and-security/local-network-permission
- Gradle wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- GitHub artifacts: https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts

Bağlantılar uygulama aşamasında doğrulanacak kaynaklardır; bu tasarım çalışmasında
Android SDK kurulumu, Gradle derlemesi veya gerçek cihaz testi çalıştırılmadı.
