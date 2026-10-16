package com.beytarchiver.mobile

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun TransferScreen(model:TransferViewModel,scan:()->Unit,selectDestination:(FileOffer)->Unit) {
    val state by model.state.collectAsStateWithLifecycle()
    MaterialTheme {
        Scaffold { padding ->
            Column(Modifier.fillMaxSize().padding(padding).padding(24.dp)
                .verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(20.dp)) {
                Text("Beytarchiver",style=MaterialTheme.typography.headlineLarge)
                Text("4.0 Alpha · Bilgisayardan telefona",style=MaterialTheme.typography.titleMedium)
                Text("Telefon ve bilgisayar aynı yerel ağda olmalı. Dosyalar buluta yüklenmez.")
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
                        when(val current=state) {
                            TransferState.Idle -> {
                                Text("Bilgisayarda Telefonla Aktar bölümünü açın ve bağlantıyı başlatın.")
                                Button(onClick=scan) { Text("QR Kodunu Tara") }
                            }
                            TransferState.Pairing -> { CircularProgressIndicator();Text("Bilgisayara bağlanılıyor…") }
                            is TransferState.AwaitingApproval -> {
                                Text("İki ekrandaki kod aynı mı?",style=MaterialTheme.typography.titleLarge)
                                Text(current.code,fontFamily=FontFamily.Monospace,style=MaterialTheme.typography.displayMedium)
                                Text("Kodları karşılaştırıp bilgisayardan bağlantıyı onaylayın.")
                            }
                            TransferState.WaitingForOffer -> { CircularProgressIndicator();Text("Eşleşme tamamlandı. Bilgisayardan bir dosya seçin.") }
                            is TransferState.Offered -> {
                                Text(current.offer.name,style=MaterialTheme.typography.titleLarge)
                                Text("${current.offer.size} bayt · En fazla 1 GiB")
                                Text("Yerel depolamada bir hedef seçin. Doğrulama için yaklaşık iki dosya boyutu kadar boş alan gerekir.")
                                Button(onClick={selectDestination(current.offer)}) { Text("Al ve Kaydet") }
                            }
                            is TransferState.Receiving -> {
                                val fraction=if(current.total==0L) 1f else (current.bytes.toDouble()/current.total).toFloat().coerceIn(0f,1f)
                                LinearProgressIndicator(progress={fraction},modifier=Modifier.fillMaxWidth())
                                Text("${current.bytes} / ${current.total} bayt · %${(fraction*100).toInt()}")
                                Text("Uygulamayı açık tutun. Arka plana geçerseniz aktarım iptal edilir.")
                            }
                            TransferState.Saving -> { CircularProgressIndicator();Text("Dosya kaydediliyor ve hedef kopya doğrulanıyor…") }
                            is TransferState.Complete -> {
                                Text("Dosya kaydedildi ve doğrulandı.",style=MaterialTheme.typography.titleLarge)
                                Text(current.name)
                                SelectionContainer { Text("SHA-256: ${current.sha256}",fontFamily=FontFamily.Monospace,
                                    style=MaterialTheme.typography.bodySmall) }
                                if(!current.receiptConfirmed) {
                                    Text(if(current.sendingReceipt) "Bilgisayara alındı onayı gönderiliyor…"
                                        else "Bilgisayara alındı onayı ulaşmadı. Dosya telefonunuzda korunuyor.")
                                    Button(onClick=model::retryReceipt,enabled=!current.sendingReceipt) { Text("Alındı Onayını Tekrar Gönder") }
                                }
                                Button(onClick=model::disconnect) { Text("Yeni Bağlantı") }
                            }
                            TransferState.Cancelled -> {
                                Text("Aktarım iptal edildi. Yeniden eşleştirmek için bilgisayarda bağlantıyı durdurup başlatın.")
                                Button(onClick=model::disconnect) { Text("Başa Dön") }
                            }
                            is TransferState.Error -> {
                                Text(current.message,color=MaterialTheme.colorScheme.error)
                                Text("Wi-Fi bağlantısını, bilgisayardaki özel ağ güvenlik duvarı iznini ve QR süresini kontrol edin.")
                                Button(onClick=model::disconnect) { Text("Başa Dön") }
                            }
                        }
                        if(state !is TransferState.Complete && state !is TransferState.Error && state!=TransferState.Idle && state!=TransferState.Cancelled) {
                            OutlinedButton(onClick=model::cancel) { Text("İptal Et") }
                        }
                    }
                }
                Text("Önizleme sürümü: tek dosya, aynı Wi-Fi, yalnızca bilgisayardan telefona. Kesilen aktarım baştan başlatılır.",
                    style=MaterialTheme.typography.bodySmall)
            }
        }
    }
}
