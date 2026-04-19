package com.jarvis.android

import android.app.Application
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.jarvis.android.audio.AudioPlayer
import com.jarvis.android.audio.AudioRecorder
import com.jarvis.android.network.JarvisWebSocket
import com.jarvis.android.network.JarvisMessage
import com.jarvis.android.service.WakeWordService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * JARVIS ViewModel — manages connection, audio, and UI state.
 */
class JarvisViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val TAG = "JarvisVM"
        private const val MAX_CHAT_SIZE = 100
        private const val PREFS_CHAT_KEY = "chat_history_json"
        private const val PREFS_AMOLED_KEY = "amoled_enabled"
    }

    // ── State ────────────────────────────────────────────────
    enum class AppState { IDLE, CONNECTING, LISTENING, TRANSCRIBING, THINKING, SPEAKING }

    data class ChatEntry(
        val id: String = UUID.randomUUID().toString(),
        val isUser: Boolean,
        val text: String,
        val imageBase64: String? = null,
    )

    private val _appState = MutableStateFlow(AppState.IDLE)
    val appState: StateFlow<AppState> = _appState.asStateFlow()

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    private val _serverIp = MutableStateFlow("192.168.0.25")
    val serverIp: StateFlow<String> = _serverIp.asStateFlow()

    private val _serverPort = MutableStateFlow(8000)
    val serverPort: StateFlow<Int> = _serverPort.asStateFlow()

    private val _statusText = MutableStateFlow("Connecting…")
    val statusText: StateFlow<String> = _statusText.asStateFlow()

    private val _chatHistory = MutableStateFlow<List<ChatEntry>>(emptyList())
    val chatHistory: StateFlow<List<ChatEntry>> = _chatHistory.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _amoledEnabled = MutableStateFlow(false)
    val amoledEnabled: StateFlow<Boolean> = _amoledEnabled.asStateFlow()

    private val _wakeWordEnabled = MutableStateFlow(false)
    val wakeWordEnabled: StateFlow<Boolean> = _wakeWordEnabled.asStateFlow()

    // Location (set from outside, e.g. MainActivity)
    var lastLatitude: Double? = null
        private set
    var lastLongitude: Double? = null
        private set

    // ── Components ───────────────────────────────────────────
    private var webSocket: JarvisWebSocket? = null
    private val audioRecorder = AudioRecorder(application.applicationContext)
    private val audioPlayer = AudioPlayer()
    private val prefs = application.getSharedPreferences("jarvis_prefs", Context.MODE_PRIVATE)

    // Wake word broadcast receiver
    private val wakeWordReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == WakeWordService.ACTION_WAKE_WORD_DETECTED) {
                Log.i(TAG, "Wake word broadcast received — starting listening")
                haptic()
                if (_isConnected.value && _appState.value == AppState.IDLE) {
                    startListening()
                }
            }
        }
    }

    init {
        // Load saved preferences
        _serverIp.value = prefs.getString("server_ip", "192.168.0.25") ?: "192.168.0.25"
        _serverPort.value = prefs.getInt("server_port", 8000)
        _amoledEnabled.value = prefs.getBoolean(PREFS_AMOLED_KEY, false)
        _wakeWordEnabled.value = prefs.getBoolean("wake_word_enabled", false)

        // Restore chat history
        loadChatHistory()

        // Register wake word receiver
        val filter = IntentFilter(WakeWordService.ACTION_WAKE_WORD_DETECTED)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            application.registerReceiver(wakeWordReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            application.registerReceiver(wakeWordReceiver, filter)
        }

        // Start wake word service if enabled
        if (_wakeWordEnabled.value) {
            startWakeWordService()
        }

        connect()
    }

    // ── AMOLED Toggle ────────────────────────────────────────
    fun setAmoled(enabled: Boolean) {
        _amoledEnabled.value = enabled
        prefs.edit().putBoolean(PREFS_AMOLED_KEY, enabled).apply()
    }

    // ── Location ─────────────────────────────────────────────
    fun updateLocation(lat: Double, lon: Double) {
        lastLatitude = lat
        lastLongitude = lon
    }

    // ── Connection ───────────────────────────────────────────
    fun updateServer(ip: String, port: Int) {
        _serverIp.value = ip
        _serverPort.value = port
        prefs.edit().putString("server_ip", ip).putInt("server_port", port).apply()
        connect()
    }

    fun connect() {
        disconnect()
        _appState.value = AppState.CONNECTING
        _statusText.value = "Connecting…"

        val url = "ws://${_serverIp.value}:${_serverPort.value}/ws/android"

        webSocket = JarvisWebSocket(
            url = url,
            onMessage = ::handleMessage,
            onBinaryMessage = ::handleBinaryMessage,
            onConnected = {
                _isConnected.value = true
                _appState.value = AppState.IDLE
                _statusText.value = "Tap the orb to speak"
                _error.value = null
                haptic()
            },
            onDisconnected = {
                _isConnected.value = false
                _appState.value = AppState.IDLE
                _statusText.value = "Disconnected"
            },
            onError = { msg ->
                _error.value = msg
                _isConnected.value = false
                _statusText.value = "Connection error"
            },
            onReconnecting = { attempt ->
                _statusText.value = "Reconnecting… (attempt $attempt)"
            },
        )
        webSocket?.connect()
    }

    fun disconnect() {
        webSocket?.close()
        webSocket = null
        _isConnected.value = false
        _appState.value = AppState.IDLE
        _statusText.value = "Disconnected"
    }

    // ── Message Handling ─────────────────────────────────────
    private fun handleMessage(msg: JarvisMessage) {
        when (msg.type) {
            "status" -> {
                when (msg.content) {
                    "listening" -> {
                        _appState.value = AppState.LISTENING
                        _statusText.value = "Listening…"
                    }
                    "transcribing" -> {
                        _appState.value = AppState.TRANSCRIBING
                        _statusText.value = "Transcribing…"
                    }
                    "thinking" -> {
                        _appState.value = AppState.THINKING
                        _statusText.value = "Thinking…"
                    }
                    "speaking" -> {
                        _appState.value = AppState.SPEAKING
                        _statusText.value = "Speaking…"
                    }
                    "idle" -> {
                        _appState.value = AppState.IDLE
                        _statusText.value = "Tap the orb to speak"
                    }
                }
            }
            "transcript" -> {
                if (msg.content.isNotBlank() && msg.content != "(no speech detected)") {
                    addChat(isUser = true, msg.content)
                }
            }
            "response" -> {
                if (msg.content.isNotBlank()) {
                    addChat(isUser = false, msg.content)
                    haptic()
                }
            }
            "image" -> {
                // base64 image from screenshot or browser
                if (msg.content.isNotBlank()) {
                    addChat(isUser = false, "", imageBase64 = msg.content)
                }
            }
            "tool_active" -> {
                if (msg.content.isNotBlank()) {
                    _statusText.value = "Using: ${msg.content}"
                }
            }
            "tts_done" -> {
                _appState.value = AppState.IDLE
                _statusText.value = "Tap the orb to speak"
            }
            "error" -> {
                _error.value = msg.content
                _appState.value = AppState.IDLE
                _statusText.value = "Error occurred"
            }
        }
    }

    private fun handleBinaryMessage(data: ByteArray) {
        viewModelScope.launch(Dispatchers.IO) {
            audioPlayer.playMp3Chunk(data)
        }
    }

    private fun addChat(isUser: Boolean, text: String, imageBase64: String? = null) {
        val current = _chatHistory.value.toMutableList()
        current.add(ChatEntry(isUser = isUser, text = text, imageBase64 = imageBase64))
        _chatHistory.value = if (current.size > MAX_CHAT_SIZE) current.takeLast(MAX_CHAT_SIZE) else current
        saveChatHistory()
    }

    fun clearChat() {
        _chatHistory.value = emptyList()
        prefs.edit().remove(PREFS_CHAT_KEY).apply()
    }

    // ── Chat persistence ─────────────────────────────────────
    private fun saveChatHistory() {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val arr = JSONArray()
                _chatHistory.value.takeLast(MAX_CHAT_SIZE).forEach { entry ->
                    val obj = JSONObject().apply {
                        put("id", entry.id)
                        put("isUser", entry.isUser)
                        put("text", entry.text)
                        // Don't persist images (too large for SharedPrefs)
                    }
                    arr.put(obj)
                }
                prefs.edit().putString(PREFS_CHAT_KEY, arr.toString()).apply()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to save chat: ${e.message}")
            }
        }
    }

    private fun loadChatHistory() {
        try {
            val json = prefs.getString(PREFS_CHAT_KEY, null) ?: return
            val arr = JSONArray(json)
            val entries = mutableListOf<ChatEntry>()
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                entries.add(ChatEntry(
                    id = obj.optString("id", UUID.randomUUID().toString()),
                    isUser = obj.getBoolean("isUser"),
                    text = obj.getString("text"),
                ))
            }
            _chatHistory.value = entries
        } catch (e: Exception) {
            Log.e(TAG, "Failed to load chat: ${e.message}")
        }
    }

    // ── Voice ────────────────────────────────────────────────
    fun startListening() {
        if (!_isConnected.value) {
            _error.value = "Not connected to JARVIS"
            return
        }

        audioPlayer.stop()
        webSocket?.sendText("""{"type": "start_listening"}""")

        audioRecorder.startRecording(viewModelScope) { pcmChunk ->
            webSocket?.sendBinary(pcmChunk)
        }
    }

    fun stopListening() {
        audioRecorder.stopRecording()
        webSocket?.sendText("""{"type": "stop_listening"}""")
    }

    fun sendTextInput(text: String) {
        if (text.isBlank() || !_isConnected.value) return
        val obj = JSONObject().apply {
            put("type", "text_input")
            put("text", text)
            lastLatitude?.let { put("lat", it) }
            lastLongitude?.let { put("lon", it) }
        }
        webSocket?.sendText(obj.toString())
        addChat(isUser = true, text)
    }

    fun cancelTask() {
        webSocket?.sendText("""{"type": "cancel"}""")
        audioRecorder.stopRecording()
        _appState.value = AppState.IDLE
        _statusText.value = "Cancelled"
    }

    fun dismissError() { _error.value = null }

    // ── Wake Word ────────────────────────────────────────────
    fun setWakeWordEnabled(enabled: Boolean) {
        _wakeWordEnabled.value = enabled
        prefs.edit().putBoolean("wake_word_enabled", enabled).apply()
        if (enabled) {
            startWakeWordService()
        } else {
            stopWakeWordService()
        }
    }

    private fun startWakeWordService() {
        val ctx = getApplication<Application>()
        val intent = Intent(ctx, WakeWordService::class.java)
        ctx.startForegroundService(intent)
    }

    private fun stopWakeWordService() {
        val ctx = getApplication<Application>()
        ctx.stopService(Intent(ctx, WakeWordService::class.java))
    }

    // ── Haptic ───────────────────────────────────────────────
    private fun haptic() {
        try {
            val ctx = getApplication<Application>().applicationContext
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vm = ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
                vm.defaultVibrator.vibrate(VibrationEffect.createOneShot(40, VibrationEffect.DEFAULT_AMPLITUDE))
            } else {
                @Suppress("DEPRECATION")
                val v = ctx.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
                v.vibrate(VibrationEffect.createOneShot(40, VibrationEffect.DEFAULT_AMPLITUDE))
            }
        } catch (_: Exception) { }
    }

    override fun onCleared() {
        super.onCleared()
        try {
            getApplication<Application>().unregisterReceiver(wakeWordReceiver)
        } catch (_: Exception) { }
        disconnect()
        audioRecorder.release()
        audioPlayer.release()
    }
}
