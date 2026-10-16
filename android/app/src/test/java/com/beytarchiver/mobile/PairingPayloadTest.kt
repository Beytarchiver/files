package com.beytarchiver.mobile

import com.google.gson.JsonParser
import org.junit.Assert.*
import org.junit.Test

class PairingPayloadTest {
    @Test fun sharedProtocolFixtures() {
        val text = javaClass.classLoader!!.getResourceAsStream("lan-v1-fixtures.json")!!
            .bufferedReader().use { it.readText() }
        for (item in JsonParser.parseString(text).asJsonArray) {
            val fixture = item.asJsonObject
            val result = runCatching { PairingPayload.parse(fixture["payload"].asString) }
            assertEquals(fixture["name"].asString, fixture["valid"].asBoolean, result.isSuccess)
        }
    }

    @Test fun rejectsDuplicateFieldsAndHugeInput() {
        val source = """{"v":1,"v":1,"origin":"https://192.168.1.2:1234","session_id":"${"a".repeat(32)}","cert_sha256":"${"b".repeat(64)}","pair_token":"${"A".repeat(43)}","expires_at":"2099-01-01T00:00:00Z"}"""
        assertTrue(runCatching { PairingPayload.parse(source) }.isFailure)
        assertTrue(runCatching { PairingPayload.parse(" ".repeat(2049)) }.isFailure)
    }

    @Test fun rejectsNonCanonicalTokenAndUnsafeOrigins() {
        val good = """{"v":1,"origin":"https://192.168.1.2:1234","session_id":"${"a".repeat(32)}","cert_sha256":"${"b".repeat(64)}","pair_token":"${"A".repeat(43)}","expires_at":"2099-01-01T00:00:00Z"}"""
        for (origin in listOf("https://user@192.168.1.2:1234", "https://192.168.1.2:1234/", "https://169.254.1.1:1234", "https://192.168.1.2:0")) {
            assertTrue(origin, runCatching { PairingPayload.parse(good.replace("https://192.168.1.2:1234", origin)) }.isFailure)
        }
        assertTrue(runCatching { PairingPayload.parse(good.replace("A".repeat(43), "A".repeat(42)+"B")) }.isFailure)
    }
}
