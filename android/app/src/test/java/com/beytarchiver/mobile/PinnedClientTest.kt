package com.beytarchiver.mobile

import java.security.MessageDigest
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test

class PinnedClientTest {
    private fun fingerprint(cert: HeldCertificate) = MessageDigest.getInstance("SHA-256")
        .digest(cert.certificate.encoded).joinToString("") { "%02x".format(it) }

    @Test fun trustsOnlyPinnedCertificateWithCorrectHostname() {
        val cert=HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val tls=HandshakeCertificates.Builder().heldCertificate(cert).build()
        MockWebServer().use { server ->
            server.useHttps(tls.sslSocketFactory(),false); server.start()
            server.enqueue(MockResponse().setBody("ok"))
            val good=PinnedClient.create(server.url("/"),fingerprint(cert))
            good.newCall(Request.Builder().url(server.url("/test")).build()).execute().use { assertEquals("ok",it.body!!.string()) }
            val bad=PinnedClient.create(server.url("/"),"0".repeat(64))
            assertTrue(runCatching { bad.newCall(Request.Builder().url(server.url("/test")).build()).execute() }.isFailure)
            good.connectionPool.evictAll(); bad.connectionPool.evictAll()
        }
    }
    @Test fun rejectsWrongHostnameEvenWhenPinMatches() {
        val cert=HeldCertificate.Builder().addSubjectAlternativeName("wrong-host").build()
        MockWebServer().use { server ->
            server.useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(),false);server.start()
            val client=PinnedClient.create(server.url("/"),fingerprint(cert))
            assertTrue(runCatching { client.newCall(Request.Builder().url(server.url("/")).build()).execute() }.isFailure)
            client.connectionPool.evictAll()
        }
    }
    @Test fun neverFollowsRedirectsOrSendsTokensToOtherOrigins() {
        val cert=HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        MockWebServer().use { server -> MockWebServer().use { other ->
            other.start()
            server.useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(),false);server.start()
            server.enqueue(MockResponse().setResponseCode(302).addHeader("Location",other.url("/steal")))
            val client=PinnedClient.create(server.url("/"),fingerprint(cert))
            client.newCall(Request.Builder().url(server.url("/")).header("Authorization","Bearer test-only").build()).execute().use {
                assertEquals(302,it.code)
            }
            assertTrue(runCatching { client.newCall(Request.Builder().url(other.url("/steal")).build()).execute() }.isFailure)
            assertEquals(0,other.requestCount)
            client.connectionPool.evictAll()
        } }
    }
}
