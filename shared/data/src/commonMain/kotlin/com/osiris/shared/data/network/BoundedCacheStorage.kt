package com.osiris.shared.data.network

import io.ktor.client.plugins.cache.storage.CacheStorage
import io.ktor.client.plugins.cache.storage.CachedResponseData
import io.ktor.http.Url
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * An in-memory HTTP cache that stays under [maxBytes] of response bodies. Ktor's default storage keeps
 * every URL ever fetched (each page, position and filter is its own URL) for the life of the process.
 *
 * When full, the URL stored or revalidated longest ago goes first. [clear] empties it at every account
 * change, so one player's responses never stay in memory for the next.
 */
internal class BoundedCacheStorage(private val maxBytes: Long = DEFAULT_MAX_BYTES) : CacheStorage {
    private val lock = Mutex()

    // Insertion order is eviction order: storing a URL again moves it to the end.
    private val entries = LinkedHashMap<Url, Set<CachedResponseData>>()

    override suspend fun store(url: Url, data: CachedResponseData): Unit = lock.withLock {
        val others = entries.remove(url).orEmpty().filterNot { it.varyKeys == data.varyKeys }
        entries[url] = others.toSet() + data
        while (entries.isNotEmpty() && bytes() > maxBytes) entries.remove(entries.keys.first())
    }

    override suspend fun find(url: Url, varyKeys: Map<String, String>): CachedResponseData? = lock.withLock {
        entries[url]?.find { cached -> varyKeys.all { (key, value) -> cached.varyKeys[key] == value } }
    }

    override suspend fun findAll(url: Url): Set<CachedResponseData> = lock.withLock { entries[url].orEmpty() }

    override suspend fun remove(url: Url, varyKeys: Map<String, String>): Unit = lock.withLock {
        val kept = entries[url].orEmpty().filterNot { it.varyKeys == varyKeys }.toSet()
        if (kept.isEmpty()) entries.remove(url) else entries[url] = kept
    }

    override suspend fun removeAll(url: Url): Unit = lock.withLock { entries.remove(url) }

    suspend fun clear(): Unit = lock.withLock { entries.clear() }

    private fun bytes(): Long = entries.values.sumOf { set -> set.sumOf { it.body.size.toLong() } }

    companion object {
        /** About a hundred typical JSON screens; small next to the app's heap. */
        const val DEFAULT_MAX_BYTES = 2L * 1024 * 1024
    }
}
