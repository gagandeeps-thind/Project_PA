package com.osiris.shared.core.logging

import platform.Foundation.NSLog

actual fun platformLogger(): Logger = object : Logger {
    override fun debug(tag: String, message: String) = NSLog("D/%@: %@", tag, message)
    override fun info(tag: String, message: String) = NSLog("I/%@: %@", tag, message)
    override fun warn(tag: String, message: String, error: Throwable?) =
        NSLog("W/%@: %@ %@", tag, message, error?.toString() ?: "")
    override fun error(tag: String, message: String, error: Throwable?) =
        NSLog("E/%@: %@ %@", tag, message, error?.toString() ?: "")
}
