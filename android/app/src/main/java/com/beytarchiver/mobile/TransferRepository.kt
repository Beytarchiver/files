package com.beytarchiver.mobile

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.io.IOException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response

sealed interface TransferState {
    data object Idle:TransferState
    data object Pairing:TransferState
    data class AwaitingApproval(val code:String):TransferState
    data object WaitingForOffer:TransferState
    data class Offered(val offer:FileOffer):TransferState
    data class Receiving(val bytes:Long,val total:Long):TransferState
    data object Saving:TransferState
    data class Complete(val name:String,val receiptConfirmed:Boolean,val sha256:String,
                        val sendingReceipt:Boolean=false):TransferState
    data object Cancelled:TransferState
    data class Error(val message:String):TransferState
}

class TransferRepository(
    private val pairing:PairingPayload, private val store:ReceiveStore,
    private val client:OkHttpClient = PinnedClient.create(pairing.origin,pairing.certificateSha256),
    private val pollIntervalMillis:Long = 1000,
) {
    private val mutableState=MutableStateFlow<TransferState>(TransferState.Idle)
    val state:StateFlow<TransferState> = mutableState.asStateFlow()
    private val cancelled=AtomicBoolean(false)
    private val savedFile=AtomicBoolean(false)
    private val saveLock=Any()
    private val activeCall=AtomicReference<Call?>(null)
    @Volatile private var accessToken:String?=null
    @Volatile private var activeOffer:FileOffer?=null
    private var pendingReceipt:FileOffer?=null

    private fun ensureActive() { if (cancelled.get()) throw CancellationException("Aktarım iptal edildi.") }

    private fun request(path:String,body:JsonObject?=null,token:String?=null):Request {
        val builder=Request.Builder().url(pairing.origin.newBuilder().encodedPath(path).build())
        if (token!=null) builder.header("Authorization","Bearer $token")
        if (body!=null) builder.post(body.toString().toRequestBody("application/json".toMediaType()))
        return builder.build()
    }

    private fun <T> withResponse(request:Request,block:(Response)->T):T {
        ensureActive()
        val call=client.newCall(request)
        check(activeCall.compareAndSet(null,call)) { "Bir işlem zaten sürüyor." }
        try {
            if (cancelled.get()) { call.cancel();ensureActive() }
            return call.execute().use { response -> ensureActive();block(response) }
        } finally { activeCall.compareAndSet(call,null) }
    }

    private fun checkStatus(response:Response,expected:Int) {
        if (response.code!=expected) throw IOException(when(response.code) {
            401 -> "Bağlantı yetkisi geçersiz; yeniden eşleştirin."
            410 -> "Bağlantı süresi doldu; yeni QR kodunu okutun."
            409 -> "Bilgisayarda başka bir işlem sürüyor veya aktarım iptal edildi."
            429 -> "Çok sık istek gönderildi; yeniden bağlanın."
            else -> "Bilgisayar beklenmeyen bir yanıt verdi (${response.code})."
        })
    }

    private fun json(path:String,body:JsonObject?=null,token:String?=null,expected:Int=200,allowEmpty:Boolean=false):JsonObject? =
        withResponse(request(path,body,token)) { response ->
            if (allowEmpty && response.code==204) null
            else {
                checkStatus(response,expected)
                val stream=response.body?.byteStream() ?: throw IOException("Boş sunucu yanıtı.")
                val output=java.io.ByteArrayOutputStream()
                val buffer=ByteArray(4096)
                while (true) {
                    val n=stream.read(buffer)
                    if (n<0) break
                    if (output.size()+n>16384) throw IOException("Sunucu yanıtı çok büyük.")
                    output.write(buffer,0,n)
                }
                try { JsonParser.parseString(output.toString("UTF-8")).asJsonObject }
                catch (error:Exception) { throw IOException("Geçersiz sunucu yanıtı.",error) }
            }
        }

    private fun field(json:JsonObject,key:String,pattern:String):String {
        val value=json[key]
        if (value==null || !value.isJsonPrimitive || !value.asJsonPrimitive.isString) throw IOException("Geçersiz $key alanı.")
        return value.asString.also { if (!Regex(pattern).matches(it)) throw IOException("Geçersiz $key alanı.") }
    }

    suspend fun pairAndAwaitOffer(deviceName:String):FileOffer = withContext(Dispatchers.IO) {
        try {
            ensureActive();mutableState.value=TransferState.Pairing
            val body=JsonObject().apply {
                addProperty("session_id",pairing.sessionId);addProperty("pair_token",pairing.pairToken)
                addProperty("device_name",deviceName.take(80).filter { it.code>=32 && it.code!=127 })
            }
            val pair=json("/v1/pair",body,expected=202)!!
            val requestId=field(pair,"request_id","[0-9a-f]{32}")
            val pollToken=field(pair,"poll_token","[A-Za-z0-9_-]{43}")
            mutableState.value=TransferState.AwaitingApproval(field(pair,"code","[0-9]{6}"))
            while (true) {
                ensureActive()
                val status=json("/v1/pair/$requestId",token=pollToken)!!
                when(field(status,"status","pending|approved|rejected")) {
                    "approved" -> { accessToken=field(status,"access_token","[A-Za-z0-9_-]{43}");break }
                    "rejected" -> throw IOException("Bilgisayar bağlantıyı reddetti veya onay süresi doldu.")
                }
                delay(pollIntervalMillis)
            }
            mutableState.value=TransferState.WaitingForOffer
            while (true) {
                ensureActive()
                val data=json("/v1/offer",token=accessToken,allowEmpty=true)
                if (data!=null) {
                    val rawSize=data["size"]
                    if (rawSize==null || !rawSize.isJsonPrimitive || !rawSize.asJsonPrimitive.isNumber ||
                        !Regex("0|[1-9][0-9]{0,9}").matches(rawSize.asString)) throw IOException("Geçersiz dosya boyutu.")
                    val offer=FileOffer(field(data,"transfer_id","[0-9a-f]{32}"),
                        field(data,"name","[^\\p{Cntrl}]{1,255}"),rawSize.asLong,
                        field(data,"sha256","[0-9a-f]{64}"))
                    activeOffer=offer;mutableState.value=TransferState.Offered(offer)
                    return@withContext offer
                }
                delay(pollIntervalMillis)
            }
            @Suppress("UNREACHABLE_CODE") error("unreachable")
        } catch (error:Exception) { fail(error);throw error }
    }

    suspend fun receive(offer:FileOffer,target:Destination) = withContext(Dispatchers.IO) {
        var handledByStore=false
        var saved=false
        try {
            ensureActive()
            check(offer==activeOffer && accessToken!=null) { "Önce bilgisayarın onayını bekleyin." }
            mutableState.value=TransferState.Receiving(0,offer.size)
            withResponse(request("/v1/files/${offer.transferId}",token=accessToken)) { response ->
                checkStatus(response,200)
                val body=response.body ?: throw IOException("Dosya yanıtı boş.")
                if (body.contentLength()!=offer.size) throw IOException("Dosya boyutu teklif ile eşleşmiyor.")
                handledByStore=true
                store.receive(body.byteStream(),offer,target,cancelled={cancelled.get()},
                    progress={bytes,total -> mutableState.value=TransferState.Receiving(bytes,total)},
                    saving={mutableState.value=TransferState.Saving},committed={
                        synchronized(saveLock) {
                            ensureActive();savedFile.set(true);pendingReceipt=offer
                            mutableState.value=TransferState.Complete(offer.name,false,offer.sha256,sendingReceipt=true)
                        }
                    })
            }
            saved=true
            val confirmed=runCatching { sendReceipt(offer) }.isSuccess
            if (confirmed) pendingReceipt=null
            mutableState.value=TransferState.Complete(offer.name,confirmed,offer.sha256)
        } catch (error:Exception) {
            if (savedFile.get()) {
                mutableState.value=TransferState.Complete(offer.name,false,offer.sha256)
                return@withContext
            }
            var reported:Exception=error
            if (!handledByStore && !saved && !runCatching { target.delete() }.getOrDefault(false)) reported=PartialDestinationException(error)
            fail(reported);throw reported
        }
    }

    private fun sendReceipt(offer:FileOffer) {
        json("/v1/receipt",JsonObject().apply {
            addProperty("transfer_id",offer.transferId);addProperty("size",offer.size);addProperty("sha256",offer.sha256)
        },accessToken)
    }

    suspend fun retryReceipt() = withContext(Dispatchers.IO) {
        val offer=pendingReceipt ?: return@withContext
        mutableState.value=TransferState.Complete(offer.name,false,offer.sha256,sendingReceipt=true)
        try {
            sendReceipt(offer);pendingReceipt=null
            mutableState.value=TransferState.Complete(offer.name,true,offer.sha256)
        } catch (error:Exception) {
            mutableState.value=TransferState.Complete(offer.name,false,offer.sha256)
            throw error
        }
    }

    private fun fail(error:Exception) {
        mutableState.value=if (error is PartialDestinationException) TransferState.Error(error.message!!)
            else if (cancelled.get() || error is CancellationException) TransferState.Cancelled
            else TransferState.Error(error.message ?: "Bağlantı kurulamadı.")
    }

    fun cancel() {
        synchronized(saveLock) {
            if (savedFile.get()) return
            cancelled.set(true);mutableState.value=TransferState.Cancelled
        }
        activeCall.getAndSet(null)?.cancel()
        val token=accessToken;val offer=activeOffer
        if (token!=null && offer!=null) {
            val call=client.newCall(request("/v1/cancel",JsonObject().apply { addProperty("transfer_id",offer.transferId) },token))
            call.timeout().timeout(2,java.util.concurrent.TimeUnit.SECONDS)
            call.enqueue(object:okhttp3.Callback {
                override fun onFailure(call:Call,e:IOException) { client.connectionPool.evictAll() }
                override fun onResponse(call:Call,response:Response) { response.close();client.connectionPool.evictAll() }
            })
        }
    }

    fun close() {
        cancel();cancelled.set(true);activeCall.getAndSet(null)?.cancel()
        accessToken=null;activeOffer=null;pendingReceipt=null
        client.connectionPool.evictAll()
    }
}
