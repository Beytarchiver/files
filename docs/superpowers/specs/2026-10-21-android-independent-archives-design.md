# Beytarchiver Android — bağımsız uygulamaya ilk adım

Tarih: 21 Ekim 2026

Durum: Kullanıcı 21 Ekim 2026 tarihinde “uygulama planına geçelim” diyerek bu
tasarımı uygulama planının temeli olarak onayladı. Uygulama planı ayrı incelenecek.
Bu belge tamamlanmış özellik veya yayımlanmış APK anlamına gelmez.

## Amaç ve aşamalar

Beytarchiver Android, bilgisayara ihtiyaç duymadan arşivlerle ve şifreli kasalarla
çalışacak. Bilgisayarla bağlantı isteğe bağlı olacak. Önce Android sağlamlaştırılacak,
ardından iOS ele alınacak. Arşiv ve kasa yerel dosyalarda internet gerektirmeyecek.

Bu tasarım yalnızca ilk teslimatı ayrıntılandırır: mevcut Android uygulamasına
bağımsız dosya seçimi, normal ZIP listeleme, oluşturma ve çıkarma eklemek.
Şifreli ZIP desteği ikinci küçük teslimattır; ürün hedefinden çıkarılmamıştır.
Kasa, çift yönlü aktarım ve internet aktarımı ayrı tasarım ve test aşamalarıdır.

## Konuşmadan korunan ürün kararları

| Alan | Karar |
| --- | --- |
| Arşivler | ZIP açma/oluşturma, içerik listeleme; sonraki teslimatta şifreli ZIP |
| Kasalar | Birden fazla kasa, kasa başına ayrı parola ve şifreleme anahtarı |
| Dosya ekleme | Önce kopyalama ve doğrulama; orijinal varsayılan olarak korunur |
| Orijinali silme | Yalnız başarılı doğrulama sonrasında, ayrı kullanıcı onayıyla |
| Kurtarma | Kasa başına ayrı kurtarma anahtarı; parola yenilemeye olanak sağlar |
| Erişim kaybı | Parola ve kurtarma anahtarı birlikte kaybolursa destek birimi kasayı açamaz |
| Biyometri | Kasa başına isteğe bağlı; parola ve kurtarma anahtarının yerini almaz |
| Kilitleme | Ekran kilitlenince hemen; arka planda varsayılan 30 saniye, ayarlanabilir |
| Kasa yedeği | Her kasayı ayrı şifreli dışarı aktarma ve geri yükleme |
| Aktarım hedefi | Android–Android ve Android–Windows arasında iki yönlü dosya aktarımı |
| Bağlantı hedefi | QR eşleştirme; aynı ağ yanında farklı Wi-Fi ve mobil veri desteği |

Uzak eşleştirme kodu/bağlantısı, hesapsız kullanım, uçtan uca şifreleme,
aktarım sunucusu ve kesintiden sonra sürdürme konuşmada önerildi; ayrıntıları
aktarım aşamasında kararlaştırılacak. Windows `.beyt` biçimiyle uyumluluk henüz
kararlaştırılmadı. Kasa biçimi, kurtarma ve biyometrik anahtar yönetimi bu ilk
teslimatta uygulanmayacak; ayrıca incelenmeden güvenli kabul edilmeyecek.

## Mevcut deponun durumu

- `android/app`: Kotlin, Jetpack Compose ve Material 3; uygulama kimliği
  `com.beytarchiver.mobile`, sürüm `4.0.1`, minSdk 26, compileSdk/targetSdk 35.
- `MainActivity.kt`: QR taraması, kamera izni ve sistem üzerinden hedef belge seçimi.
- `TransferScreen.kt`: bilgisayardan telefona, aynı yerel ağda tek dosya alma ekranı.
- `TransferViewModel.kt`: aktarım durumu ve arka plana geçişte iptal yönetimi.
- `ReceiveStore.kt`: geçici kopya, boyut/SHA-256 doğrulaması, hedef kopyasını tekrar
  okuma ve başarısız işlemde kısmi hedef temizliği.
- Android testlerinde eşleştirme, TLS sabitleme, dosya alma ve Python birlikte
  çalışabilirlik senaryoları bulunuyor. Bunların mevcut sonucu bu incelemede ölçülmedi.
- `.github/workflows/android-debug.yml`: Python testleri; Android birim testleri,
  lint ve debug APK derlemesi için tanımlı akış.
- Başlangıçta `docs/status.json` zaten değiştirilmişti; bu çalışmanın parçası değil.

## Yaklaşım seçimi

Öneri, mevcut Kotlin/Compose uygulamasını genişletmek. Böylece aktarım kodu ve
testlerinden yararlanılır. Yeni ortak platform uygulamasına geçmek mevcut Android
işini yeniden yazdırır; ayrı bir ikinci Android uygulaması ise iki paket ve iki
bakım hattı oluşturur. İlk aşamada bu iki seçenek tercih edilmiyor.

## İlk teslimat: kullanıcı deneyimi

Uygulama iki çalışan bölüme sahip olacak: **Arşivler** ve **Aktarım**.
İlk açılışta Arşivler gösterilecek. Aktarım bölümünde mevcut QR akışı kalacak;
henüz olmayan kasa veya internet aktarımı için çalışıyormuş gibi düğme gösterilmeyecek.

1. **ZIP aç:** Sistem seçicisinden bir yerel ZIP seçilir. Uygulama dosya/klasör
   adlarını ve bilinen boyutlarını listeler. Listeleme dosyaları hedefe çıkarmaz.
2. **Tümünü çıkar:** Kullanıcı bir hedef klasör seçer. Sonuçlar bu hedefte yeni,
   çakışmayan bir alt klasöre yazılır. Mevcut dosyaların üzerine yazılmaz.
3. **ZIP oluştur:** Birden fazla dosya seçilir; sistemin yeni belge oluşturma
   ekranıyla ZIP adı ve kayıt yeri belirlenir. İlk aşamada klasörleri topluca
   içeri alma ve diğer uygulamalardan Paylaş ile alma sonraki teslimata bırakılır.
4. **İlerleme/iptal:** Hazırlama, işleme, doğrulama ve kaydetme durumları gösterilir.
   Boyut bilinmiyorsa sahte yüzde yerine işlenen bayt/dosya sayısı gösterilir.
5. **Sonuç:** Başarı ancak çıktı kapatılıp doğrulandıktan sonra gösterilir.
   Şifreli veya desteklenmeyen bir arşiv anlaşılır hata verir; sessizce atlanmaz.

Kaynaklar hiçbir aşamada değiştirilmez veya silinmez. Aynı isimli oluşturma
girdileri ZIP içinde deterministik `ad (1).uzantı` biçiminde ayrıştırılır ve sonuç
isimleri kullanıcıya gösterilir. Aynı kaynak iki kez seçilmişse bir kez işlenir.

## Bileşenler ve veri akışı

Tek Gradle uygulama modülü korunur; sorumluluklar Kotlin paketlerine ayrılır.

| Bileşen | Sorumluluk |
| --- | --- |
| Uygulama ekranı | Arşivler/Aktarım seçimi, ortak tema ve sistem seçicisi sonuçları |
| `archive/ArchiveScreen` | Girdiler, içerik listesi, ilerleme, iptal ve hata sunumu |
| `archive/ArchiveViewModel` | Tek aktif arşiv işi, iş durumu, iptal ve ekran döndürme |
| `archive/ArchiveService` | ZIP listeleme/oluşturma/çıkarma, doğrulama ve kaynak sınırları |
| `storage/DocumentAccess` | Content URI okuma, hedef oluşturma, yeni çıktıları izleme ve temizleme |
| Mevcut aktarım sınıfları | QR, TLS, aktarım protokolü ve alındı bildirimi |

Akış: sistem seçimi → URI erişim katmanı → özel geçici çalışma alanı → ZIP servisi
→ doğrulanmış yeni çıktı → kullanıcının seçtiği hedef → sonuç doğrulaması.
Arşiv servisi Android ekran sınıflarına bağımlı olmaz; test edilebilir akışlar ve
iptal/ilerleme bildirimleri kullanır. Disk işleri ana UI iş parçacığını engellemez.

Dosya erişimi Storage Access Framework üzerinden yapılır. URI'ler dosya sistemi
yolu varsayılmaz. Tüm depolamaya erişim izni talep edilmez. İlk sürüm yerel dosya
sağlayıcılarını hedefler; bulut sağlayıcısının çevrimdışı çalışacağı vaat edilmez.

## İlk teslimatın hata ve güvenlik kuralları

- ZIP motoru normal ZIP için standart `java.util.zip` API'lerini kullanır.
  Şifreli ZIP için kütüphane seçimi sonraki teslimatın işidir.
- Girdi doğrulaması yalnız `.zip` uzantısına güvenmez; bozuk/eksik ZIP reddedilir.
- Girdi adları hedefe yazmadan denetlenir: mutlak yollar, `..` bileşenleri,
  Windows sürücü/UNC yolları, ters eğik çizgiyle kaçış ve kontrol karakterleri
  reddedilir. Normalleştirmeden sonra yinelenen yollar ve dosya/klasör çakışmaları
  arşivin tamamını reddettirir. Özel çalışma alanı dışına yazılamaz.
- Arşiv girdilerinden sembolik bağlantı, çalıştırılabilir işlem veya cihaz dosyası
  oluşturulmaz; yalnız normal dosya/klasör çıkarılır. İç içe arşiv otomatik açılmaz.
- İlk teslimat için önerilen sabit koruma sınırları: 1 GiB girdi ZIP'i,
  2 GiB toplam açılmış veri, en çok 10.000 girdi ve en çok 32 klasör derinliği.
  ZIP oluşturma girdilerinin toplamı en çok 1 GiB. Bunlar ürünün kalıcı sınırları
  değildir; test edilecek ilk teslimat sınırlarıdır. Başlıktaki boyutlara güvenmek
  yerine akış sırasında gerçek baytlar sayılır; limit aşımında işlem iptal edilir.
- İş başlangıcında özel çalışma alanının boş alanı kontrol edilir. Hedef sağlayıcı
  kullanılabilir alan bildirmiyorsa kesin alan garantisi verilmez; yazma hatası
  yakalanır. Dosyanın tamamı RAM'e alınmaz.
- Çıkarma sırasında CRC ve gerçek boyut denetlenir. Hedefe kopyalanan dosyalar
  tekrar okunup geçici kopyanın SHA-256 değeri ve boyutuyla karşılaştırılır.
  ZIP oluşturma sonucu yeniden okunup girdileri doğrulanır; hedef ZIP de geçici
  ZIP ile bayt boyutu ve SHA-256 üzerinden karşılaştırılır. Özet karşılaştırması
  dosyanın güvenilir bir kişiden geldiğini kanıtladığı şeklinde sunulmaz.
- İptal/hata durumunda yalnız bu işin oluşturduğu çıktılar temizlenir. Silme
  başarısızsa kısmi çıktı konumu gösterilir; başarı mesajı verilmez.
- Ekran döndürme işi çoğaltmaz. İlk teslimat uzun süre arka planda çalışma veya
  kaldığı yerden sürdürme vaat etmez: gerçek arka plana geçişte işlem iptal edilir.
  Sistem dosya seçicisine geçiş bu iptali tetiklemez. İşletim sisteminin süreci
  sonlandırmasından sonra geçici dosyalar temizlenir; hedefte kalan kısmi çıktı
  için iş kaydı üzerinden uyarı gösterilir. Dış hedefe otomatik yeniden yazılmaz.
- Mevcut aktarımın arka plana geçişte iptal davranışı korunur. Sekme geçişi aktif
  işi görünmez bırakmaz; aktif iş varsa kullanıcıya iptal edip geçme seçeneği verilir.

## Kabul ve doğrulama

1. İnternet kapalıyken yerel dosyalarla ZIP oluşturma, listeleme ve çıkarma tamamlanır.
2. Türkçe/Unicode isimler, boş dosya, boş ZIP ve iç içe klasörler doğru işlenir.
3. Oluşturulan ZIP çıkarıldığında her dosyanın baytları kaynakla eşleşir.
4. Bozuk ZIP/CRC, desteklenmeyen şifreleme, yol kaçışı ve limit aşımı kontrollü
   hata verir; kaynaklar ve önceden var olan hedef dosyalar değişmez.
5. Aynı isimler, dosya/klasör çakışmaları ve sağlayıcı izin kaybı test edilir.
6. İptal, alan yetersizliği, yazma/okuma hatası ve silinemeyen kısmi çıktı test edilir.
7. Ekran döndürme, seçiciden vazgeçme, arka plana geçiş ve süreç sonlanması için
   cihaz/emülatör denemeleri yapılır. Masaüstü birim testleri bunların yerine geçmez.
8. Mevcut Android aktarım testleri ve Python protokol testleri geçmeye devam eder.
9. `android` altında `gradlew.bat testDebugUnitTest lintDebug assembleDebug`
   çalıştırılır; mevcut CI akışı da aynı kontrolleri Linux'ta tanımlıyor.
10. Gerçek cihazda eski QR aktarımı ve yeni çevrimdışı ZIP akışı birlikte denenir.

Bu tasarım yazılırken ürün kodu değiştirilmedi ve test/derleme çalıştırılmadı.
Yerel PATH Java 8 JRE gösteriyor; varsayılan `%LOCALAPPDATA%/Android/Sdk` konumu
bulunamadı. Başka JDK/SDK konumları henüz araştırılmadı. Uygulamaya geçişte mevcut
JDK 17/SDK 35 bulunmalı veya uygun bir derleme ortamı hazırlanmalı; APK üretildiği
iddiası ancak başarılı derleme çıktısından sonra yapılmalı.

## Resmî teknik kaynaklar

- Android dosya seçme/kaydetme ve URI erişimi:
  https://developer.android.com/training/data-storage/shared/documents-files
- ZIP çıkarmada yol kaçışı ve boş hedef denetimi:
  https://developer.android.com/privacy-and-security/risks/zip-path-traversal

Kaynaklar 21 Ekim 2026 tarihinde incelendi. Boyut limitleri, paket sınırları ve
aşama sırası bu proje için tasarım önerileridir; Android platform zorunluluğu değildir.
