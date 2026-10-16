package com.beytarchiver.mobile

import java.nio.file.Files
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class TransferViewModelTest {
    @Test fun backgroundingPendingConnectionCancelsItAndInvalidQrNeverConnects() = runBlocking {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        val cert=HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val dir=Files.createTempDirectory("viewmodel-test").toFile()
        try {
            MockWebServer().use { server ->
                server.useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(),false);server.start()
                val pin=MessageDigest.getInstance("SHA-256").digest(cert.certificate.encoded).hex()
                server.enqueue(MockResponse().setResponseCode(202).setBody("""{"request_id":"${"b".repeat(32)}","poll_token":"${"A".repeat(43)}","code":"000123"}"""))
                server.enqueue(MockResponse().setBody("""{"status":"pending"}"""))
                val store=ReceiveStore(dir)
                val model=TransferViewModel(store) { payload, targetStore ->
                    TransferRepository(PairingPayload(server.url("/"),payload.sessionId,pin,payload.pairToken),targetStore)
                }
                try {
                    model.connect("invalid")
                    assertTrue(model.state.value is TransferState.Error)
                    assertEquals(0,server.requestCount)
                    model.connect("""{"v":1,"origin":"https://192.168.1.2:1234","session_id":"${"a".repeat(32)}","cert_sha256":"$pin","pair_token":"${"A".repeat(43)}","expires_at":"2099-01-01T00:00:00Z"}""")
                    val awaiting=withTimeout(5000) { model.state.first { it is TransferState.AwaitingApproval } }
                    assertEquals("000123",(awaiting as TransferState.AwaitingApproval).code)
                    model.onBackground()
                    assertEquals(TransferState.Cancelled,model.state.value)
                } finally { model.disconnect() }
            }
        } finally { dir.deleteRecursively();Dispatchers.resetMain() }
    }
}
