package com.jarvis.android.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import com.jarvis.android.JarvisViewModel.AppState
import com.jarvis.android.ui.theme.*
import kotlin.math.*
import kotlin.random.Random

/* ─────────────────────────────────────────────────────────────
 * ParticleOrb – particles.js-style connected-dot network
 * inside a circular boundary.
 *
 * 2D particles drift freely, bouncing off the circle edge.
 * All nearby pairs are connected with fading lines.
 * Boundary, speed, and colours react to JARVIS app state.
 * ───────────────────────────────────────────────────────────── */

private const val PARTICLE_COUNT = 90

// Per-state configuration
private data class OrbConfig(
    val hue: Float,        // 0..360
    val sat: Float,        // 0..1
    val light: Float,      // 0..1
    val boundaryR: Float,  // fraction of half-width
    val speed: Float,      // movement multiplier
    val lineDistFrac: Float, // connection distance as fraction of half-width
    val lineAlpha: Float,
    val dotAlpha: Float,
    val pulseAmp: Float,
)

private val CONFIGS = mapOf(
    AppState.IDLE         to OrbConfig(200f, 0.60f, 0.55f, 0.72f, 0.35f, 0.30f, 0.18f, 0.55f, 0.02f),
    AppState.CONNECTING   to OrbConfig(200f, 0.40f, 0.45f, 0.60f, 0.20f, 0.28f, 0.10f, 0.40f, 0.02f),
    AppState.LISTENING    to OrbConfig(190f, 0.90f, 0.70f, 0.88f, 1.20f, 0.34f, 0.35f, 0.75f, 0.12f),
    AppState.TRANSCRIBING to OrbConfig(190f, 0.80f, 0.60f, 0.80f, 0.80f, 0.32f, 0.25f, 0.65f, 0.08f),
    AppState.THINKING     to OrbConfig(35f,  0.85f, 0.60f, 0.76f, 1.60f, 0.30f, 0.28f, 0.65f, 0.04f),
    AppState.SPEAKING     to OrbConfig(160f, 0.80f, 0.60f, 0.92f, 0.60f, 0.36f, 0.40f, 0.80f, 0.18f),
)

private data class Particle(
    var nx: Float,   // normalised position (−1…1)
    var ny: Float,
    var vx: Float,   // velocity direction + magnitude
    var vy: Float,
    val size: Float,
    val brightness: Float,
)

private fun createParticles(): List<Particle> = List(PARTICLE_COUNT) {
    val angle = Random.nextFloat() * 2f * PI.toFloat()
    val r = sqrt(Random.nextFloat()) // uniform in circle
    val spd = 0.3f + Random.nextFloat() * 0.7f
    val dir = Random.nextFloat() * 2f * PI.toFloat()
    Particle(
        nx = r * cos(angle),
        ny = r * sin(angle),
        vx = cos(dir) * spd,
        vy = sin(dir) * spd,
        size = 1.5f + Random.nextFloat() * 2.5f,
        brightness = 0.4f + Random.nextFloat() * 0.6f,
    )
}

/** HSL → Compose Color */
private fun hslColor(h: Float, s: Float, l: Float, alpha: Float = 1f): Color {
    val hNorm = ((h % 360f) + 360f) % 360f
    val c = (1f - abs(2f * l - 1f)) * s
    val x = c * (1f - abs((hNorm / 60f) % 2f - 1f))
    val m = l - c / 2f
    val (r1, g1, b1) = when {
        hNorm < 60f  -> Triple(c, x, 0f)
        hNorm < 120f -> Triple(x, c, 0f)
        hNorm < 180f -> Triple(0f, c, x)
        hNorm < 240f -> Triple(0f, x, c)
        hNorm < 300f -> Triple(x, 0f, c)
        else         -> Triple(c, 0f, x)
    }
    return Color(
        red   = (r1 + m).coerceIn(0f, 1f),
        green = (g1 + m).coerceIn(0f, 1f),
        blue  = (b1 + m).coerceIn(0f, 1f),
        alpha = alpha.coerceIn(0f, 1f),
    )
}

@Composable
fun VoiceOrb(
    state: AppState,
    modifier: Modifier = Modifier,
) {
    val particles = remember { createParticles() }

    // Continuous time driver
    val infiniteTransition = rememberInfiniteTransition(label = "orbTime")
    val timeSeconds by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 600f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 600_000, easing = LinearEasing),
        ),
        label = "time",
    )

    val target = CONFIGS[state] ?: CONFIGS[AppState.IDLE]!!

    // Smoothly animated config values
    val hue        by animateFloatAsState(target.hue, tween(400), label = "h")
    val sat        by animateFloatAsState(target.sat, tween(400), label = "s")
    val light      by animateFloatAsState(target.light, tween(400), label = "l")
    val boundaryR  by animateFloatAsState(target.boundaryR, tween(500), label = "bR")
    val speed      by animateFloatAsState(target.speed, tween(400), label = "spd")
    val lineDistF  by animateFloatAsState(target.lineDistFrac, tween(400), label = "ld")
    val lineAlpha  by animateFloatAsState(target.lineAlpha, tween(400), label = "la")
    val dotAlpha   by animateFloatAsState(target.dotAlpha, tween(400), label = "da")
    val pulseAmp   by animateFloatAsState(target.pulseAmp, tween(400), label = "pa")

    // Thinking spinner
    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(2000, easing = LinearEasing),
        ),
        label = "rotation",
    )

    Box(
        modifier = modifier.size(320.dp),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val w = size.width
            val h = size.height
            val cx = w / 2f
            val cy = h / 2f
            val halfW = w / 2f

            val t = timeSeconds
            val pulse = 1f + sin(t * 2.5f) * pulseAmp
            val bR = halfW * boundaryR * pulse  // actual boundary radius in px
            val lineDist = halfW * lineDistF

            // ── Subtle background glow ──
            drawCircle(
                brush = Brush.radialGradient(
                    colorStops = arrayOf(
                        0.0f to hslColor(hue, sat, light, 0.06f),
                        0.7f to hslColor(hue, sat, light, 0.015f),
                        1.0f to Color.Transparent,
                    ),
                    center = Offset(cx, cy),
                    radius = bR * 1.1f,
                ),
                radius = bR * 1.1f,
                center = Offset(cx, cy),
            )

            // ── Update particles (2D free movement, bounce off circle) ──
            val dt = 0.016f
            for (p in particles) {
                p.nx += p.vx * speed * 0.003f
                p.ny += p.vy * speed * 0.003f

                val dist = sqrt(p.nx * p.nx + p.ny * p.ny)
                if (dist > 1f) {
                    val nx = p.nx / dist
                    val ny = p.ny / dist
                    val dot = p.vx * nx + p.vy * ny
                    p.vx -= 2f * dot * nx
                    p.vy -= 2f * dot * ny
                    p.nx = nx * 0.99f
                    p.ny = ny * 0.99f
                }
            }

            // ── Compute screen positions ──
            data class ScreenDot(val x: Float, val y: Float, val sz: Float, val br: Float)
            val dots = particles.map { p ->
                ScreenDot(cx + p.nx * bR, cy + p.ny * bR, p.size, p.brightness)
            }

            // ── Connecting lines (all pairs) ──
            val ldSq = lineDist * lineDist
            for (i in dots.indices) {
                val a = dots[i]
                for (j in (i + 1) until dots.size) {
                    val b = dots[j]
                    val dx = a.x - b.x
                    val dy = a.y - b.y
                    val dSq = dx * dx + dy * dy
                    if (dSq < ldSq) {
                        val fade = 1f - sqrt(dSq) / lineDist
                        val alpha = fade * lineAlpha
                        drawLine(
                            color = hslColor(hue, sat - 0.10f, light + 0.20f, alpha),
                            start = Offset(a.x, a.y),
                            end = Offset(b.x, b.y),
                            strokeWidth = 1f,
                        )
                    }
                }
            }

            // ── Draw particles ──
            for (d in dots) {
                val alpha = d.br * dotAlpha
                drawCircle(
                    color = hslColor(hue + (d.br - 0.5f) * 20f, sat, light + 0.15f, alpha),
                    radius = d.sz,
                    center = Offset(d.x, d.y),
                )
                // Bloom
                if (d.sz > 2f) {
                    drawCircle(
                        color = hslColor(hue, sat, light, alpha * 0.08f),
                        radius = d.sz * 4f,
                        center = Offset(d.x, d.y),
                    )
                }
            }

            // ── Boundary ring ──
            drawCircle(
                color = hslColor(hue, sat, light, 0.06f),
                radius = bR,
                center = Offset(cx, cy),
                style = Stroke(width = 1f),
            )

            // ── Thinking spinner ──
            if (state == AppState.THINKING || state == AppState.TRANSCRIBING) {
                val arcR = bR * 0.45f
                drawArc(
                    color = JarvisGold.copy(alpha = 0.7f),
                    startAngle = rotation,
                    sweepAngle = 90f,
                    useCenter = false,
                    style = Stroke(width = 3f),
                    topLeft = Offset(cx - arcR, cy - arcR),
                    size = androidx.compose.ui.geometry.Size(arcR * 2f, arcR * 2f),
                )
            }
        }
    }
}
