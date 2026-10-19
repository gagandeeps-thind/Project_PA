package com.osiris.shared.data.platform

/** Writes [text] to `dir/name`, creating [dir] if needed; returns the full path. Throws on I/O failure. */
expect fun writeTextFile(dir: String, name: String, text: String): String
