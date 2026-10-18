# Beytarchiver Android v4.0.1 — Kurulum ve Test Rehberi

Bu test sürümü aynı yerel ağda Windows Beytarchiver'dan Android telefona tek dosya
alma içindir. Android Studio kurulması gerekmez. Android 8.0 (API 26) veya üzeri
hedeflenir; her Android sürümü / telefon modelinde denenmiş olduğu iddia edilmez.

## APK'yı GitHub Actions'tan alma

1. Depoda **Actions → Android debug APK** akışını açın. İlgili commit / dal için
   başarılı (yeşil) çalıştırmayı seçin. Push akışı derlemeyi otomatik başlatır;
   workflow varsayılan dalda bulunduğunda **Run workflow** ile de başlatılabilir.
2. **Artifacts** bölümünden `beytarchiver-android-4.0.1-<commit>` arşivini
   indirin. GitHub oturumu gerekebilir; artifact 14 gün tutulur.
3. ZIP'i açın. `Beytarchiver-4.0.1-debug.apk` ve `SHA256SUMS` bulunur.
   İndirilen APK'nın SHA-256 değerini kontrol etmek için Windows PowerShell'de:

   ```powershell
   Get-FileHash .\Beytarchiver-4.0.1-debug.apk -Algorithm SHA256
   ```

4. APK'yı telefona aktarın. Android'in ilgili dosya yöneticisi veya tarayıcı için
   istediği kaynaktan yükleme iznini verip APK'yı açın. Play Protect'i kapatmanız
   gerekmez. Beklenmeyen bir uyarıda kurulumu durdurup dosyanın kaynağını kontrol edin.

Bu APK debug anahtarıyla imzalanır; Play Store / üretim sürümü değildir. CI ortamları
arasında debug imzası değişebilir. «Paket mevcut uygulamayla çakışıyor» hatasında
önceki alpha uygulamasını kaldırıp yeniden kurmak gerekebilir. Kaldırmak uygulamaya
ait önbelleği ve ayarları siler; kalıcı public imza sonraki yayın aşamasında kurulur.

## Bilgisayar tarafını hazırlama

 Doğrudan Windows Kurulum Sihirbazı (`Beytarchiver_v4.0.1_Setup.exe`) ile kurabilir veya
kaynak koddan çalıştırmak için Python bağımlılıklarını depo kökünden güncelleyebilirsiniz:

```powershell
python -m pip install -r scripts\beytarchiver-requirements.txt
python .\beytarchiver.py
```

Kaynak altındaki `lan_transfer` klasörü de gereklidir; yalnız `beytarchiver.py`
kopyalamak yeterli değildir. EXE yeniden oluşturulacaksa `scripts\build_windows.ps1`
betiğini kullanabilirsiniz.

## İlk aktarım

1. İki cihazı aynı yerel ağa bağlayın. Bilgisayar aynı ağda Ethernet ile de bağlı
   olabilir. Misafir Wi-Fi / istemci izolasyonu veya VPN bağlantıyı engelleyebilir.
2. Bilgisayarda **Telefonla Aktar → ağ arabirimi → Bağlantı Başlat** seçin.
   Güvenlik duvarı sorarsa yalnız **özel ağ** erişimi verin; duvarı kapatmayın.
3. Telefonda **QR Kodunu Tara** ile kamera izni verin. Bilgisayardaki QR'ı okutun.
   QR 120 saniyede yenilenir; ekran görüntüsünü paylaşmayın.
4. İki ekrandaki altı haneli kodu karşılaştırın. Yalnız aynıysa bilgisayardan
   **Kodlar Aynı — Onayla** seçin. Sonra bilgisayarda **Dosya Seç** kullanın.
5. Telefonda **Al ve Kaydet** ile sistem seçicisinden yerel hedef seçin.
   Azami boyut 1 GiB; doğrulama kopyaları için yaklaşık iki dosya boyutu kadar
   boş alan gerekir. Hedef sağlayıcı yazma / okuma erişimi vermelidir.
6. Uygulamayı aktarım boyunca açık tutun. Dosya ve hedef kopyasının SHA-256
   doğrulaması bitince başarı görünür. Bilgisayar ancak telefonun alındı bildirimi
   ulaşınca tamamlandı der. Onay ulaşmazsa dosya korunur; telefondan yeniden deneyin.

Arka plana geçiş, Wi-Fi kopması veya iptal durumunda aktarım baştan başlatılır.
Yeni eşleştirme için bilgisayardaki bağlantıyı durdurup yeniden başlatın.
Dosya sağlayıcısı kısmi hedefi silemezse uygulama uyarır; hedefi elle kontrol edin.
İşletim sistemi uygulamayı aniden kapatırsa hedefte boş / kısmi belge kalabilir;
özel staging dosyaları sonraki uygulama açılışında temizlenir.

## Otomatik doğrulama

Depo kökünden Python testleri: `python -m pytest -q` (gerçek Tk testi ekran ister).
Android klasöründe Java 17 ve SDK 35 ile:

```sh
./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug
```

JVM testleri Python sunucusunu başlatıp gerçek OkHttp / TLS bağlantısıyla sıfır
bayt ve blok sınırını geçen ikili dosyayı alır. Python bağımlılıkları kurulu olmalıdır.
Farklı Python yolu gerekiyorsa `BEYT_PYTHON` kullanılır. Yerel testte loopback adresi
yalnız fixture içindir; uygulamanın QR doğrulaması loopback'i kabul etmez.

## Gerçek cihaz kabul tablosu

CI ve JVM başarısı kamera / Android dosya sağlayıcısı veya Windows güvenlik duvarını
gerçek cihazda doğrulamaz. Aşağıdaki maddeler kullanıcıyla denenene kadar bekliyor:

| Kontrol | Sonuç |
|---|---|
| Telefon modeli, Android sürümü, Windows sürümü | Bekliyor |
| APK kurulumu, kamera izni / izin reddi ve QR tarama | Bekliyor |
| Kod karşılaştırması, Windows onayı / reddi | Bekliyor |
| Sıfır bayt ve en az 10 MiB dosya aktarımı | Bekliyor |
| Telefonda gösterilen SHA-256 ile Get-FileHash eşleşmesi | Bekliyor |
| Wi-Fi kopması, iptal ve arka plana geçiş | Bekliyor |
| Hedefte yetersiz alan ve kısmi dosya temizliği | Bekliyor |
| QR / onay / oturum süresinin dolması | Bekliyor |
| Sonraki alpha APK'yı kurma / imza farklılığı | Bekliyor |
