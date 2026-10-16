package com.beytarchiver.mobile

import java.io.*
import java.nio.file.Files
import java.security.MessageDigest
import org.junit.Assert.*
import org.junit.Test

class ReceiveStoreTest {
    private class Target : Destination {
        var data = byteArrayOf()
        var deleted = false
        var refuseDelete = false
        var failWrite = false
        var corrupt = false
        override fun openOutput(): OutputStream = object : ByteArrayOutputStream() {
            override fun write(b: ByteArray, off: Int, len: Int) {
                if (failWrite) throw IOException("disk full")
                super.write(b,off,len)
            }
            override fun close() { data=toByteArray(); if (corrupt) data=byteArrayOf(99) }
        }
        override fun openInput(): InputStream = data.inputStream()
        override fun delete(): Boolean { deleted = !refuseDelete; return deleted }
    }
    private fun offer(data: ByteArray) = FileOffer("a".repeat(32), "sample.bin", data.size.toLong(),
        MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) })

    @Test fun successfulAndEmptyCopiesAreVerified() {
        for (data in listOf(byteArrayOf(), "hello".toByteArray())) {
            val directory=Files.createTempDirectory("receive-test").toFile()
            try {
                val target=Target()
                ReceiveStore(directory) { Long.MAX_VALUE }.receive(data.inputStream(),offer(data),target)
                assertArrayEquals(data,target.data); assertFalse(target.deleted)
                assertTrue(directory.listFiles()!!.isEmpty())
            } finally { directory.deleteRecursively() }
        }
    }
    @Test fun rejectsTruncationExtraDataAndBadHash() {
        for (incoming in listOf(byteArrayOf(1), byteArrayOf(1,2,3))) {
            val directory=Files.createTempDirectory("receive-test").toFile()
            try {
                val target=Target()
                assertTrue(runCatching { ReceiveStore(directory).receive(incoming.inputStream(),offer(byteArrayOf(1,2)),target) }.isFailure)
                assertTrue(target.deleted); assertTrue(directory.listFiles()!!.isEmpty())
            } finally { directory.deleteRecursively() }
        }
        val directory=Files.createTempDirectory("receive-test").toFile()
        try {
            val target=Target()
            assertTrue(runCatching { ReceiveStore(directory).receive(byteArrayOf(8,9).inputStream(),offer(byteArrayOf(1,2)),target) }.isFailure)
            assertTrue(target.deleted)
        } finally { directory.deleteRecursively() }
    }
    @Test fun targetFailuresAndCancellationNeverReportSuccess() {
        for (scenario in 0..3) {
            val directory=Files.createTempDirectory("receive-test").toFile()
            try {
                val target=Target().apply { failWrite=scenario==0 || scenario==3; corrupt=scenario==1; refuseDelete=scenario==3 }
                val result=runCatching { ReceiveStore(directory).receive("hi".byteInputStream(),offer("hi".toByteArray()),target,cancelled={scenario==2}) }
                assertTrue(result.isFailure)
                if (scenario==3) assertTrue(result.exceptionOrNull() is PartialDestinationException)
                else assertTrue(target.deleted)
                assertTrue(directory.listFiles()!!.isEmpty())
            } finally { directory.deleteRecursively() }
        }
    }
    @Test fun checksFreeSpaceBeforeReading() {
        val directory=Files.createTempDirectory("receive-test").toFile()
        try {
            val target=Target()
            assertTrue(runCatching { ReceiveStore(directory) { 0 }.receive("hi".byteInputStream(),offer("hi".toByteArray()),target) }.isFailure)
            assertTrue(target.deleted)
        } finally { directory.deleteRecursively() }
    }
}
