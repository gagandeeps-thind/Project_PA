package com.osiris.player.ui.arise

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Base64
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import java.io.ByteArrayOutputStream
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val MAX_SIDE = 1024
private const val MAX_BYTES = 300_000
private const val START_QUALITY = 85
private const val MIN_QUALITY = 40
private const val QUALITY_STEP = 10

/** A picture from a plain URL (domain photos are public), or null while loading or if it fails. */
@Composable
fun rememberRemoteImage(url: String): ImageBitmap? {
    val image by produceState<ImageBitmap?>(null, url) {
        value = withContext(Dispatchers.IO) {
            runCatching { URL(url).openStream().use { BitmapFactory.decodeStream(it) }?.asImageBitmap() }.getOrNull()
        }
    }
    return image
}

/**
 * The picked photo as a base64 JPEG the server accepts: at most 1024 px on the long side and 300 KB,
 * lowering the quality until it fits. Null when the image cannot be read.
 */
suspend fun photoForUpload(context: Context, uri: Uri): String? = withContext(Dispatchers.IO) {
    val source = context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it) } ?: return@withContext null
    val scale = MAX_SIDE.toFloat() / maxOf(source.width, source.height)
    val bitmap = if (scale < 1f) {
        Bitmap.createScaledBitmap(source, (source.width * scale).toInt(), (source.height * scale).toInt(), true)
    } else {
        source
    }
    var quality = START_QUALITY
    var bytes: ByteArray
    do {
        bytes = ByteArrayOutputStream().also { bitmap.compress(Bitmap.CompressFormat.JPEG, quality, it) }.toByteArray()
        quality -= QUALITY_STEP
    } while (bytes.size > MAX_BYTES && quality >= MIN_QUALITY)
    bytes.takeIf { it.size <= MAX_BYTES }?.let { Base64.encodeToString(it, Base64.NO_WRAP) }
}
