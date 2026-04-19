package com.jarvis.android.audio

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat
import android.content.Context
import kotlinx.coroutines.*

/**
 * Records 16 kHz mono 16-bit PCM audio and streams raw chunks via callback.
 * Matches backend expectations: 16000 Hz, mono, int16 little-endian.
 */
class AudioRecorder(private val context: Context) {

    companion object {
        private const val TAG = "AudioRecorder"
        const val SAMPLE_RATE = 16000
        private const val CHANNEL = AudioFormat.CHANNEL_IN_MONO
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
        // Send chunks every ~100ms = 1600 samples * 2 bytes = 3200 bytes
        private const val CHUNK_SIZE = 3200
    }

    private var audioRecord: AudioRecord? = null
    private var recordingJob: Job? = null
    private var isRecording = false

    /**
     * Start recording and invoke [onChunk] with each PCM byte array.
     * Runs on a coroutine; returns immediately.
     */
    fun startRecording(scope: CoroutineScope, onChunk: (ByteArray) -> Unit) {
        if (isRecording) {
            Log.w(TAG, "Already recording")
            return
        }

        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.e(TAG, "RECORD_AUDIO permission not granted")
            return
        }

        val bufferSize = maxOf(
            AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING),
            CHUNK_SIZE * 4
        )

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE,
            CHANNEL,
            ENCODING,
            bufferSize
        )

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord failed to initialise")
            audioRecord?.release()
            audioRecord = null
            return
        }

        isRecording = true
        audioRecord?.startRecording()
        Log.i(TAG, "Recording started – ${SAMPLE_RATE}Hz mono PCM16")

        recordingJob = scope.launch(Dispatchers.IO) {
            val buffer = ByteArray(CHUNK_SIZE)
            while (isActive && isRecording) {
                val read = audioRecord?.read(buffer, 0, CHUNK_SIZE) ?: -1
                if (read > 0) {
                    onChunk(buffer.copyOf(read))
                } else if (read < 0) {
                    Log.e(TAG, "AudioRecord.read error: $read")
                    break
                }
            }
        }
    }

    fun stopRecording() {
        isRecording = false
        recordingJob?.cancel()
        recordingJob = null
        try {
            audioRecord?.stop()
        } catch (e: Exception) {
            Log.w(TAG, "stop error: $e")
        }
        Log.i(TAG, "Recording stopped")
    }

    fun release() {
        stopRecording()
        audioRecord?.release()
        audioRecord = null
    }
}
