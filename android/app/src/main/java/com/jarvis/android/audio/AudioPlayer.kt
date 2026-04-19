package com.jarvis.android.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.util.Log
import kotlinx.coroutines.*
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Plays MP3 audio chunks received from the backend.
 * Decodes MP3 → PCM with MediaCodec, then streams to AudioTrack.
 */
class AudioPlayer {

    companion object {
        private const val TAG = "AudioPlayer"
        private const val SAMPLE_RATE = 24000 // TTS output is typically 24kHz
    }

    private val chunkQueue = ConcurrentLinkedQueue<ByteArray>()
    private val isPlaying = AtomicBoolean(false)
    private var playbackJob: Job? = null

    /**
     * Enqueue an MP3 chunk (complete or partial) for playback.
     */
    fun playMp3Chunk(data: ByteArray) {
        chunkQueue.add(data)
        if (isPlaying.compareAndSet(false, true)) {
            startPlayback()
        }
    }

    /**
     * Stop all playback and clear the queue.
     */
    fun stop() {
        isPlaying.set(false)
        playbackJob?.cancel()
        playbackJob = null
        chunkQueue.clear()
    }

    fun release() {
        stop()
    }

    private fun startPlayback() {
        playbackJob = CoroutineScope(Dispatchers.IO).launch {
            try {
                while (isActive && (chunkQueue.isNotEmpty() || isPlaying.get())) {
                    val mp3Data = chunkQueue.poll()
                    if (mp3Data == null) {
                        delay(50)
                        // If queue is still empty after a bit, we're done
                        if (chunkQueue.isEmpty()) {
                            delay(200)
                            if (chunkQueue.isEmpty()) break
                        }
                        continue
                    }
                    playMp3Bytes(mp3Data)
                }
            } catch (e: CancellationException) {
                // normal
            } catch (e: Exception) {
                Log.e(TAG, "Playback error: $e")
            } finally {
                isPlaying.set(false)
            }
        }
    }

    /**
     * Decode MP3 bytes → PCM and play via AudioTrack.
     * Uses a temp file + MediaExtractor/MediaCodec pipeline.
     */
    private fun playMp3Bytes(mp3Data: ByteArray) {
        var tempFile: File? = null
        var extractor: MediaExtractor? = null
        var codec: MediaCodec? = null
        var audioTrack: AudioTrack? = null

        try {
            // Write MP3 to a temp file for MediaExtractor
            tempFile = File.createTempFile("jarvis_tts", ".mp3")
            FileOutputStream(tempFile).use { it.write(mp3Data) }

            // Set up extractor
            extractor = MediaExtractor()
            extractor.setDataSource(tempFile.absolutePath)

            if (extractor.trackCount == 0) {
                Log.w(TAG, "No tracks found in MP3 data")
                return
            }

            extractor.selectTrack(0)
            val format = extractor.getTrackFormat(0)
            val mime = format.getString(MediaFormat.KEY_MIME) ?: "audio/mpeg"
            val sampleRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
            val channelCount = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)

            // Set up codec
            codec = MediaCodec.createDecoderByType(mime)
            codec.configure(format, null, null, 0)
            codec.start()

            // Set up AudioTrack
            val channelConfig = if (channelCount == 1)
                AudioFormat.CHANNEL_OUT_MONO else AudioFormat.CHANNEL_OUT_STEREO

            val minBuf = AudioTrack.getMinBufferSize(
                sampleRate, channelConfig, AudioFormat.ENCODING_PCM_16BIT
            )

            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setSampleRate(sampleRate)
                        .setChannelMask(channelConfig)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .build()
                )
                .setBufferSizeInBytes(minBuf * 2)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            audioTrack.play()

            // Decode loop
            val info = MediaCodec.BufferInfo()
            var inputDone = false

            while (!inputDone || true) {
                // Feed input
                if (!inputDone) {
                    val inputIndex = codec.dequeueInputBuffer(10_000)
                    if (inputIndex >= 0) {
                        val inputBuffer = codec.getInputBuffer(inputIndex)!!
                        val sampleSize = extractor.readSampleData(inputBuffer, 0)
                        if (sampleSize < 0) {
                            codec.queueInputBuffer(
                                inputIndex, 0, 0, 0,
                                MediaCodec.BUFFER_FLAG_END_OF_STREAM
                            )
                            inputDone = true
                        } else {
                            codec.queueInputBuffer(
                                inputIndex, 0, sampleSize,
                                extractor.sampleTime, 0
                            )
                            extractor.advance()
                        }
                    }
                }

                // Drain output
                val outputIndex = codec.dequeueOutputBuffer(info, 10_000)
                if (outputIndex >= 0) {
                    val outBuffer = codec.getOutputBuffer(outputIndex)!!
                    val pcmData = ByteArray(info.size)
                    outBuffer.get(pcmData)
                    outBuffer.clear()

                    audioTrack.write(pcmData, 0, pcmData.size)
                    codec.releaseOutputBuffer(outputIndex, false)

                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) {
                        break
                    }
                } else if (outputIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    // ignore
                } else if (outputIndex == MediaCodec.INFO_TRY_AGAIN_LATER) {
                    if (inputDone) break
                }
            }

            // Drain remaining audio
            audioTrack.stop()

        } catch (e: Exception) {
            Log.e(TAG, "Decode/play error: $e")
        } finally {
            try { codec?.stop() } catch (_: Exception) {}
            try { codec?.release() } catch (_: Exception) {}
            try { extractor?.release() } catch (_: Exception) {}
            try { audioTrack?.release() } catch (_: Exception) {}
            tempFile?.delete()
        }
    }
}
