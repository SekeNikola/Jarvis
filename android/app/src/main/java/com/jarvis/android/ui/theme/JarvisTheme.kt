package com.jarvis.android.ui.theme

import android.app.Activity
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

// ── Colour palette ──────────────────────────────────────────────────
val JarvisBlue = Color(0xFF4FC3F7)
val JarvisCyan = Color(0xFF00E5FF)
val JarvisGold = Color(0xFFFFD54F)
val JarvisRed  = Color(0xFFEF5350)

val OnSurfaceText  = Color(0xFFE6EDF3)
val OnSurfaceDim   = Color(0xFF8B949E)

// ── Regular dark surface colours ────────────────────────────────────
val SurfaceDarkNormal    = Color(0xFF0D1117)
val SurfaceCardNormal    = Color(0xFF161B22)
val SurfaceVariantNormal = Color(0xFF21262D)

// ── AMOLED surface colours (pure blacks) ────────────────────────────
val SurfaceDarkAmoled    = Color(0xFF000000)
val SurfaceCardAmoled    = Color(0xFF0A0A0A)
val SurfaceVariantAmoled = Color(0xFF111111)

// ── Dynamic surface colours (resolved by theme) ────────────────────
data class JarvisSurfaceColors(
    val surfaceDark: Color,
    val surfaceCard: Color,
    val surfaceVariant: Color,
)

val LocalJarvisSurfaces = staticCompositionLocalOf {
    JarvisSurfaceColors(SurfaceDarkNormal, SurfaceCardNormal, SurfaceVariantNormal)
}

// Convenience accessors (use these everywhere instead of raw vals)
val SurfaceDark: Color @Composable get() = LocalJarvisSurfaces.current.surfaceDark
val SurfaceCard: Color @Composable get() = LocalJarvisSurfaces.current.surfaceCard
val SurfaceVariant: Color @Composable get() = LocalJarvisSurfaces.current.surfaceVariant

private fun jarvisDarkColors(amoled: Boolean) = darkColorScheme(
    primary        = JarvisBlue,
    onPrimary      = Color.Black,
    secondary      = JarvisCyan,
    onSecondary    = Color.Black,
    tertiary       = JarvisGold,
    error          = JarvisRed,
    background     = if (amoled) SurfaceDarkAmoled else SurfaceDarkNormal,
    surface        = if (amoled) SurfaceDarkAmoled else SurfaceDarkNormal,
    surfaceVariant = if (amoled) SurfaceCardAmoled else SurfaceCardNormal,
    onBackground   = OnSurfaceText,
    onSurface      = OnSurfaceText,
    onSurfaceVariant = OnSurfaceDim,
    outline        = if (amoled) SurfaceVariantAmoled else SurfaceVariantNormal,
)

// ── Typography ──────────────────────────────────────────────────────
val JarvisTypography = Typography()

// ── Theme ───────────────────────────────────────────────────────────
@Composable
fun JarvisTheme(
    amoled: Boolean = false,
    content: @Composable () -> Unit,
) {
    val colorScheme = jarvisDarkColors(amoled)
    val surfaces = if (amoled)
        JarvisSurfaceColors(SurfaceDarkAmoled, SurfaceCardAmoled, SurfaceVariantAmoled)
    else
        JarvisSurfaceColors(SurfaceDarkNormal, SurfaceCardNormal, SurfaceVariantNormal)

    // Make status bar match background
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.background.toArgb()
            window.navigationBarColor = colorScheme.background.toArgb()
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = false
                isAppearanceLightNavigationBars = false
            }
        }
    }

    CompositionLocalProvider(LocalJarvisSurfaces provides surfaces) {
        MaterialTheme(
            colorScheme = colorScheme,
            typography = JarvisTypography,
            content = content,
        )
    }
}
