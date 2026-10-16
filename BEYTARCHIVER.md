# Beytarchiver 3.7

Python 3.10 veya üzeri ve Tkinter gerekir. Windows sistem araçları (winget,
kayıt defteri, RAM temizleme ve geri dönüşüm kutusu) Windows'a özeldir.

Depo kökünden bağımlılıkları kurun:

```sh
python -m pip install -r beytarchiver-requirements.txt
python "venv/Akıllı_Dosya_Yöneticisi/beytarchiver.py"
```

`venv/Akıllı_Dosya_Yöneticisi` kaynak kod içerir; yeni sanal ortam oluşturmak
için bu klasörün üzerine yazmayın. İsterseniz ayrı bir `.venv` kullanın.

## Şifre kasası

- İlk kullanımda **Kasa Oluştur / Kilidi Aç** ile en az 12 karakterlik bir ana
  parola belirleyin. Ana parolayı unutursanız kayıtlar kurtarılamaz.
- Kayıtlar `~/.beyt_passwords.enc` dosyasında AES-256-GCM ile şifrelenir.
  Anahtarı scrypt türetir; her kaydetmede yeni rastgele nonce kullanılır.
  Ana parola diske kaydedilmez. Yeni dosya tamamlanmadan eski kayıt değiştirilmez.
- Şifreler varsayılan olarak maskelenir; seçili kayıt 15 saniyeliğine gösterilebilir.
  Sekmeden ayrılınca, pencere kapatılınca veya kasa içinde 5 dakika işlem
  yapılmayınca kasa kilitlenir. Bu, Python belleğinin fiziksel olarak
  sıfırlandığına ilişkin bir garanti değildir.
- Eski `~/.beyt_passwords.json` otomatik yüklenmez. Kilidi açtıktan sonra
  **Eski JSON Kayıtlarını İçe Aktar** düğmesiyle onay vererek taşıyabilirsiniz.
  Aynı site için mevcut şifreli kayıt korunur. Eski JSON dosyası silinmez;
  açık metin kopyanın ve varsa yedeklerinin kaldırılması ayrıca gerekir.
- Şifreli dosyanın yedeğini alın. Aynı kasayı birden fazla uygulama örneğinde
  eşzamanlı düzenlemeyin.

## Arşiv çıkartma

ZIP, AES şifreli ZIP / `.beyt`, 7z, TAR, TAR.GZ / TGZ ve tek dosyalık GZ
desteklenir. Varsayılan sınırlar 10.000 kayıt ve toplam 2 GiB açılmış veridir.
Yol geçişleri, bağlantılar, özel dosyalar, Windows'ta tehlikeli dosya adları
ve çakışan yollar reddedilir. Dosyalar önce geçici alanda açılır; hata olursa
hedef klasör oluşmaz. Mevcut hedefin üzerine yazılmaz. Tekrar çıkartmak için
önceki hedefi taşıyın veya yeniden adlandırın. Bu kısıtlamalar bazı güvenilir
ama bağlantı veya platforma özgü dosya adları içeren arşivleri de reddedebilir.

TAR şifrelemeyi desteklemez; parola gerekiyorsa ZIP veya 7z seçin.

## Tarama ve dosya silme

Yerel tarama yalnızca sınırlı uzantı sezgileri ve EICAR test imzasını kontrol eder;
tam bir antivirüs motoru değildir. Uyarı çıkmaması güvenlik garantisi vermez.

Dosya imhası son onaydan sonra normal dosyanın üzerine 1 MiB parçalarla üç
geçiş yazar ve dosyayı siler. Sembolik ve sabit bağlantılar reddedilir.
SSD, dosya sistemi anlık görüntüsü ve yedeklerde fiziksel silme garantisi yoktur.

## Testler

```sh
python -m pip install pytest==9.1.1
python -m pytest -q
```

Dosya işlemleri testlerde yalnızca geçici verilere uygulanır. Linux'ta gerçek
Tk arayüz testi için bir grafik ekranı (`DISPLAY`) gerekir; ekran yoksa bu test
atlanır. Windows sistem araçları ayrıca Windows üzerinde doğrulanmalıdır.

## 4.0 önizleme: bilgisayardan telefona aktarım altyapısı

Masaüstünde **Telefonla Aktar** paneli ve `android/` altında Android alpha istemcisi
eklendi. Test APK'sı Gradle ile üretilebilir; GitHub Actions akışı APK ve SHA-256
artifact'i hazırlar. [Android kurulum ve test adımları](docs/android-install-and-test.md).
Pencere / kurulum sürümü, gerçek cihaz kabul testi tamamlanana kadar 3.7 olarak kalır.

- Bağımlılıkları `python -m pip install -r beytarchiver-requirements.txt` ile güncelleyin.
- Aynı ağa bağlı özel IPv4 arabirimini seçip **Bağlantı Başlat** düğmesini kullanın.
  Birden fazla arabirimde Wi-Fi veya telefonla aynı yerel ağdaki Ethernet'i seçin.
- 120 saniyelik QR, geçici TLS sertifikasının parmak izini ve eşleştirme bilgisini
  içerir. Süresi dolunca yenilenir. QR'ı veya ekran görüntüsünü başkalarıyla paylaşmayın.
- İki cihazdaki altı haneli kodu karşılaştırdıktan sonra **Kodlar Aynı — Onayla**
  seçilir. Cihaz adı tek başına güvenilir kimlik değildir.
- Dosya ancak onaydan sonra seçilir. En fazla 1 GiB, aynı anda tek dosya desteklenir.
  Kaynak değiştirilmez; özel geçici kopya hazırlanıp SHA-256 hesaplanır.
- Bilgisayar yalnızca telefon dosyanın kaydını doğrulayıp alındı bildirimi verince
  tamamlandı gösterir. Gönderim bitmesi tek başına başarılı kayıt sayılmaz.
- **Bağlantıyı Durdur** ve pencereyi kapatma, oturumu / soketleri ve geçici veriyi
  temizler. Ani kapanıştan kalan tanınmış sahipsiz oturum dosyaları sonraki bağlantı
  başlangıcında temizlenir; etkin oturumlar ve tanınmayan dosyalar korunur.
- Windows güvenlik duvarı sorarsa uygulamaya yalnızca **özel ağ** erişimi verin.
  Güvenlik duvarını kapatmayın. Misafir ağı izolasyonu, VPN veya yanlış arabirim
  bağlantıyı engelleyebilir. Telefonun sunucuya ulaşabilmesi gerekir.

Bu prototip genel dosya gezme, uzaktan komut çalıştırma, internetten erişim,
telefondan bilgisayara gönderme veya kesilen aktarıma devam etme sağlamaz.

Windows EXE yeniden derlenecekse kaynak klasöründe, proje sanal ortamı ile:

```powershell
& "..\..\.venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name Beytarchiver --collect-all customtkinter --collect-all tkinterdnd2 --collect-all qrcode beytarchiver.py
```

Bu komutun çıktısı Windows'ta ayrıca denenmelidir; bu Linux ortamında Windows EXE
üretilmez. Android test APK'sı yerel SDK ile derlendi; Python–OkHttp TLS ve hash
uyumluluğu JVM testinde doğrulandı. Gerçek telefon kamerası / dosya sağlayıcısı ve
Windows güvenlik duvarı kabul testleri bekliyor. Protokol örnekleri
`protocol/lan-v1-fixtures.json`, masaüstü regresyonları `tests/lan/` altındadır.
