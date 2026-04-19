package com.jarvis.android.ui

import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.android.JarvisViewModel
import com.jarvis.android.JarvisViewModel.AppState
import com.jarvis.android.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JarvisScreen(viewModel: JarvisViewModel) {
    val state by viewModel.appState.collectAsState()
    val chatHistory by viewModel.chatHistory.collectAsState()
    val statusText by viewModel.statusText.collectAsState()
    val isConnected by viewModel.isConnected.collectAsState()
    val error by viewModel.error.collectAsState()
    var showSettings by remember { mutableStateOf(false) }
    var textInput by remember { mutableStateOf("") }
    val focusManager = LocalFocusManager.current
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current

    // Show errors as snackbar
    LaunchedEffect(error) {
        error?.let {
            snackbarHostState.showSnackbar(it, duration = SnackbarDuration.Short)
            viewModel.dismissError()
        }
    }

    Scaffold(
        snackbarHost = {
            SnackbarHost(snackbarHostState) { data ->
                Snackbar(
                    snackbarData = data,
                    containerColor = SurfaceCard,
                    contentColor = JarvisRed,
                )
            }
        },
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(if (isConnected) JarvisCyan else JarvisRed)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "J.A.R.V.I.S.",
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 2.sp,
                            color = JarvisBlue,
                        )
                    }
                },
                actions = {
                    IconButton(onClick = {
                        viewModel.clearChat()
                    }) {
                        Icon(Icons.Default.Delete, "Clear chat", tint = OnSurfaceDim)
                    }
                    IconButton(onClick = { showSettings = !showSettings }) {
                        Icon(Icons.Default.Settings, "Settings", tint = OnSurfaceDim)
                    }
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = SurfaceDark,
                ),
            )
        },
        containerColor = SurfaceDark,
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .pointerInput(Unit) {
                    detectTapGestures {
                        focusManager.clearFocus()
                        hapticTick(context)
                        if (!isConnected) {
                            showSettings = true
                            viewModel.connect()
                        } else {
                            when (state) {
                                AppState.LISTENING, AppState.TRANSCRIBING -> viewModel.stopListening()
                                else -> viewModel.startListening() // Barge-in from any state
                            }
                        }
                    }
                },
        ) {
            // ── Particle orb behind everything ──────────────────────
            VoiceOrb(
                state = state,
                modifier = Modifier.align(Alignment.Center),
            )

            // ── Foreground content on top ───────────────────────────
            Column(
                modifier = Modifier.fillMaxSize(),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                // ── Settings panel ──────────────────────────────────
                AnimatedVisibility(visible = showSettings) {
                    SettingsPanel(viewModel) { showSettings = false }
                }

                // ── Transcript ──────────────────────────────────────
                TranscriptList(
                    entries = chatHistory,
                    modifier = Modifier.weight(1f),
                )

                // ── Quick action chips ──────────────────────────────
                QuickActionChips(
                    onChipClick = { command ->
                        if (isConnected) {
                            viewModel.sendTextInput(command)
                        }
                    },
                )

                // ── Status label ────────────────────────────────────
                Text(
                    text = statusText,
                    style = MaterialTheme.typography.bodySmall,
                    color = OnSurfaceDim,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.padding(vertical = 4.dp),
                )

                // ── Spacer where orb used to be ─────────────────────
                Spacer(modifier = Modifier.height(40.dp))

                // ── Text input row ──────────────────────────────────
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OutlinedTextField(
                        value = textInput,
                        onValueChange = { textInput = it },
                        placeholder = { Text("Type a command…", color = OnSurfaceDim) },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(24.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = JarvisBlue,
                            unfocusedBorderColor = SurfaceVariant,
                            focusedTextColor = OnSurfaceText,
                            unfocusedTextColor = OnSurfaceText,
                            cursorColor = JarvisCyan,
                        ),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = {
                            if (textInput.isNotBlank()) {
                                viewModel.sendTextInput(textInput.trim())
                                textInput = ""
                                focusManager.clearFocus()
                            }
                        }),
                        singleLine = true,
                    )
                    Spacer(Modifier.width(8.dp))
                    FilledIconButton(
                        onClick = {
                            if (textInput.isNotBlank()) {
                                viewModel.sendTextInput(textInput.trim())
                                textInput = ""
                                focusManager.clearFocus()
                            }
                        },
                        colors = IconButtonDefaults.filledIconButtonColors(
                            containerColor = JarvisBlue,
                        ),
                    ) {
                        Icon(Icons.Default.Send, "Send")
                    }
                }
            }
        }
    }
}

// ── Quick Action Chips ──────────────────────────────────────────────
@Composable
private fun QuickActionChips(onChipClick: (String) -> Unit) {
    val chips = listOf(
        "☀️ Weather" to "What's the weather like?",
        "📸 Screenshot" to "Take a screenshot of my computer screen",
        "📋 Briefing" to "Give me my daily briefing",
        "⏰ Remind" to "Set a reminder",
        "🔍 Search" to "Search the web for",
    )

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        chips.forEach { (label, command) ->
            SuggestionChip(
                onClick = { onChipClick(command) },
                label = { Text(label, fontSize = 12.sp) },
                colors = SuggestionChipDefaults.suggestionChipColors(
                    containerColor = SurfaceCard,
                    labelColor = OnSurfaceText,
                ),
                border = SuggestionChipDefaults.suggestionChipBorder(
                    borderColor = SurfaceVariant,
                ),
            )
        }
    }
}

// ── Settings Panel ──────────────────────────────────────────────────
@Composable
private fun SettingsPanel(viewModel: JarvisViewModel, onDismiss: () -> Unit) {
    val serverIp by viewModel.serverIp.collectAsState()
    val serverPort by viewModel.serverPort.collectAsState()
    val amoledEnabled by viewModel.amoledEnabled.collectAsState()
    val wakeWordEnabled by viewModel.wakeWordEnabled.collectAsState()
    var ip by remember { mutableStateOf(serverIp) }
    var port by remember { mutableStateOf(serverPort.toString()) }

    Surface(
        shape = RoundedCornerShape(bottomStart = 16.dp, bottomEnd = 16.dp),
        color = SurfaceCard,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Server Settings", style = MaterialTheme.typography.titleSmall, color = JarvisBlue)
            Spacer(Modifier.height(12.dp))

            OutlinedTextField(
                value = ip,
                onValueChange = { ip = it },
                label = { Text("Server IP") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = JarvisBlue,
                    unfocusedBorderColor = SurfaceVariant,
                    focusedTextColor = OnSurfaceText,
                    unfocusedTextColor = OnSurfaceText,
                    focusedLabelColor = JarvisBlue,
                    unfocusedLabelColor = OnSurfaceDim,
                ),
            )
            Spacer(Modifier.height(8.dp))

            OutlinedTextField(
                value = port,
                onValueChange = { port = it },
                label = { Text("Port") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = JarvisBlue,
                    unfocusedBorderColor = SurfaceVariant,
                    focusedTextColor = OnSurfaceText,
                    unfocusedTextColor = OnSurfaceText,
                    focusedLabelColor = JarvisBlue,
                    unfocusedLabelColor = OnSurfaceDim,
                ),
            )

            Spacer(Modifier.height(16.dp))
            Divider(color = SurfaceVariant, thickness = 0.5.dp)
            Spacer(Modifier.height(12.dp))

            // AMOLED toggle
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text("AMOLED Black", style = MaterialTheme.typography.bodyMedium, color = OnSurfaceText)
                    Text("Pure black for OLED screens", style = MaterialTheme.typography.bodySmall, color = OnSurfaceDim)
                }
                Switch(
                    checked = amoledEnabled,
                    onCheckedChange = { viewModel.setAmoled(it) },
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = JarvisBlue,
                        checkedTrackColor = JarvisBlue.copy(alpha = 0.3f),
                    ),
                )
            }

            Spacer(Modifier.height(12.dp))

            // Wake word toggle
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text("\"Hey JARVIS\"", style = MaterialTheme.typography.bodyMedium, color = OnSurfaceText)
                    Text("Voice activation wake word", style = MaterialTheme.typography.bodySmall, color = OnSurfaceDim)
                }
                Switch(
                    checked = wakeWordEnabled,
                    onCheckedChange = { viewModel.setWakeWordEnabled(it) },
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = JarvisCyan,
                        checkedTrackColor = JarvisCyan.copy(alpha = 0.3f),
                    ),
                )
            }

            Spacer(Modifier.height(12.dp))

            Row(horizontalArrangement = Arrangement.End, modifier = Modifier.fillMaxWidth()) {
                TextButton(onClick = onDismiss) {
                    Text("Cancel", color = OnSurfaceDim)
                }
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = {
                        viewModel.updateServer(ip, port.toIntOrNull() ?: 8000)
                        onDismiss()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = JarvisBlue),
                ) {
                    Text("Connect")
                }
            }
        }
    }
}
