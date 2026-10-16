package com.beytarchiver.mobile

import com.google.gson.JsonParser
import java.io.*
import java.nio.file.Files
import java.security.MessageDigest
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.concurrent.TimeUnit
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test

class TransferRepositoryTest {
    private class Target : Destination {
        var bytes=byteArrayOf(); var deleted=false
        override fun openOutput(): OutputStream = object:ByteArrayOutputStream() {
            override fun close() { bytes=toByteArray() }
        }
        override fun openInput(): InputStream=bytes.inputStream()
        override fun delete(): Boolean { deleted=true;return true }
    }
    @Test fun approvalPrecedesDownloadAndReceiptFollowsVerifiedSave() = runBlocking {
        val cert=HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        MockWebServer().use { server ->
            server.useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(),false);server.start()
            val pin=MessageDigest.getInstance("SHA-256").digest(cert.certificate.encoded).joinToString("") { "%02x".format(it) }
            val payload=PairingPayload(server.url("/"),"a".repeat(32),pin,"A".repeat(43))
            val bytes="verified file".toByteArray()
            val sha=MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            server.enqueue(MockResponse().setResponseCode(202).setBody("""{"request_id":"${"b".repeat(32)}","poll_token":"${"A".repeat(43)}","code":"001234"}"""))
            server.enqueue(MockResponse().setBody("""{"status":"pending"}"""))
            server.enqueue(MockResponse().setBody("""{"status":"approved","access_token":"${"C".repeat(42)}A"}"""))
            server.enqueue(MockResponse().setBody("""{"transfer_id":"${"c".repeat(32)}","name":"example.txt","size":${bytes.size},"sha256":"$sha"}"""))
            server.enqueue(MockResponse().setBody(String(bytes)))
            server.enqueue(MockResponse().setBody("""{"status":"ok"}"""))
            val dir=Files.createTempDirectory("repository-test").toFile()
            val repo=TransferRepository(payload,ReceiveStore(dir),pollIntervalMillis=1)
            try {
                val offer=repo.pairAndAwaitOffer("Test phone")
                assertTrue(repo.state.value is TransferState.Offered)
                assertEquals(4,server.requestCount)
                val target=Target();repo.receive(offer,target)
                assertArrayEquals(bytes,target.bytes)
                assertFalse(target.deleted)
                assertTrue((repo.state.value as TransferState.Complete).receiptConfirmed)
                val paths=(1..6).map { server.takeRequest().path }
                assertEquals(listOf("/v1/pair","/v1/pair/${"b".repeat(32)}","/v1/pair/${"b".repeat(32)}","/v1/offer","/v1/files/${"c".repeat(32)}","/v1/receipt"),paths)
            } finally { repo.close();dir.deleteRecursively() }
        }
    }

    @Test fun rejectionNeverRequestsFile() = runBlocking {
        val cert=HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        MockWebServer().use { server ->
            server.useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(),false);server.start()
            val pin=MessageDigest.getInstance("SHA-256").digest(cert.certificate.encoded).joinToString("") { "%02x".format(it) }
            server.enqueue(MockResponse().setResponseCode(202).setBody("""{"request_id":"${"b".repeat(32)}","poll_token":"${"A".repeat(43)}","code":"000001"}"""))
            server.enqueue(MockResponse().setBody("""{"status":"rejected"}"""))
            val dir=Files.createTempDirectory("repository-test").toFile()
            val repo=TransferRepository(PairingPayload(server.url("/"),"a".repeat(32),pin,"A".repeat(43)),ReceiveStore(dir),pollIntervalMillis=1)
            try {
                assertTrue(runCatching { repo.pairAndAwaitOffer("phone") }.isFailure)
                assertEquals(2,server.requestCount)
                assertTrue(repo.state.value is TransferState.Error)
            } finally { repo.close();dir.deleteRecursively() }
        }
    }

    @Test fun cancellingAfterVerifiedSavePreservesReceiptRetry() = runBlocking {
        val cert=HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        MockWebServer().use { server ->
            server.useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(),false);server.start()
            val pin=MessageDigest.getInstance("SHA-256").digest(cert.certificate.encoded).hex()
            val bytes="saved file".toByteArray()
            val sha=MessageDigest.getInstance("SHA-256").digest(bytes).hex()
            server.enqueue(MockResponse().setResponseCode(202).setBody("""{"request_id":"${"b".repeat(32)}","poll_token":"${"A".repeat(43)}","code":"001234"}"""))
            server.enqueue(MockResponse().setBody("""{"status":"approved","access_token":"${"C".repeat(42)}A"}"""))
            server.enqueue(MockResponse().setBody("""{"transfer_id":"${"c".repeat(32)}","name":"example.txt","size":${bytes.size},"sha256":"$sha"}"""))
            server.enqueue(MockResponse().setBody(String(bytes)))
            server.enqueue(MockResponse().setResponseCode(503).setHeadersDelay(300,TimeUnit.MILLISECONDS))
            server.enqueue(MockResponse().setBody("""{"status":"ok"}"""))
            val dir=Files.createTempDirectory("repository-test").toFile()
            val repo=TransferRepository(PairingPayload(server.url("/"),"a".repeat(32),pin,"A".repeat(43)),ReceiveStore(dir),pollIntervalMillis=1)
            try {
                val offer=repo.pairAndAwaitOffer("phone")
                repeat(3) { checkNotNull(server.takeRequest(5,TimeUnit.SECONDS)) }
                val target=Target()
                val receive=launch(Dispatchers.Default) { repo.receive(offer,target) }
                assertEquals("/v1/files/${offer.transferId}",server.takeRequest(5,TimeUnit.SECONDS)!!.path)
                assertEquals("/v1/receipt",server.takeRequest(5,TimeUnit.SECONDS)!!.path)
                repo.cancel()
                assertTrue("Verified save must remain complete while receipt waits",repo.state.value is TransferState.Complete)
                receive.join()
                assertArrayEquals(bytes,target.bytes)
                assertFalse(target.deleted)
                assertFalse((repo.state.value as TransferState.Complete).receiptConfirmed)
                repo.retryReceipt()
                assertTrue((repo.state.value as TransferState.Complete).receiptConfirmed)
                assertEquals("/v1/receipt",server.takeRequest(5,TimeUnit.SECONDS)!!.path)
            } finally { repo.close();dir.deleteRecursively() }
        }
    }
}
