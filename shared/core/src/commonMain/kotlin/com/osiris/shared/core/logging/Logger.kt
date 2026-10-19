package com.osiris.shared.core.logging

/** Minimal logging facade; each platform writes to its native log (Logcat, os_log, stdout). */
interface Logger {
    fun debug(tag: String, message: String)
    fun info(tag: String, message: String)
    fun warn(tag: String, message: String, error: Throwable? = null)
    fun error(tag: String, message: String, error: Throwable? = null)

    /** Drops everything; the default in tests. */
    object None : Logger {
        override fun debug(tag: String, message: String) = Unit
        override fun info(tag: String, message: String) = Unit
        override fun warn(tag: String, message: String, error: Throwable?) = Unit
        override fun error(tag: String, message: String, error: Throwable?) = Unit
    }
}

/** The platform's native logger. */
expect fun platformLogger(): Logger
