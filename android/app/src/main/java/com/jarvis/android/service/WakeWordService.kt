package com.jarvis.android.service

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.IBinder
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

/**
 * Background service that listens for the "Hey JARVIS" wake phrase.
 * Uses Android's built-in SpeechRecognizer in a loop.
 *
 * When the phrase is detected, broadcasts ACTION_WAKE_WORD_DETECTED
 * which the ViewModel can pick up to start listening.
 */
class WakeWordService : Service() {

    companion object {
        const val TAG = "WakeWord"
        const val ACTION_WAKE_WORD_DETECTED = "com.jarvis.android.WAKE_WORD_DETECTED"
        private const val CHANNEL_ID = "jarvis_wake_word"
        private val WAKE_PHRASES = listOf("jarvis", "hey jarvis", "ok jarvis", "yo jarvis")
    }

    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(2, buildNotification())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!isListening) {
            startWakeWordDetection()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        stopWakeWordDetection()
        super.onDestroy()
    }

    private fun startWakeWordDetection() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "No mic permission — cannot start wake word detection")
            stopSelf()
            return
        }

        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            Log.w(TAG, "Speech recognition not available on this device")
            stopSelf()
            return
        }

        try {
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
                setRecognitionListener(WakeWordListener())
            }
            startRecognition()
            isListening = true
            Log.i(TAG, "Wake word detection started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start speech recognizer: ${e.message}")
        }
    }

    private fun startRecognition() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 1000)
        }
        try {
            speechRecognizer?.startListening(intent)
        } catch (e: Exception) {
            Log.e(TAG, "startListening failed: ${e.message}")
            restartAfterDelay()
        }
    }

    private fun stopWakeWordDetection() {
        isListening = false
        try {
            speechRecognizer?.stopListening()
            speechRecognizer?.cancel()
            speechRecognizer?.destroy()
        } catch (_: Exception) { }
        speechRecognizer = null
        Log.i(TAG, "Wake word detection stopped")
    }

    private fun restartAfterDelay() {
        if (!isListening) return
        android.os.Handler(mainLooper).postDelayed({
            if (isListening) {
                startRecognition()
            }
        }, 500)
    }

    private fun onWakeWordDetected() {
        Log.i(TAG, "🔊 Wake word detected!")
        sendBroadcast(Intent(ACTION_WAKE_WORD_DETECTED))
    }

    private inner class WakeWordListener : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}

        override fun onResults(results: Bundle?) {
            checkForWakeWord(results)
            // Restart listening loop
            restartAfterDelay()
        }

        override fun onPartialResults(partialResults: Bundle?) {
            checkForWakeWord(partialResults)
        }

        override fun onError(error: Int) {
            // Errors like no speech detected, timeout — just restart
            val errorName = when (error) {
                SpeechRecognizer.ERROR_AUDIO -> "AUDIO"
                SpeechRecognizer.ERROR_CLIENT -> "CLIENT"
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "PERMISSIONS"
                SpeechRecognizer.ERROR_NETWORK -> "NETWORK"
                SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "NETWORK_TIMEOUT"
                SpeechRecognizer.ERROR_NO_MATCH -> "NO_MATCH"
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "BUSY"
                SpeechRecognizer.ERROR_SERVER -> "SERVER"
                SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "SPEECH_TIMEOUT"
                else -> "UNKNOWN($error)"
            }
            Log.d(TAG, "SpeechRecognizer error: $errorName")
            restartAfterDelay()
        }

        override fun onEvent(eventType: Int, params: Bundle?) {}

        private fun checkForWakeWord(bundle: Bundle?) {
            val matches = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION) ?: return
            for (match in matches) {
                val lower = match.lowercase().trim()
                if (WAKE_PHRASES.any { lower.contains(it) }) {
                    onWakeWordDetected()
                    return
                }
            }
        }
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Wake Word Detection",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Listening for 'Hey JARVIS' wake phrase"
            setShowBadge(false)
        }
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        mgr.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("JARVIS")
            .setContentText("Listening for wake word…")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }
}
