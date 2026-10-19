package com.osiris.shared.core.logging

import android.util.Log

actual fun platformLogger(): Logger = object : Logger {
    override fun debug(tag: String, message: String) {
        Log.d(tag, message)
    }
    override fun info(tag: String, message: String) {
        Log.i(tag, message)
    }
    override fun warn(tag: String, message: String, error: Throwable?) {
        Log.w(tag, message, error)
    }
    override fun error(tag: String, message: String, error: Throwable?) {
        Log.e(tag, message, error)
    }
}
