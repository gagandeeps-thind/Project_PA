package com.osiris.shared.core.util

/** [size] bytes from the platform's cryptographically secure generator. */
expect fun secureRandomBytes(size: Int): ByteArray

/** Random 128-bit id as 32 lowercase hex characters; used as idempotency keys. */
fun newHexId(bytes: Int = 16): String =
    secureRandomBytes(bytes).joinToString("") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
