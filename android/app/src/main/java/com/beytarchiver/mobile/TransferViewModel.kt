package com.beytarchiver.mobile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class TransferViewModel(
    private val store:ReceiveStore,
    private val factory:(PairingPayload,ReceiveStore)->TransferRepository = { payload,target -> TransferRepository(payload,target) },
):ViewModel() {
    private val mutableState=MutableStateFlow<TransferState>(TransferState.Idle)
    val state=mutableState.asStateFlow()
    private var repository:TransferRepository?=null
    private var work:Job?=null
    private var collector:Job?=null
    init { store.clearAbandoned() }

    fun connect(raw:String) {
        disconnect()
        try {
            val payload=PairingPayload.parse(raw)
            val session=factory(payload,store)
            repository=session
            collector=viewModelScope.launch { session.state.collect { if (repository===session) mutableState.value=it } }
            work=viewModelScope.launch { runCatching { session.pairAndAwaitOffer("Android") } }
        } catch (error:Exception) { mutableState.value=TransferState.Error(error.message ?: "QR kodu okunamadı.") }
    }

    fun receive(target:Destination) {
        val offer=(state.value as? TransferState.Offered)?.offer
        val session=repository
        if (offer==null || session==null) {
            if (!runCatching { target.delete() }.getOrDefault(false)) mutableState.value=TransferState.Error("Boş hedef dosya silinemedi; dosya yöneticisinden kontrol edin.")
            return
        }
        work=viewModelScope.launch { runCatching { session.receive(offer,target) } }
    }

    fun retryReceipt() {
        val session=repository ?: return
        work=viewModelScope.launch { runCatching { session.retryReceipt() } }
    }

    fun showError(message:String) { mutableState.value=TransferState.Error(message) }

    fun cancel() {
        repository?.cancel()
        work?.cancel()
        mutableState.value=TransferState.Cancelled
    }

    fun onBackground() {
        when(state.value) {
            TransferState.Pairing, is TransferState.AwaitingApproval, TransferState.WaitingForOffer,
            is TransferState.Offered, is TransferState.Receiving, TransferState.Saving -> cancel()
            else -> Unit
        }
    }

    fun disconnect() {
        collector?.cancel();collector=null
        repository?.close();repository=null
        work?.cancel();work=null
        mutableState.value=TransferState.Idle
    }

    override fun onCleared() { disconnect() }
}
