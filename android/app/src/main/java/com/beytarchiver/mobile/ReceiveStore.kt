package com.beytarchiver.mobile

import java.io.*
import java.security.MessageDigest
import java.util.concurrent.CancellationException

data class FileOffer(val transferId: String,val name: String,val size: Long,val sha256: String) {
    init {
        require(Regex("[0-9a-f]{32}").matches(transferId))
        require(size in 0..MAX_FILE_SIZE)
        require(Regex("[0-9a-f]{64}").matches(sha256))
        require(name.isNotEmpty() && name.length<=255 && name.none { it.code<32 || it.code==127 })
    }
    companion object { const val MAX_FILE_SIZE=1073741824L }
}

interface Destination {
    fun openOutput(): OutputStream
    fun openInput(): InputStream
    fun delete(): Boolean
}

class PartialDestinationException(cause: Throwable?) : IOException(
    "Hedefte kısmi bir dosya kalmış olabilir; dosya yöneticisinden kontrol edin.",cause)

class ReceiveStore(private val directory: File, private val availableBytes: ()->Long = { directory.usableSpace }) {
    init { check(directory.isDirectory || directory.mkdirs()) { "Geçici depolama açılamadı." } }

    fun clearAbandoned() {
        directory.listFiles()?.filter { it.name.startsWith("receive-") && it.name.endsWith(".part") &&
            it.isFile && it.canonicalFile.parentFile==directory.canonicalFile }?.forEach { it.delete() }
    }

    fun receive(input: InputStream,offer: FileOffer,target: Destination,
                cancelled: ()->Boolean = {false},progress: (Long,Long)->Unit = {_,_->},
                saving: ()->Unit = {},committed: ()->Unit = {}) {
        var staged: File?=null
        var success=false
        var failure: Throwable?=null
        fun checkCancelled() { if (cancelled()) throw CancellationException("Aktarım iptal edildi.") }
        try {
            checkCancelled()
            if (availableBytes()<offer.size*2+65536) throw IOException("Geçici dosya ve hedef kopyası için yeterli boş alan yok.")
            staged=File.createTempFile("receive-",".part",directory)
            val digest=MessageDigest.getInstance("SHA-256")
            var count=0L
            val buffer=ByteArray(128*1024)
            staged.outputStream().use { output ->
                while (true) {
                    checkCancelled()
                    val n=input.read(buffer,0,minOf(buffer.size.toLong(),offer.size-count+1).toInt())
                    if (n<0) break
                    if (n==0) continue
                    count+=n
                    if (count>offer.size) throw IOException("Beklenenden fazla veri alındı.")
                    output.write(buffer,0,n);digest.update(buffer,0,n);progress(count,offer.size)
                }
                output.fd.sync()
            }
            if (count!=offer.size || digest.digest().hex()!=offer.sha256) throw IOException("Dosyanın boyut veya SHA-256 doğrulaması başarısız.")
            checkCancelled();saving()
            target.openOutput().use { output -> staged.inputStream().use { source ->
                while (true) {
                    checkCancelled()
                    val n=source.read(buffer)
                    if (n<0) break
                    output.write(buffer,0,n)
                }
                output.flush()
            } }
            val savedDigest=MessageDigest.getInstance("SHA-256")
            var savedCount=0L
            target.openInput().use { saved ->
                while (true) {
                    checkCancelled()
                    val n=saved.read(buffer,0,minOf(buffer.size.toLong(),offer.size-savedCount+1).toInt())
                    if (n<0) break
                    if (n==0) continue
                    savedCount+=n
                    if (savedCount>offer.size) throw IOException("Hedef dosyanın boyutu değişti.")
                    savedDigest.update(buffer,0,n)
                }
            }
            if (savedCount!=offer.size || savedDigest.digest().hex()!=offer.sha256) throw IOException("Hedef dosya doğrulanamadı.")
            checkCancelled();progress(offer.size,offer.size);committed();success=true
        } catch (error: Throwable) {
            failure=error;throw error
        } finally {
            staged?.delete()
            if (!success && !runCatching { target.delete() }.getOrDefault(false)) throw PartialDestinationException(failure)
        }
    }
}

internal fun ByteArray.hex(): String = joinToString("") { "%02x".format(it) }
