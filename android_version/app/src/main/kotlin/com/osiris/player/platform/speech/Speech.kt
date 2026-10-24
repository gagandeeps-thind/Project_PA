package com.osiris.player.platform.speech

import android.speech.tts.TextToSpeech
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext

/**
 * Speaks short announcements in the device voice and language, queued so none cut another off.
 * Text sent before the engine is ready is dropped; the first cue is a kilometre in, long after.
 */
@Composable
fun rememberSpeech(): (String) -> Unit {
    val context = LocalContext.current
    val tts = remember { TextToSpeech(context.applicationContext) {} }
    DisposableEffect(tts) { onDispose { tts.shutdown() } }
    return remember(tts) { { text -> tts.speak(text, TextToSpeech.QUEUE_ADD, null, "osiris-cue") } }
}
