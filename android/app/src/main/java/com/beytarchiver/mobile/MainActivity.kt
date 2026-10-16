package com.beytarchiver.mobile

import android.Manifest
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import java.io.File

class MainActivity:ComponentActivity() {
    private var scanning=false
    private var choosingDestination=false
    private val model:TransferViewModel by viewModels {
        object:ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T:ViewModel> create(modelClass:Class<T>):T =
                TransferViewModel(ReceiveStore(File(application.cacheDir,"incoming"))) as T
        }
    }
    private val scanner=registerForActivityResult(ScanContract()) { result ->
        scanning=false
        result.contents?.let(model::connect)
    }
    private val cameraPermission=registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            scanning=true
            scanner.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setPrompt("Bilgisayardaki Beytarchiver QR kodunu okutun")
                .setBeepEnabled(false).setOrientationLocked(false))
        } else model.showError("QR taramak için kamera izni gerekli. İzni uygulama ayarlarından verebilirsiniz.")
    }
    private val destination=registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        choosingDestination=false
        val uri=result.data?.data
        if (result.resultCode==RESULT_OK && uri!=null) {
            runCatching { ContentDestination(applicationContext,uri) }
                .onSuccess(model::receive)
                .onFailure { model.showError(it.message ?: "Hedef seçilemedi.") }
        }
    }
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { TransferScreen(model,
            scan={ cameraPermission.launch(Manifest.permission.CAMERA) },
            selectDestination={ offer ->
                val suggested=offer.name.replace('\\','/').substringAfterLast('/').take(128).ifBlank { "received.bin" }
                choosingDestination=true
                destination.launch(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE);type="application/octet-stream"
                    putExtra(Intent.EXTRA_TITLE,suggested);putExtra(Intent.EXTRA_LOCAL_ONLY,true)
                })
            }) }
    }
    override fun onStop() {
        if (!isChangingConfigurations && !scanning && !choosingDestination) model.onBackground()
        super.onStop()
    }
}
