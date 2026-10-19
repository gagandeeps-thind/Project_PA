package com.osiris.shared.core.util

private val generator = java.security.SecureRandom()

actual fun secureRandomBytes(size: Int): ByteArray = ByteArray(size).also(generator::nextBytes)
