package com.beytarchiver.mobile

import java.io.IOException
import java.net.Proxy
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager
import okhttp3.ConnectionSpec
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.TlsVersion

object PinnedClient {
    fun create(origin: HttpUrl, fingerprint: String): OkHttpClient {
        require(origin.isHttps && origin.username.isEmpty() && origin.password.isEmpty())
        require(Regex("[0-9a-f]{64}").matches(fingerprint))
        val expected=fingerprint.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        val trust=object:X509TrustManager {
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                throw CertificateException("Client certificates are not supported")
            }
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                if (chain==null || chain.size!=1) throw CertificateException("Unexpected certificate chain")
                val cert=chain[0]
                cert.checkValidity()
                if (!MessageDigest.isEqual(expected,MessageDigest.getInstance("SHA-256").digest(cert.encoded))) {
                    throw CertificateException("Computer certificate does not match QR")
                }
                cert.verify(cert.publicKey)
            }
        }
        val tls=SSLContext.getInstance("TLS").apply { init(null,arrayOf(trust),null) }
        return OkHttpClient.Builder()
            .sslSocketFactory(tls.socketFactory,trust)
            // Keep OkHttp's normal SAN / hostname verification as well as the pin.
            .connectionSpecs(listOf(ConnectionSpec.Builder(ConnectionSpec.MODERN_TLS)
                .tlsVersions(TlsVersion.TLS_1_3,TlsVersion.TLS_1_2).build()))
            .protocols(listOf(Protocol.HTTP_1_1)).proxy(Proxy.NO_PROXY)
            .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
            .connectTimeout(10,TimeUnit.SECONDS).readTimeout(30,TimeUnit.SECONDS).writeTimeout(30,TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val url=chain.request().url
                if (!url.isHttps || url.host!=origin.host || url.port!=origin.port) throw IOException("Farklı sunucuya bağlantı reddedildi.")
                chain.proceed(chain.request())
            }.build()
    }
}
