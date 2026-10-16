package com.beytarchiver.mobile

import com.google.gson.JsonParser
import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.*
import org.junit.Test

class PythonInteropTest {
    @Test fun realPythonServerAndOkHttpVerifyEmptyAndChunkedFiles() = runBlocking {
        val root=File(checkNotNull(System.getProperty("user.dir")))
        val script=File(root,"tests/lan/serve_fixture.py")
        check(script.isFile) { "Python interop fixture missing: $script" }
        for (size in listOf(0,131079)) {
            val work=Files.createTempDirectory("python-interop").toFile()
            val ready=File(work,"ready.json")
            val python=System.getenv("BEYT_PYTHON") ?: "python3"
            val process=ProcessBuilder(python,script.absolutePath,"--ready-file",ready.absolutePath,"--size",size.toString())
                .directory(root).redirectErrorStream(true).redirectOutput(File(work,"fixture.log")).start()
            var repository:TransferRepository?=null
            try {
                val end=System.nanoTime()+TimeUnit.SECONDS.toNanos(15)
                var payload:com.google.gson.JsonObject?=null
                while (System.nanoTime()<end && process.isAlive) {
                    payload=runCatching { JsonParser.parseString(ready.readText()).asJsonObject }.getOrNull()
                    if (payload!=null) break
                    Thread.sleep(25)
                }
                checkNotNull(payload) { "Python fixture did not become ready: ${File(work,"fixture.log").readText()}" }
                val pair=PairingPayload(payload["origin"].asString.toHttpUrl(),payload["session_id"].asString,
                    payload["cert_sha256"].asString,payload["pair_token"].asString)
                repository=TransferRepository(pair,ReceiveStore(File(work,"staging")),pollIntervalMillis=1000)
                val offer=repository.pairAndAwaitOffer("JVM test")
                assertEquals(size.toLong(),offer.size)
                val destination=File(work,"received.bin")
                val target=object:Destination {
                    override fun openOutput()=destination.outputStream()
                    override fun openInput()=destination.inputStream()
                    override fun delete()=destination.delete()
                }
                repository.receive(offer,target)
                assertTrue((repository.state.value as TransferState.Complete).receiptConfirmed)
                assertEquals(offer.sha256,MessageDigest.getInstance("SHA-256").digest(destination.readBytes()).hex())
            } finally {
                repository?.close()
                process.destroy()
                if (!process.waitFor(5,TimeUnit.SECONDS)) { process.destroyForcibly();process.waitFor(5,TimeUnit.SECONDS) }
                work.deleteRecursively()
            }
        }
    }
}
