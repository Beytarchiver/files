package com.beytarchiver.mobile

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream

/** Only receives a newly-created URI returned by ACTION_CREATE_DOCUMENT. */
class ContentDestination(private val context:Context,private val uri:Uri):Destination {
    init { require(uri.scheme=="content") { "Sistem dosya seçicisinden bir hedef seçin." } }
    override fun openOutput():OutputStream = context.contentResolver.openOutputStream(uri,"wt")
        ?: throw IOException("Hedef dosya yazılamıyor.")
    override fun openInput():InputStream = context.contentResolver.openInputStream(uri)
        ?: throw IOException("Kaydedilen dosya doğrulama için okunamıyor.")
    override fun delete():Boolean = if (DocumentsContract.isDocumentUri(context,uri)) {
        DocumentsContract.deleteDocument(context.contentResolver,uri)
    } else context.contentResolver.delete(uri,null,null)>0
}
