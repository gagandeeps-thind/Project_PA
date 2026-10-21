package com.osiris.player.ui.common

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.background
import com.osiris.player.ui.theme.OsirisColors
import kotlin.time.Clock
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Instant
import kotlinx.coroutines.delay

/** An empty list: an icon, a line saying so, and what to do about it. */
@Composable
fun EmptyState(
    icon: ImageVector,
    title: String,
    body: String? = null,
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null,
) {
    Column(Modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(icon, null, Modifier.size(56.dp), tint = Color.White.copy(alpha = 0.38f))
        Spacer(Modifier.height(12.dp))
        Text(title, textAlign = TextAlign.Center)
        if (body != null) {
            Spacer(Modifier.height(8.dp))
            Text(body, textAlign = TextAlign.Center, color = OsirisColors.Faint)
        }
        if (actionLabel != null && onAction != null) {
            Spacer(Modifier.height(16.dp))
            Button(onClick = onAction) { Text(actionLabel) }
        }
    }
}

/** A centred message in place of content, such as a refused permission. */
@Composable
fun Notice(text: String, modifier: Modifier = Modifier, color: Color = OsirisColors.Error) {
    Box(modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Text(text, color = color, textAlign = TextAlign.Center)
    }
}

/** A small rounded label. */
@Composable
fun Chip(label: String, color: Color) {
    Text(
        label,
        color = color,
        fontSize = 11.sp,
        modifier = Modifier
            .background(color.copy(alpha = 0.15f), RoundedCornerShape(8.dp))
            .padding(horizontal = 8.dp, vertical = 2.dp),
    )
}

/** A label and value on one line, labels aligned in a column. */
@Composable
fun TermRow(label: String, value: String) {
    Row(Modifier.padding(vertical = 3.dp)) {
        Text(label, color = OsirisColors.Faint, modifier = Modifier.width(130.dp))
        Text(value, modifier = Modifier.weight(1f))
    }
}

@Composable
fun Gap(height: Int = 12) = Spacer(Modifier.height(height.dp))

/** The current time, refreshed each minute, for "closes in" labels. */
@Composable
fun rememberNow(): Instant {
    var now by remember { mutableStateOf(Clock.System.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(1.minutes)
            now = Clock.System.now()
        }
    }
    return now
}

val ListSpacing = Arrangement.spacedBy(8.dp)

private val minuteFormat = java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

/** `2026-10-19 18:30` in the phone's time zone. */
fun Instant.localMinute(): String =
    minuteFormat.format(java.time.Instant.ofEpochMilli(toEpochMilliseconds()).atZone(java.time.ZoneId.systemDefault()))
