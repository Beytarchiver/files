package com.beytarchiver.mobile

import com.google.gson.Strictness
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import java.io.StringReader
import java.time.Instant
import java.util.Base64
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl

/** Short-lived credentials; deliberately not a data class (no secret-bearing toString). */
class PairingPayload internal constructor(
    val origin: HttpUrl, val sessionId: String, val certificateSha256: String,
    internal val pairToken: String,
) {
    companion object {
        fun parse(json: String): PairingPayload {
            require(json.toByteArray(Charsets.UTF_8).size <= 2048) { "QR kodu çok büyük." }
            val fields=mutableMapOf<String,String>()
            JsonReader(StringReader(json)).use { reader ->
                reader.strictness=Strictness.STRICT
                reader.beginObject()
                while (reader.hasNext()) {
                    val key=reader.nextName()
                    require(key !in fields) { "Tekrarlanan QR alanı." }
                    if (key=="v") {
                        require(reader.peek()==JsonToken.NUMBER && reader.nextString()=="1") { "Desteklenmeyen protokol." }
                        fields[key]="1"
                    } else {
                        require(reader.peek()==JsonToken.STRING) { "Geçersiz QR alanı." }
                        fields[key]=reader.nextString()
                    }
                }
                reader.endObject()
                require(reader.peek()==JsonToken.END_DOCUMENT)
            }
            require(fields.keys==setOf("v","origin","session_id","cert_sha256","pair_token","expires_at"))
            val raw=fields.getValue("origin")
            val match=Regex("^https://([0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+):([0-9]{1,5})$").matchEntire(raw)
                ?: throw IllegalArgumentException("QR yalnızca özel ağdaki HTTPS adresini içerebilir.")
            val host=match.groupValues[1]
            val octets=host.split('.').map { it.toIntOrNull() ?: -1 }
            require(octets.all { it in 0..255 } && octets.joinToString(".")==host)
            require(octets[0]==10 || (octets[0]==172 && octets[1] in 16..31) || (octets[0]==192 && octets[1]==168))
            val port=match.groupValues[2].toInt()
            require(port in 1..65535 && raw=="https://$host:$port")
            require(Regex("[0-9a-f]{32}").matches(fields.getValue("session_id")))
            require(Regex("[0-9a-f]{64}").matches(fields.getValue("cert_sha256")))
            val token=fields.getValue("pair_token")
            require(Regex("[A-Za-z0-9_-]{43}").matches(token))
            val decoded=Base64.getUrlDecoder().decode(token)
            require(decoded.size==32 && Base64.getUrlEncoder().withoutPadding().encodeToString(decoded)==token)
            val expiry=fields.getValue("expires_at")
            require(expiry.endsWith("Z") && Instant.parse(expiry).isAfter(Instant.now())) { "QR süresi dolmuş. Bilgisayardaki yeni kodu okutun; telefon saatini kontrol edin." }
            return PairingPayload(raw.toHttpUrl(),fields.getValue("session_id"),fields.getValue("cert_sha256"),token)
        }
    }
}
