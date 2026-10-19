package com.osiris.shared.core.logging

actual fun platformLogger(): Logger = object : Logger {
    override fun debug(tag: String, message: String) = println("D/$tag: $message")
    override fun info(tag: String, message: String) = println("I/$tag: $message")
    override fun warn(tag: String, message: String, error: Throwable?) =
        System.err.println("W/$tag: $message" + (error?.let { " ($it)" } ?: ""))
    override fun error(tag: String, message: String, error: Throwable?) =
        System.err.println("E/$tag: $message" + (error?.let { " ($it)" } ?: ""))
}
