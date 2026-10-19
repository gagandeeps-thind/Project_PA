package com.osiris.shared.data.platform

import kotlinx.cinterop.BetaInteropApi
import kotlinx.cinterop.ExperimentalForeignApi
import platform.Foundation.NSFileManager
import platform.Foundation.NSString
import platform.Foundation.NSUTF8StringEncoding
import platform.Foundation.create
import platform.Foundation.writeToFile

@OptIn(ExperimentalForeignApi::class, BetaInteropApi::class)
actual fun writeTextFile(dir: String, name: String, text: String): String {
    val manager = NSFileManager.defaultManager
    if (!manager.fileExistsAtPath(dir) &&
        !manager.createDirectoryAtPath(dir, withIntermediateDirectories = true, attributes = null, error = null)
    ) {
        throw IllegalStateException("Cannot create $dir")
    }
    val path = "$dir/$name"
    val ok = NSString.create(string = text).writeToFile(path, atomically = true, encoding = NSUTF8StringEncoding, error = null)
    if (!ok) throw IllegalStateException("Cannot write $path")
    return path
}
