package com.jarvis.android.network

import android.util.Log
import okhttp3.*
import okio.ByteString
import java.util.concurrent.TimeUnit

data class JarvisMessage(
    val type: String,
    val content: String,
    val extra: Map<String, String> = emptyMap()
)

/**
 * OkHttp WebSocket client for JARVIS backend.
 * Handles text (JSON) and binary (audio) frames.
 * Auto-reconnects with exponential backoff.
 */
class JarvisWebSocket(
    private val url: String,
    private val onMessage: (JarvisMessage) -> Unit,
    private val onBinaryMessage: (ByteArray) -> Unit,
    private val onConnected: () -> Unit,
    private val onDisconnected: () -> Unit,
    private val onError: (String) -> Unit,
    private val onReconnecting: ((Int) -> Unit)? = null,
) {
    companion object {
        private const val TAG = "JarvisWS"
        private const val INITIAL_DELAY_MS = 1000L
        private const val MAX_DELAY_MS = 30000L
        private const val BACKOFF_FACTOR = 2.0
    }

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(30, TimeUnit.SECONDS)
        .build()

    private var ws: WebSocket? = null
    private var shouldReconnect = true
    private var reconnectAttempt = 0

    fun connect() {
        shouldReconnect = true
        reconnectAttempt = 0
        doConnect()
    }

    private fun doConnect() {
        Log.i(TAG, "Connecting to $url (attempt ${reconnectAttempt + 1})")

        val request = Request.Builder().url(url).build()
        ws = client.newWebSocket(request, object : WebSocketListener() {

            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "Connected")
                reconnectAttempt = 0  // reset on successful connection
                onConnected()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = org.json.JSONObject(text)
                    val msg = JarvisMessage(
                        type = json.optString("type", ""),
                        content = json.optString("content", ""),
                    )
                    onMessage(msg)
                } catch (e: Exception) {
                    Log.e(TAG, "Parse error: $e")
                }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                onBinaryMessage(bytes.toByteArray())
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "Closing: $code $reason")
                webSocket.close(1000, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "Closed: $code")
                onDisconnected()
                scheduleReconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "Failure: ${t.message}")
                onError(t.message ?: "Connection failed")
                onDisconnected()
                scheduleReconnect()
            }
        })
    }

    fun sendText(text: String) {
        ws?.send(text) ?: Log.w(TAG, "sendText: not connected")
    }

    fun sendBinary(data: ByteArray) {
        ws?.send(ByteString.of(*data)) ?: Log.w(TAG, "sendBinary: not connected")
    }

    fun close() {
        shouldReconnect = false
        reconnectAttempt = 0
        ws?.close(1000, "User disconnect")
        ws = null
    }

    private fun scheduleReconnect() {
        if (!shouldReconnect) return
        reconnectAttempt++
        val delay = (INITIAL_DELAY_MS * Math.pow(BACKOFF_FACTOR, (reconnectAttempt - 1).toDouble()))
            .toLong()
            .coerceAtMost(MAX_DELAY_MS)
        Log.i(TAG, "Reconnecting in ${delay}ms (attempt $reconnectAttempt)")
        onReconnecting?.invoke(reconnectAttempt)
        Thread {
            Thread.sleep(delay)
            if (shouldReconnect) {
                doConnect()
            }
        }.start()
    }
}
