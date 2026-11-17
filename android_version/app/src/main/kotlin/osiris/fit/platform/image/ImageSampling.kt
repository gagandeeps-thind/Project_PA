package osiris.fit.platform.image

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.InputStream

/**
 * The largest power-of-two subsampling that keeps the long side at [maxSide] or more, so a decoded
 * picture is at most twice the size it is shown or uploaded at instead of the camera's full resolution.
 */
internal fun sampleSize(width: Int, height: Int, maxSide: Int): Int {
    var sample = 1
    while (maxOf(width, height) / (sample * 2) >= maxSide) sample *= 2
    return sample
}

/**
 * Decodes a picture subsampled for [maxSide]: the bounds are read first, so a 50-megapixel photo never
 * becomes a 200 MB bitmap. [open] is called twice. Null when the source cannot be opened or is not an image.
 */
internal fun decodeSampled(maxSide: Int, open: () -> InputStream?): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    open()?.use { BitmapFactory.decodeStream(it, null, bounds) }
    // Still zero when the source did not open or is not an image.
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
    val options = BitmapFactory.Options().apply { inSampleSize = sampleSize(bounds.outWidth, bounds.outHeight, maxSide) }
    return open()?.use { BitmapFactory.decodeStream(it, null, options) }
}
