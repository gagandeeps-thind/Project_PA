package osiris.fit.platform.image

import android.content.Context
import android.graphics.Bitmap
import android.util.LruCache
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Pictures from public URLs (post photos, domain photos) for every screen that shows one.
 *
 * - The download has connect and read timeouts, so a stalled server cannot hold an IO thread for good.
 * - Decoded bitmaps are kept in memory up to an eighth of the app's heap, counted in bytes.
 * - Downloaded files are kept in `cacheDir/images` up to [DISK_BYTES], oldest use first out; the system
 *   may clear that directory at any time.
 * - Pictures are decoded subsampled for the size they are shown at.
 */
object RemoteImages {
    /** Enough for a photo across the width of a phone; post photos are uploaded at 1024 px. */
    const val FULL_WIDTH_PX = 1024

    /** A grid tile or a card thumbnail. */
    const val THUMBNAIL_PX = 384

    private const val CONNECT_TIMEOUT_MS = 10_000
    private const val READ_TIMEOUT_MS = 15_000
    private const val MAX_DOWNLOAD_BYTES = 8L * 1024 * 1024
    private const val DISK_BYTES = 24L * 1024 * 1024
    private const val MEMORY_FRACTION = 8
    private const val DIR = "images"

    private val memory = object : LruCache<String, Bitmap>(
        (Runtime.getRuntime().maxMemory() / MEMORY_FRACTION).coerceAtMost(Int.MAX_VALUE.toLong()).toInt(),
    ) {
        override fun sizeOf(key: String, value: Bitmap): Int = value.byteCount
    }

    private fun key(url: String, maxSidePx: Int) = "$maxSidePx $url"

    /** The picture if it is already decoded at this size. */
    fun cached(url: String, maxSidePx: Int): Bitmap? = memory.get(key(url, maxSidePx))

    /** The picture from memory, disk or the network, in that order; null when it cannot be loaded. */
    suspend fun load(context: Context, url: String, maxSidePx: Int): Bitmap? = withContext(Dispatchers.IO) {
        cached(url, maxSidePx)
            // Also catches OutOfMemoryError: a picture that does not fit is shown as missing, not as a crash.
            ?: runCatching {
                val file = file(File(context.cacheDir, DIR), url)
                decodeSampled(maxSidePx) { file.inputStream() }?.also { memory.put(key(url, maxSidePx), it) }
            }.getOrNull()
    }

    /** The cached download of [url], fetching it first when it is not on disk. */
    private fun file(dir: File, url: String): File {
        val file = File(dir, hash(url))
        if (file.exists()) {
            // Marks it as recently used for the trim below.
            file.setLastModified(System.currentTimeMillis())
            return file
        }
        dir.mkdirs()
        val partial = File.createTempFile("download", null, dir)
        try {
            download(url, partial)
            if (!partial.renameTo(file)) throw IOException("Could not store $file")
        } finally {
            partial.delete()
        }
        trim(dir)
        return file
    }

    private fun download(url: String, into: File) {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = CONNECT_TIMEOUT_MS
        connection.readTimeout = READ_TIMEOUT_MS
        try {
            if (connection.responseCode != HttpURLConnection.HTTP_OK) throw IOException("HTTP ${connection.responseCode}")
            connection.inputStream.use { input -> into.outputStream().use { output -> copyCapped(input, output) } }
        } finally {
            connection.disconnect()
        }
    }

    /** Copies at most [MAX_DOWNLOAD_BYTES]; a larger body is not a photo this app made, so it is refused. */
    private fun copyCapped(input: InputStream, output: OutputStream) {
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        var total = 0L
        var read = input.read(buffer)
        while (read >= 0) {
            total += read
            if (total > MAX_DOWNLOAD_BYTES) throw IOException("Image over $MAX_DOWNLOAD_BYTES bytes")
            output.write(buffer, 0, read)
            read = input.read(buffer)
        }
    }

    /** Deletes the least recently used files until the directory is under [DISK_BYTES]. */
    private fun trim(dir: File) {
        val files = dir.listFiles().orEmpty().sortedBy { it.lastModified() }
        var total = files.sumOf { it.length() }
        for (old in files) {
            if (total <= DISK_BYTES) break
            total -= old.length()
            old.delete()
        }
    }

    private fun hash(url: String): String =
        MessageDigest.getInstance("SHA-256").digest(url.toByteArray()).joinToString("") { "%02x".format(it) }
}

/**
 * A picture from a public [url], or null while it loads or if it cannot be loaded. [maxSidePx] is about
 * the size it is shown at ([RemoteImages.FULL_WIDTH_PX] or [RemoteImages.THUMBNAIL_PX]).
 */
@Composable
fun rememberRemoteImage(url: String, maxSidePx: Int = RemoteImages.FULL_WIDTH_PX): ImageBitmap? {
    val context = LocalContext.current.applicationContext
    val image by produceState(RemoteImages.cached(url, maxSidePx)?.asImageBitmap(), url, maxSidePx) {
        // Reset first, so a slot reused for another URL never keeps showing the previous picture.
        value = RemoteImages.cached(url, maxSidePx)?.asImageBitmap()
        if (value == null) value = RemoteImages.load(context, url, maxSidePx)?.asImageBitmap()
    }
    return image
}
