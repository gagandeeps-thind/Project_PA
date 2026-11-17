package osiris.fit.ui.arise

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import android.util.Base64
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import osiris.fit.platform.image.decodeSampled

private const val MAX_SIDE = 1024
private const val MAX_BYTES = 300_000
private const val START_QUALITY = 85
private const val MIN_QUALITY = 40
private const val QUALITY_STEP = 10
private const val TURN_90 = 90f
private const val TURN_180 = 180f
private const val TURN_270 = 270f

/**
 * The picked photo as a base64 JPEG the server accepts: upright, at most 1024 px on the long side and
 * 300 KB, lowering the quality until it fits. Null when the image cannot be read.
 *
 * The photo is decoded subsampled, never at the camera's full resolution, which would not fit in memory.
 */
suspend fun photoForUpload(context: Context, uri: Uri): String? = withContext(Dispatchers.IO) {
    // Also catches OutOfMemoryError: an unreadable photo is reported like any other, not as a crash.
    runCatching {
        val resolver = context.contentResolver
        val source = decodeSampled(MAX_SIDE) { resolver.openInputStream(uri) } ?: return@runCatching null
        val scale = (MAX_SIDE.toFloat() / maxOf(source.width, source.height)).coerceAtMost(1f)
        val upright = Matrix().apply {
            postScale(scale, scale)
            postRotate(rotation(context, uri))
        }
        val bitmap = Bitmap.createBitmap(source, 0, 0, source.width, source.height, upright, true)
        var quality = START_QUALITY
        var bytes: ByteArray
        do {
            bytes = ByteArrayOutputStream().also { bitmap.compress(Bitmap.CompressFormat.JPEG, quality, it) }.toByteArray()
            quality -= QUALITY_STEP
        } while (bytes.size > MAX_BYTES && quality >= MIN_QUALITY)
        bytes.takeIf { it.size <= MAX_BYTES }?.let { Base64.encodeToString(it, Base64.NO_WRAP) }
    }.getOrNull()
}

/**
 * Degrees to turn the pixels so the photo is upright: cameras store portrait photos sideways with an
 * EXIF orientation, which re-encoding would otherwise drop. 0 when there is none (PNG, screenshots).
 */
// shortcut: mirrored orientations (some front cameras) stay as stored, add them if players report flipped photos.
private fun rotation(context: Context, uri: Uri): Float = runCatching {
    context.contentResolver.openInputStream(uri)?.use { stream ->
        when (ExifInterface(stream).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
            ExifInterface.ORIENTATION_ROTATE_90 -> TURN_90
            ExifInterface.ORIENTATION_ROTATE_180 -> TURN_180
            ExifInterface.ORIENTATION_ROTATE_270 -> TURN_270
            else -> 0f
        }
    }
}.getOrNull() ?: 0f
