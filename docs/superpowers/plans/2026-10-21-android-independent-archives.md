# Beytarchiver Android bağımsız arşivler — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mevcut Android uygulamasında, bilgisayar ve internet gerektirmeden normal ZIP listeleme, oluşturma ve çıkarma sağlamak; mevcut QR aktarımını korumak.

**Architecture:** Mevcut tek Kotlin/Compose uygulaması genişletilir. Android'den bağımsız ZIP servisi özel çalışma alanında işlem yapar; URI erişimi ve doğrulanmış çıktının yayımlanması ayrı sorumluluklardır. ViewModel tek işi yönetir, Arşivler/Aktarım ekranı mevcut aktarım protokolünü kullanır.

**Tech Stack:** Mevcut Kotlin 2.0.21, Compose/Material 3, coroutines 1.9.0, JUnit 4.13.2; `java.util.zip`, Android Storage Access Framework. Şifreli ZIP veya yeni üretim kitaplığı eklenmez.

**Spec:** [Onaylı tasarım](../specs/2026-10-21-android-independent-archives-design.md)

## Global Constraints

- `applicationId = com.beytarchiver.mobile`; minSdk 26; compileSdk/targetSdk 35; JDK 17; Gradle 8.9; mevcut bağımlılık sürümleri korunur.
- 1 GiB girdi ZIP'i = `1_073_741_824L`; 2 GiB toplam açılmış veri = `2_147_483_648L`; en çok `10_000` girdi; en çok `32` klasör derinliği.
- ZIP oluşturma girdilerinin toplamı en çok `1_073_741_824L`. Gerçek okunan/yazılan baytlar sayılır; metadata bu sınırların yerine geçmez.
- Kaynaklar değiştirilmez/silinmez, mevcut hedefler ezilmez, yalnız işin oluşturduğu çıktılar temizlenir. İşler disk üzerinde akışla yürütülür.
- Listeleme hedefe dosya çıkarmaz. Çıktılar kapanıp doğrulanmadan başarı gösterilmez. Bilinmeyen boyutta yüzde gösterilmez.
- Başlangıç ekranı Arşivler; diğer bölüm Aktarım. Kasa, şifreli ZIP, Paylaş menüsü, klasörleri topluca içeri alma, internet/çift yönlü aktarım bu teslimatın dışındadır.
- İlk teslimat ön planda çalışır: gerçek arka plana geçiş iptal eder; sistem seçicisi ve ekran döndürme iptal etmez. Devam etme veya arka plan hizmeti eklenmez.
- `docs/status.json` başlangıçta değiştirilmişti; dokunulmaz. Windows uygulaması ve LAN protokolü değiştirilmez. Testleri geçen özellikler dışında sürüm/yayın iddiası yapılmaz.

## Review Focus

1. Boyutu bilinmeyen/yanlış bildirilen veya seçildikten sonra değişen kaynak: akış sınırları ve kaynak özetiyle doğrulama; Görev 1 ve 3.
2. Geçerli görünen ZIP'te bozuk CRC, `a` dosyası ile `a/b` çakışması, 10.001 girdi: dış hedefe yazmadan reddetme; Görev 1 ve 2.
3. Sağlayıcının yazdıktan sonra farklı bayt döndürmesi, izin kaldırılması veya silmeyi reddetmesi: başarı yerine hata/kısmi konum; Görev 4 ve 5.
4. Sürecin dosya oluşturma ile iş kaydını güncelleme arasında ölmesi: muhafazakâr kısmi çıktı uyarısı ve kullanıcı dosyasını silmeme; Görev 4 ve 7.
5. Seçici/QR sırasında döndürme, art arda düğmeye basma veya sekme değiştirme: çift iş ve yanlış iptal olmaması; Görev 6 ve 7.

## Çalışma biçimi ve başlangıç kontrolü

Bu dosya uygulanacak işleri tanımlar; aşağıdaki kutular henüz tamamlanmadı.
Önerilen yürütme: aynı oturumda sırayla uygulama; bağımlılıklar nedeniyle görevler paralel yazılmaz.
Tamamlanmış değişiklikler sonunda ayrı bir inceleme yapılır. Yöntem kullanıcı incelemesinden sonra seçilir.

- [ ] İcra başlangıcında git durumunu ve yönergeleri yeniden oku; `using-git-worktrees` becerisiyle izin verilen konumda izolasyonu değerlendir. Kullanıcı değişikliklerini taşıma veya sıfırlama.
- [ ] JDK 17 ve SDK 35 konumlarını araştır. Önceki kontrolde PATH Java 8 gösteriyor, varsayılan SDK dizini bulunamıyordu. Bulunamazsa izinli çalışma alanında ortam hazırlama veya mevcut CI seçeneğini somutlaştır; derleme mümkün değilse bunu açıkça kaydet.
- [ ] Android testleri için `BEYT_PYTHON` ortam değişkenini mevcut `.venv/Scripts/python.exe` mutlak yoluna ayarla. `PythonInteropTest` aksi durumda `python3` arıyor. Gradle çalıştırılmadan önce JDK/SDK seçimi doğrulanmalı.
- [ ] `android` çalışma dizininde `./gradlew.bat --version` ve `./gradlew.bat --no-daemon testDebugUnitTest lintDebug` çalıştır; mevcut sonucu kaydet. Önceden var olan başarısızlığı yeni değişikliğin başarısı/başarısızlığıyla karıştırma.

Her görevde önce davranış testi yazılır, ilgili testin beklenen nedenle başarısız olduğu görülür, sonra uygulama yazılıp aynı test geçirilir. Derleme ortamı hatası davranış testi başarısızlığı sayılmaz.
Görev sonu commit yalnız o görevin dosyalarını kapsar. `.git` yazımı izinli değilse commit denenerek sınır aşılmaz; değişiklikler ve doğrulama sonucu çalışma alanında tutulur, commit yapılmadığı belirtilir. Push/yayın bu planın parçası değildir.

## Dosya haritası

Tablodaki `M`, `android/app/src/main/java/com/beytarchiver/mobile/`; `T`, `android/app/src/test/java/com/beytarchiver/mobile/`; `I`, `android/app/src/androidTest/java/com/beytarchiver/mobile/` köküdür. Yol kısaltmaları bütün görevlerde aynı anlamdadır.

| Dosyalar | Sorumluluk |
| --- | --- |
| Yeni `M/archive/ArchiveModels.kt` | Limitler, kaynak/girdi/ilerleme ve hata türleri |
| Yeni `M/archive/ArchivePaths.kt` | Yol doğrulama ve çakışmayan oluşturma adları |
| Yeni `M/archive/ArchiveWorkspace.kt` | İşe özel geçici alan, bayt bütçesi, kapatılabilir sonuçlar |
| Yeni `M/archive/ArchiveService.kt` | ZIP inceleme, çıkarma, oluşturma ve doğrulama |
| Yeni `M/storage/DocumentAccess.kt` | URI erişim sözleşmesi ve belge bilgisi |
| Yeni `M/storage/AndroidDocumentAccess.kt` | ContentResolver/DocumentsContract uyarlaması |
| Yeni `M/storage/ArchiveJobJournal.kt` | Kalıcı iş kaydı ve kesinti uyarıları |
| Yeni `M/storage/ArchivePublisher.kt` | Yeni hedef oluşturma, doğrulama ve sınırlı temizlik |
| Yeni `M/archive/ArchiveViewModel.kt` | İş durumu ve yaşam döngüsü |
| Yeni `M/archive/ArchiveScreen.kt`, `M/BeytarchiverScreen.kt` | Arşiv ekranı ve iki bölümün ortak çerçevesi |
| Değişen `M/MainActivity.kt`, `M/TransferScreen.kt` | Sistem seçicileri, ekran bağlama ve mevcut aktarımı ortak çerçeveye yerleştirme |
| Yeni `android/app/src/main/res/values/strings.xml` | Yeni Türkçe UI metinleri |
| Testler `T/archive/`, `T/storage/`, `I/` | Aşağıdaki görevlerde tek tek adlandırılan davranış testleri |
| Değişen `android/app/build.gradle.kts` | Yalnız cihaz/UI test çalıştırıcısı ve test bağımlılıkları |
| Değişen `docs/android-install-and-test.md` | Yeni yerel ZIP akışı ve cihaz kabul tablosu |

## Görev 1: ZIP inceleme, sınırlar ve güvenli adlar

**Files:** Create `M/archive/ArchiveModels.kt`, `ArchivePaths.kt`, `ArchiveWorkspace.kt`, `ArchiveService.kt`; test `T/archive/ArchiveInspectTest.kt`, `ArchivePathsTest.kt`, `ArchiveFixtures.kt`.

**Interfaces — üretilen sözleşme:**

```kotlin
data class ArchiveLimits(val maxZipBytes: Long = 1_073_741_824L,
    val maxExpandedBytes: Long = 2_147_483_648L,
    val maxCreateInputBytes: Long = 1_073_741_824L,
    val maxEntries: Int = 10_000, val maxDepth: Int = 32)
data class ArchiveSource(val id: String, val name: String,
    val declaredBytes: Long?, val open: () -> InputStream)
data class ArchiveEntry(val path: String, val directory: Boolean, val bytes: Long?)
enum class ArchivePhase { PREPARING, PROCESSING, VERIFYING, SAVING }
data class ArchiveProgress(val phase: ArchivePhase, val bytes: Long,
    val total: Long?, val entries: Int)
data class ArchiveCallbacks(val checkCancelled: () -> Unit = {},
    val progress: (ArchiveProgress) -> Unit = {})
enum class ArchiveError { INVALID_OR_UNSUPPORTED, UNSAFE_PATH, CONFLICT,
    LIMIT, NO_SPACE, ACCESS, IO, INTEGRITY }
class ArchiveException(val code: ArchiveError, cause: Throwable? = null) : IOException(cause)
// PreparedArchive : Closeable; val entries: List<ArchiveEntry>, val id: String
// Dahili ZIP dosyası yalnız aynı paketin erişiminde; close() idempotent.
class ArchiveWorkspace(root: File, availableBytes: () -> Long = { root.usableSpace }) {
    fun clearAbandoned() // Yalnız başlangıçta, herhangi bir iş başlamadan çağrılır.
}
class ArchiveService(workspace: ArchiveWorkspace, limits: ArchiveLimits = ArchiveLimits()) {
    fun inspect(source: ArchiveSource, callbacks: ArchiveCallbacks = ArchiveCallbacks()): PreparedArchive
}
```

`PreparedArchive` ve Görev 2'deki `PreparedOutput`, `ArchiveWorkspace.kt` içinde tanımlanır. `ArchivePaths` fonksiyonları: `validateEntry(path: String, directory: Boolean, maxDepth: Int): String`, `allocateNames(names: List<String>): List<String>`. Normalize edilmiş `/` yolları döner; ters eğik çizgi içeren adlar bu teslimatta reddedilir. Klasör derinliği dosya adını saymaz. Örtük ebeveyn klasör + aynı açık klasör kaydı kabul edilir; iki açık kayıt veya dosya/klasör çakışması reddedilir.

- [ ] Testleri yaz: `listsUnicodeDirectoriesAndEmptyZipWithoutExtracting`, `rejectsMalformedEncryptedAndUnsupportedZip`, `rejectsTraversalAndConflictingEntries`, `enforcesActualInputAndEntryLimits`. Bozuk/şifreli örnekleri küçük, sabit test baytlarıyla oluştur; kaynak ve dış hedefin değişmediğini doğrula.

```kotlin
// ArchivePathsTest: seçim sırasını koruyarak çakışmayan ad tahsisi.
assertEquals(listOf("a.txt", "a (1).txt", "a (2).txt"),
    ArchivePaths.allocateNames(listOf("a.txt", "a.txt", "a (1).txt")))
assertThrows(ArchiveException::class.java) {
    ArchivePaths.validateEntry("../secret.txt", false, 32)
}
assertEquals(2_147_483_648L, ArchiveLimits().maxExpandedBytes)
```

- [ ] `./gradlew.bat testDebugUnitTest --tests '*ArchiveInspectTest' --tests '*ArchivePathsTest'` çalıştır; ilkinde eksik API nedeniyle FAIL bekle.
- [ ] Sözleşmeleri uygula: kaynak ZIP'i 128 KiB tamponla özel çalışma alanına kopyala, boyutu akışta sınırla; `ZipFile` ile merkezi dizini açıp girdileri doğrula ve listele. Desteklenmeyen/şifreli/bozuk veri `INVALID_OR_UNSUPPORTED` olur. Listeleme payload bütünlüğünün doğrulandığını iddia etmez.
- [ ] Uzantıdan bağımsız tanıma; mutlak/UNC/sürücü/`..`/kontrol karakteri yolları, yinelenen açık girdiler, önek çakışmaları ve derinlik denetimi ekle. Listeleme sırasında dış hedefe erişme. Özgün isim sırası korunarak önceki tahsislerle çakışmayan ` (n)` adları üret.
- [ ] Aynı testleri geçir. 10.000/10.001 ve 32/33 sınırlarını test et; bayt sınırlarını küçük enjekte edilmiş limitlerle eşik/eşik+1 testiyle ölç, üretim sabitlerini ayrıca assert et. Boş ZIP geçerli, sıfır baytlık rastgele dosya geçersiz olmalı.
- [ ] Görev dosyalarını ayrı kaydet/commit et: `feat(android): inspect local ZIP archives safely`.

## Görev 2: Özel alana doğrulanmış ZIP çıkarma

**Files:** Modify `M/archive/ArchiveService.kt`, `ArchiveWorkspace.kt`; create `T/archive/ArchiveExtractTest.kt`; extend `T/archive/ArchiveFixtures.kt`.

**Interfaces:** Görev 1 `PreparedArchive` tüketilir. `ArchiveService.extract(archive: PreparedArchive, callbacks: ArchiveCallbacks = ArchiveCallbacks()): PreparedOutput` eklenir. `PreparedOutput : Closeable` içinde `val entries: List<StagedEntry>` bulunur; `StagedEntry(path: String, directory: Boolean, file: File?, bytes: Long, sha256: String?)`. Klasörde file/hash null ve bytes 0; dosyada ikisi de doludur. Yalnız bu çıktı çalışma dizini `close()` ile temizlenir; kaynak `PreparedArchive` sahibi tarafından kapatılır.

- [ ] `extractsUnicodeEmptyFilesAndNestedFolders`, `rejectsWrongCrcAndTruncation`, `cancelsAndCleansOnlyItsWorkspace`, `enforcesActualExpandedLimitAndFreeSpace` testlerini yaz. Son testte küçük limitli, çok genişleyen bir ZIP kullan; `.zip` uzantılı iç dosyanın yeniden açılmadığını kontrol et.

```kotlin
// Fixture düzenlemesi: tek "belgeler/ödev.txt" girdisinin baytları expected.
service.inspect(source).use { archive ->
    service.extract(archive).use { output ->
        assertArrayEquals(expected, output.entries.single { !it.directory }.file!!.readBytes())
    }
}
// Bozuk CRC örneği için:
assertEquals(ArchiveError.INTEGRITY,
    assertThrows(ArchiveException::class.java) { service.extract(badCrcArchive) }.code)
```

- [ ] `./gradlew.bat testDebugUnitTest --tests '*ArchiveExtractTest'` çalıştır; yeni davranışın FAIL olduğunu doğrula.
- [ ] Her girdiyi yalnız özel, yeni çalışma kökünün altında normal dosya/klasör olarak çıkar. Kanonik sınırı tekrar doğrula; metadata izinlerini/bağlantı türünü uygulama. CRC32, gerçek boyut ve SHA-256'yı akışta hesapla; `ZipFile` okumasının CRC'yi kendiliğinden denetlediğine güvenme.
- [ ] Başlangıçta boş alanı, her yazımda byte bütçesini denetle; bilinen boyutları ön kontrol olarak kullan. Her tampon adımında iptal kontrolü yap, akışları kapat ve hatada yalnız bu çalışma alanını temizle. CRC/boyut uyuşmazlığı `INTEGRITY`, limit `LIMIT`, alan `NO_SPACE` üretir.
- [ ] Testi geçir; kaynak ZIP ve önceden oluşturulmuş komşu dosyanın hash değerleri değişmemeli. Büyük akış testi dosyanın tamamını RAM'e alan fixture kullanmamalı.
- [ ] Kaydet/commit: `feat(android): extract ZIP files with bounded verified writes`.

## Görev 3: Seçili dosyalardan ZIP oluşturma

**Files:** Modify `M/archive/ArchiveService.kt`; create `T/archive/ArchiveCreateTest.kt`; extend `ArchiveFixtures.kt`.

**Interfaces:** `ArchiveService.create(sources: List<ArchiveSource>, callbacks: ArchiveCallbacks = ArchiveCallbacks()): PreparedOutput`. Sonuç tek dosya girdisidir (`archive.zip`); kullanıcının dış kayıt adı bundan bağımsızdır. `PreparedOutput` ayrıca `val sourceNames: Map<String, String>` taşır: kaynak id → arşivdeki son ad; çıkarma çıktısında bu map boştur.

- [ ] `roundTripsSelectedFiles`, `deduplicatesSourceIdsAndRenamesCollisions`, `countsUnknownSizesFromStream`, `cancellationOrReadFailureLeavesSourcesUntouched` testlerini yaz. Aynı ad ve farklı id farklı girdidir; aynı id bir girdidir. Boş kaynak listesi UI'da başlatılamaz; servis `CONFLICT` ile reddeder, boş dosyalar kabul edilir.

```kotlin
service.create(listOf(first, first, sameNameDifferentId)).use { created ->
    assertEquals(2, created.sourceNames.size)
    val zip = created.entries.single().file!!
    ZipFile(zip).use { assertEquals(2, it.size()) }
}
// Test fikstürüyle oluşturulan ZIP'i service.inspect/extract üzerinden geri aç:
assertArrayEquals(originalBytes, restoredBytes)
```

- [ ] `./gradlew.bat testDebugUnitTest --tests '*ArchiveCreateTest'` çalıştır ve beklenen FAIL'i gör.
- [ ] `ZipOutputStream` ile yaz; URI id bazlı tekilleştir, Görev 1 ad tahsisini kullan. Okunan toplamı 1 GiB ile sınırla. Girdi adını tek güvenli basename'e indir, kontrol karakteri/geçersiz adları `dosya`, `dosya (1)` benzeri adlara dönüştür; son adları UI'a ilet.
- [ ] Her kaynağı bir defa okuyup gerçek bayt boyutu ve SHA-256'sını kaydet; ZIP'i kapattıktan sonra girdilerini yeniden okuyup bu ölçümlerle karşılaştır. Seçimden sonra değişebilen kaynağı tekrar açıp farklı sürümle karşılaştırma. Oluşan ZIP'in boyut/SHA-256'sını `PreparedOutput` içine koy. Uygulamanın kendi çıktısını yeniden açabilmesi için ZIP çıktısını ayrıca `maxZipBytes` ile sınırla; sıkıştırma/başlık ek yükü nedeniyle bu sınır aşılırsa `LIMIT` üret ve daha az dosya seçilmesini bildir. Küçük enjekte edilmiş limitli testle bu durumu doğrula; depolama bütçesi çıktı büyümesini de sayar.
- [ ] Testleri geçir: bilinmeyen/yanlış bildirilen boyut, okuma ortasında hata ve birden fazla `a (1).txt` çakışması da dahil. Kaynak silme çağrısı sıfır olmalı.
- [ ] Kaydet/commit: `feat(android): create and verify local ZIP archives`.

## Görev 4: Hedefe yayımlama, temizleme ve kesinti kaydı

**Files:** Create `M/storage/DocumentAccess.kt`, `ArchiveJobJournal.kt`, `ArchivePublisher.kt`; create `T/storage/ArchivePublisherTest.kt`, `ArchiveJobJournalTest.kt`, `FakeDocumentAccess.kt`.

**Interfaces — Android'den bağımsız URI sözleşmesi:**

```kotlin
data class DocumentInfo(val uri: String, val name: String, val bytes: Long?, val directory: Boolean)
interface DocumentAccess {
    fun stat(uri: String): DocumentInfo
    fun read(uri: String): InputStream
    fun writeNew(uri: String): OutputStream
    fun create(parent: String, name: String, mime: String): DocumentInfo
    fun children(parent: String): List<DocumentInfo>
    fun delete(uri: String): Boolean
}
sealed interface PublishTarget {
    data class NewZip(val uri: String) : PublishTarget
    data class Directory(val treeUri: String, val baseName: String) : PublishTarget
}
data class PublishResult(val location: String, val files: Int, val bytes: Long)
data class RecoveryWarning(val jobId: String, val locations: List<String>)
class ArchiveJobJournal(directory: File) {
    fun begin(jobId: String, locationHint: String)
    fun created(jobId: String, uri: String)
    fun complete(jobId: String)
    fun pending(): List<RecoveryWarning>
    fun dismiss(jobId: String)
}
class ArchivePublisher(documents: DocumentAccess, journal: ArchiveJobJournal) {
    fun publish(output: PreparedOutput, target: PublishTarget,
        callbacks: ArchiveCallbacks = ArchiveCallbacks()): PublishResult
}
```

`NewZip` yalnız bu oturumdaki `ACTION_CREATE_DOCUMENT` sonucudur; rastgele mevcut dosya URI'si kabul edilmez. `writeNew` sahiplik denetimi publisher tarafından yapılan yeni URI'ler içindir. `Directory` hedefinde benzersiz, yeni alt klasör oluşturulur. Alt klasörün gerçek URI'si kayda girer. Klasör oluşturma MIME değeri Android katmanının tanıdığı `vnd.android.document/directory` olur.

- [ ] Hata enjekte edilebilir sahte sağlayıcı ve testleri yaz: `verifiesReadBackBeforeSuccess`, `failureDeletesOnlyOwnedOutputs`, `refusedDeleteRetainsRecoveryWarning`, `processDeathLeavesJournalAndDoesNotRewriteTargets`, `crashBeforeCreatedRecordStillWarnsAtParent`.

```kotlin
// Fake sağlayıcıya önceden var olan sentinel ekle; yazma sonrası bozma etkin.
assertThrows(ArchiveException::class.java) { publisher.publish(output, target) }
assertArrayEquals(sentinelBytes, fake.bytes(sentinelUri))
assertFalse(fake.deletedUris.contains(sentinelUri))
// Silmenin reddedildiği farklı senaryo:
assertTrue(journal.pending().single().locations.isNotEmpty())
```

- [ ] `./gradlew.bat testDebugUnitTest --tests '*ArchivePublisherTest' --tests '*ArchiveJobJournalTest'` çalıştır ve FAIL'i gör.
- [ ] Yazma öncesi `begin`, her yeni belge sonrası `created`, yalnız tüm sonuçlar doğrulanınca `complete` uygula. Günlük uygulamanın `filesDir` altında Gson ile UTF-8 JSON olarak tutulur: şema sürümü 1, iş kimliği, konum ipucu ve oluşturulmuş URI listesi. Geçici dosya + atomik değiştirme ve flush/sync kullanılır. Bozuk kayıt atılmaz; anlaşılır kurtarma uyarısı olarak korunur. Testler kaydı yeniden açarak kesinti davranışını ölçer.
- [ ] Çıkarılan her dosyayı ve oluşan ZIP'i hedefe kopyala; hedef akışını kapatıp yeniden okuyarak boyut/SHA-256 karşılaştır. Aynı kökte önceden bulunan dosyalara yazma; dönen URI girdi/ebeveyn veya önceden var olan belgeyle çakışıyorsa işlemi reddet. Sağlayıcının ad değiştirmesini doğrula ve gerçek kayıt yerini kullan.
- [ ] Hata/iptalde ters oluşturma sırasıyla yalnız kayıtlı yeni dosyaları sil. Yeni klasörü ancak boşluğu okunup doğrulanabiliyorsa sil; rekürsif klasör silmesiyle başka kişinin eklediği dosyayı silme. Temizlik de hata verirse günlük kalır ve konumu gösterilir. Süreç yeniden açıldığında dış URI'lere otomatik silme/yazma yapılmaz.
- [ ] Yazma çağrısından önceki niyet kaydı, create ile created arasındaki çökmede ebeveyn/hedef konumunu uyarı olarak korusun. Özel çalışma alanı artıkları açılışta yalnız doğrulanmış uygulama dizini içinde temizlensin; global temp veya kullanıcı klasörü taranmasın.
- [ ] Testleri geçir; başarılı iş kaydı kapanır, iptal başarılı sayılmaz, bilinmeyen hedef alanı için sahte kapasite garantisi verilmez. Kaydet/commit: `feat(android): publish archives with verification and recovery records`.

## Görev 5: Android URI erişimi

**Files:** Create `M/storage/AndroidDocumentAccess.kt`; create `I/storage/AndroidDocumentAccessTest.kt`, `I/storage/TestDocumentsProvider.kt`, `android/app/src/androidTest/AndroidManifest.xml`; modify `android/app/build.gradle.kts`.

**Interfaces:** `AndroidDocumentAccess(context: Context) : DocumentAccess` Görev 4'ü uygular. `stat` negatif/eksik boyutu null yapar. `create` yeni belge/klasör üretir; `read/writeNew` null akış ve izin hatalarını `ArchiveException(ACCESS/IO)` olarak bildirir; URI'yi dosya yolu olarak çözmez.

- [ ] Cihaz testleri yaz: `contentUrisWorkWithoutFilesystemPaths`, `unknownSizeRemainsNull`, `revokedPermissionFailsWithoutDeletingSource`, `providerRenamesAreReturned`, `failedReadBackNeverReportsSuccess`. Test sağlayıcısı content URI üretir, hata/izin/yeniden adlandırma durumlarını kontrol eder; üretim manifestine eklenmez.
- [ ] `testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"` ve test bağımlılıklarını ekle: `androidx.test:runner:1.6.2`, `androidx.test.ext:junit:1.2.1`; Compose UI testleri için mevcut BOM ile `androidx.compose.ui:ui-test-junit4`, debug için `androidx.compose.ui:ui-test-manifest`. Yalnız test bağımlılıkları; uygulama SDK/Compose sürümünü yükseltme. Çözümleme sorunu varsa rastgele sürüm yükseltmek yerine kaydet.
- [ ] Hazır emülatör/cihazda `./gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=com.beytarchiver.mobile.storage.AndroidDocumentAccessTest` çalıştır; uygulama öncesi beklenen FAIL'i doğrula.
- [ ] ContentResolver ve DocumentsContract ile erişimi uygula; tree URI kökünü ilgili document URI'sine dönüştür, child id'leri sağlayıcıdan al. Cursor/streamleri kapat; yeni üretim depolama izni ekleme. Devamlı URI izni zorunlu değildir; kurtarma uyarısı için saklanan URI erişiminin sürmesini varsayma.
- [ ] Aynı cihaz testlerini geçir. Emülatör/cihaz yoksa derleme ile yetinildiğini açıkça kaydet ve bu kabul kutusunu açık bırak. Kaydet/commit: `feat(android): connect archive storage to document providers`.

## Görev 6: Tek arşiv işi ve yaşam döngüsü

**Files:** Create `M/archive/ArchiveViewModel.kt`; test `T/archive/ArchiveViewModelTest.kt`; mevcut `TransferViewModel.kt` protokol davranışını değiştirme.

**Interfaces:** `ArchiveViewModel(service: ArchiveService, documents: DocumentAccess, publisher: ArchivePublisher, journal: ArchiveJobJournal, ioDispatcher: CoroutineDispatcher = Dispatchers.IO)`. Dış API: `state: StateFlow<ArchiveUiState>`, `inspect(uri: String)`, `create(uris: List<String>, newZipUri: String)`, `extract(treeUri: String)`, `cancel()`, `onBackground()`, `reset()` ve `dismissWarning(jobId: String)`.

`ArchiveUiState` bu dosyada tanımlanır: `Idle`, `Running(progress)`, `Ready(entries)`, `Completed(result, sourceNames)`, `Cancelled`, `Failed(code, message)` durumları; her birine eşlik eden `warnings: List<RecoveryWarning>` aynı state içinde korunur. `PreparedArchive` private kalır; UI'a dosya/akış nesnesi verilmez. Girdiler Görev 4 `stat/read` ile `ArchiveSource` olur.

- [ ] `doubleStartDoesNotDuplicateWork`, `cancelNeverPublishesSuccess`, `backgroundCancelsAndKeepsWarnings`, `reopeningShowsPendingOutputWarning`, `resetClosesPreparedArchive` testlerini yaz. Mevcut testlerdeki gibi test dispatcher ve gerçek geçici dosyalar + fake sağlayıcı kullan.

```kotlin
// Geçit kontrollü fake InputStream ile işi ilerlerken durdur.
model.inspect(uri); model.inspect(uri)
assertEquals(1, fake.sourceOpenCount)
model.onBackground()
// Test dispatcher/işi tamamladıktan sonra:
assertTrue(model.state.value.status is ArchiveStatus.Cancelled)
assertArrayEquals(originalBytes, fake.bytes(uri))
```

Burada `ArchiveUiState(status: ArchiveStatus, warnings: List<RecoveryWarning>)` ve yukarıdaki durumları taşıyan sealed `ArchiveStatus` kullanılır; isimler UI testlerinde de aynıdır.

- [ ] `./gradlew.bat testDebugUnitTest --tests '*ArchiveViewModelTest'` çalıştır ve FAIL'i gör.
- [ ] IO dispatcher üzerinde servis/publisher akışını bağla, `ensureActive()` callback'iyle iptal et. Yeni iş aktifken ikinci başlangıcı reddet; yanlışlıkla oluşturulmuş yeni ZIP hedefi varsa sahipliğine göre temizle/kayıtla. İptali genel hata catch'iyle yutma. İş kimliğiyle geç kalan ilerleme/başarı bildirimini engelle.
- [ ] `finally` ile kaynak/sonuçları kapat; seçili PreparedArchive yalnız Ready durumunda korunur, yeni seçim/reset/onCleared ile kapatılır. İptal temizliği tamamlanana kadar yeni işe başlama. Çalışma alanını uygulama başlangıcında herhangi bir işten önce `clearAbandoned()` ile temizle; Activity yeniden oluştuğunda bunu aktif ViewModel üzerinde tekrarlama. Journal uyarılarını getir; uyarıyı kapatmak dış dosyayı silmez.
- [ ] Testleri geçir ve mevcut `*TransferViewModelTest` testini de çalıştır. Kaydet/commit: `feat(android): manage archive jobs and cancellation`.

## Görev 7: Çalışan ekran, seçiciler ve teslimat doğrulaması

**Files:** Create `M/BeytarchiverScreen.kt`, `M/archive/ArchiveScreen.kt`, `android/app/src/main/res/values/strings.xml`; modify `M/MainActivity.kt`, `M/TransferScreen.kt`, `docs/android-install-and-test.md`; create `I/ArchiveFlowTest.kt`, `I/PickerLifecycleTest.kt`.

**Interfaces:** `BeytarchiverScreen(archiveModel: ArchiveViewModel, transferModel: TransferViewModel, selectedSourceCount: Int, onPickZip: () -> Unit, onPickSources: () -> Unit, onPickOutput: () -> Unit, onPickTree: () -> Unit, onScan: () -> Unit, onTransferDestination: (FileOffer) -> Unit)`; `ArchiveScreen(state: ArchiveUiState, selectedSourceCount: Int, onPickZip: () -> Unit, onPickSources: () -> Unit, onPickOutput: () -> Unit, onPickTree: () -> Unit, onCancel: () -> Unit, onDismissWarning: (String) -> Unit)`. Seçilen kaynak URI listesi Activity-scoped state içinde saklanır; `onSaveInstanceState` ile döndürmede korunur. ZIP oluştur düğmesi yalnız `selectedSourceCount > 0` ve aktif iş yokken etkinleşir. Activity `create` çağrısına bu listeyi ve yeni ZIP hedefini birlikte verir.

- [ ] UI testlerini yaz: `startsInArchivesWithoutCameraPermission`, `localZipRoundTripAndProgress`, `cancelPickerDoesNotStartJob`, `rotationPreservesSelectionAndDoesNotCancel`, `switchingTabsRequiresCancellingActiveJob`, `qrAndTransferPickerStillWork`. Semantik düğme metinleri üzerinden assert et; implementation aynalayan ekran görüntüsü/sabit piksel testleri ekleme.
- [ ] `./gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=com.beytarchiver.mobile.ArchiveFlowTest,com.beytarchiver.mobile.PickerLifecycleTest` çalıştır; yeni akışların FAIL'ini doğrula.
- [ ] `MainActivity` içinde farklı Activity Result launcher'ları bağla: ZIP için OpenDocument, kaynaklar için OpenMultipleDocuments, ZIP hedefi için CreateDocument, çıkarma hedefi için OpenDocumentTree. Content URI kullan; yerel kaynak isteği uygula, kamera iznini yalnız QR düğmesi ister. İptal edilen seçici hiçbir servis işini başlatmaz.
- [ ] Activity-scoped kaydedilebilir state ile seçici/QR/izin penceresi durumunu koru; yalnız gerçekten beklenen dış ekran sırasında arka plan iptalini ertele. Dönüşte bayrağı her sonuçta temizle. Süreç yeniden yaratılırsa eski işi devam ediyor sayma; günlüğü göster. Gerçek Home/arka plan geçişinde mevcut aktarımı ve aktif arşiv işini iptal et.
- [ ] Ortak MaterialTheme/Scaffold ve iki bölüm oluştur. `TransferScreen` içeriğini gerekirse `TransferContent` fonksiyonuna ayır; eski wrapper çağrısını koru. Aktif işte bölüm değiştirme isteği “İptal edip geç” / “Burada kal” sunar; iptal temizliği bitmeden yeni bölümde iş başlatılmaz.
- [ ] Arşiv ekranında tembel liste, dosya/klasör adı ve boyut, aşama/bayt ilerlemesi, iptal ve kayıt konumu göster. Bilinmeyen boyutta belirsiz ilerleme; yüzde gerekiyorsa ölçülmüş toplam kullan. Hata metinlerini kullanıcı diliyle eşle: örneğin `INVALID_OR_UNSUPPORTED` → “Bu ZIP bozuk, şifreli veya henüz desteklenmeyen bir biçimde.” Kasa veya internet aktarımı düğmesi ekleme.
- [ ] Cihaz testlerini geçir. Güncellenmiş rehbere çevrimdışı ZIP adımları, sınırlar, arka planda iptal davranışı, kısmi dosya uyarısı ve mevcut QR kontrolünü ekle. Henüz yapılmayan gerçek cihaz kontrollerini “Bekliyor” bırak.
- [ ] Repo kökünde `./.venv/Scripts/python.exe -m pytest -q`; `android` altında `./gradlew.bat --no-daemon testDebugUnitTest lintDebug assembleDebug` çalıştır. Beklenen: testler PASS, lint fatal/error yok, `app/build/outputs/apk/debug/app-debug.apk` mevcut. Gereken test donanımı/ortamı yoksa bunu ayrı eksik olarak bildir; başarı sayma.
- [ ] API 26 ve hedef API 35 cihaz/emülatöründe yerel sağlayıcıyı dene; bir gerçek Android cihazda uçak modunda ZIP akışını, ardından LAN açıkken eski Windows QR aktarımını dene. Telefon arka plana alınması, ekran döndürme, düşük alan, silme reddi ve süreci kapatıp yeniden açma sonuçlarını kaydet. Bu fiziksel kontroller otomatik testten türetilmez.
- [ ] Son diff'i incele: sadece Android özellik/testleri ve ilgili rehber değişmeli; `.gitignore`, `docs/status.json`, Windows/LAN protokolü ve sırlar etkilenmemeli. Seçilen yürütme yöntemine göre tamamlanmış dal için ayrı incelemeyi yap. Kaydet/commit: `feat(android): deliver independent ZIP workflows alongside QR transfer`.

## Planın kapsam denetimi ve sonraki adım

Tasarımın dosya seçimi/listeleme/oluşturma/çıkarma gereksinimleri Görev 1–3, URI/yayımlama ve kesinti güvenliği Görev 4–5, tek iş/yaşam döngüsü Görev 6–7 ile kapsanır. Mevcut QR akışı Görev 6–7 testleri ve tam regresyonla korunur. Şifreli ZIP, kasa ve internet aktarımı ürün yol haritasında durur; bu plan onlar için uygulama iddiası taşımaz.

Plan incelemesinden sonra önerilen ilk uygulama adımı: JDK/SDK ve mevcut test temelini doğrulamak, ardından **Görev 1** ile başlamak. Test ve derleme çalıştırılmadan APK teslim edildiği söylenmez. Bu belge hazırlanırken uygulama kodu değiştirilmedi, bağımlılık kurulmadı, test/derleme çalıştırılmadı.
