package com.jarvis.android.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Base64
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.android.JarvisViewModel.ChatEntry
import com.jarvis.android.ui.theme.*

@Composable
fun TranscriptList(
    entries: List<ChatEntry>,
    modifier: Modifier = Modifier,
) {
    val listState = rememberLazyListState()

    // Auto-scroll to bottom on new messages
    LaunchedEffect(entries.size) {
        if (entries.isNotEmpty()) {
            listState.animateScrollToItem(entries.size - 1)
        }
    }

    LazyColumn(
        state = listState,
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(entries, key = { it.id }) { entry ->
            ChatBubble(entry)
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ChatBubble(entry: ChatEntry) {
    val context = LocalContext.current
    val isUser = entry.isUser
    val alignment = if (isUser) Alignment.CenterEnd else Alignment.CenterStart
    val bgColor = if (isUser) SurfaceVariant.copy(alpha = 0.55f) else SurfaceCard.copy(alpha = 0.55f)
    val labelColor = if (isUser) JarvisCyan else JarvisBlue
    var showMenu by remember { mutableStateOf(false) }

    Box(
        modifier = Modifier.fillMaxWidth(),
        contentAlignment = alignment,
    ) {
        Surface(
            shape = RoundedCornerShape(
                topStart = 16.dp, topEnd = 16.dp,
                bottomStart = if (isUser) 16.dp else 4.dp,
                bottomEnd = if (isUser) 4.dp else 16.dp,
            ),
            color = bgColor,
            modifier = Modifier
                .widthIn(max = 300.dp)
                .combinedClickable(
                    onClick = { },
                    onLongClick = {
                        hapticTick(context)
                        showMenu = true
                    },
                ),
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = if (isUser) "You" else "JARVIS",
                    style = MaterialTheme.typography.labelSmall,
                    color = labelColor,
                    fontWeight = FontWeight.Bold,
                    fontSize = 11.sp,
                )
                Spacer(Modifier.height(4.dp))

                // Image content (base64)
                entry.imageBase64?.let { b64 ->
                    val bitmap = remember(b64) {
                        try {
                            val bytes = Base64.decode(b64, Base64.DEFAULT)
                            BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                        } catch (_: Exception) { null }
                    }
                    bitmap?.let {
                        Image(
                            bitmap = it.asImageBitmap(),
                            contentDescription = "Image",
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp)),
                            contentScale = ContentScale.FillWidth,
                        )
                        Spacer(Modifier.height(4.dp))
                    }
                }

                // Text content
                if (entry.text.isNotBlank()) {
                    if (!isUser) {
                        Text(
                            text = parseSimpleMarkdown(entry.text),
                            style = MaterialTheme.typography.bodyMedium,
                            color = OnSurfaceText,
                        )
                    } else {
                        Text(
                            text = entry.text,
                            style = MaterialTheme.typography.bodyMedium,
                            color = OnSurfaceText,
                        )
                    }
                }
            }
        }

        // ── Long-press context menu ────────────────────────
        DropdownMenu(
            expanded = showMenu,
            onDismissRequest = { showMenu = false },
        ) {
            DropdownMenuItem(
                text = { Text("\uD83D\uDCCB  Copy") },
                onClick = {
                    copyToClipboard(context, entry.text)
                    showMenu = false
                },
            )
            DropdownMenuItem(
                text = { Text("\uD83D\uDCE4  Share") },
                onClick = {
                    shareText(context, entry.text)
                    showMenu = false
                },
            )
        }
    }
}


// ── Simple Markdown parser ─────────────────────────────────────
/**
 * Parses a subset of Markdown into AnnotatedString:
 *  - **bold**
 *  - `inline code`
 *  - ```code blocks```
 *  - [link text](url)
 */
@Composable
fun parseSimpleMarkdown(text: String) = buildAnnotatedString {
    var i = 0
    while (i < text.length) {
        when {
            // **bold**
            text.startsWith("**", i) -> {
                val end = text.indexOf("**", i + 2)
                if (end != -1) {
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) {
                        append(text.substring(i + 2, end))
                    }
                    i = end + 2
                } else {
                    append(text[i]); i++
                }
            }
            // ```code block```
            text.startsWith("```", i) -> {
                val end = text.indexOf("```", i + 3)
                if (end != -1) {
                    val codeStart = text.indexOf('\n', i + 3).let { nl ->
                        if (nl in (i + 3) until end) nl + 1 else i + 3
                    }
                    withStyle(SpanStyle(
                        fontFamily = FontFamily.Monospace,
                        background = Color(0xFF21262D),
                        color = JarvisCyan,
                    )) {
                        append(text.substring(codeStart, end).trimEnd())
                    }
                    i = end + 3
                } else {
                    append(text[i]); i++
                }
            }
            // `inline code`
            text[i] == '`' -> {
                val end = text.indexOf('`', i + 1)
                if (end != -1) {
                    withStyle(SpanStyle(
                        fontFamily = FontFamily.Monospace,
                        background = Color(0xFF21262D),
                        color = JarvisCyan,
                    )) {
                        append(text.substring(i + 1, end))
                    }
                    i = end + 1
                } else {
                    append(text[i]); i++
                }
            }
            // [text](url)
            text[i] == '[' -> {
                val closeBracket = text.indexOf(']', i + 1)
                val openParen = if (closeBracket != -1 && closeBracket + 1 < text.length)
                    closeBracket + 1 else -1
                val isLink = openParen != -1 && text.getOrNull(openParen) == '('
                val closeParen = if (isLink) text.indexOf(')', openParen) else -1

                if (closeBracket != -1 && closeParen != -1) {
                    val linkText = text.substring(i + 1, closeBracket)
                    withStyle(SpanStyle(
                        color = JarvisBlue,
                        textDecoration = TextDecoration.Underline,
                    )) {
                        append(linkText)
                    }
                    i = closeParen + 1
                } else {
                    append(text[i]); i++
                }
            }
            else -> {
                append(text[i]); i++
            }
        }
    }
}


// ── Clipboard / Share helpers ──────────────────────────────────
private fun copyToClipboard(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    clipboard.setPrimaryClip(ClipData.newPlainText("JARVIS", text))
}

private fun shareText(context: Context, text: String) {
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, text)
    }
    context.startActivity(Intent.createChooser(intent, "Share via"))
}

/** Quick haptic tick for long-press feedback */
fun hapticTick(context: Context) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
        vm.defaultVibrator.vibrate(VibrationEffect.createOneShot(30, VibrationEffect.DEFAULT_AMPLITUDE))
    } else {
        @Suppress("DEPRECATION")
        val v = context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        v.vibrate(VibrationEffect.createOneShot(30, VibrationEffect.DEFAULT_AMPLITUDE))
    }
}
