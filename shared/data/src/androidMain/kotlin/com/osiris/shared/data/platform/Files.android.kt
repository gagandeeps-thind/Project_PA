package com.osiris.shared.data.platform

import java.io.File

actual fun writeTextFile(dir: String, name: String, text: String): String {
    val folder = File(dir)
    if (!folder.isDirectory && !folder.mkdirs()) throw java.io.IOException("Cannot create $dir")
    val file = File(folder, name)
    file.writeText(text)
    return file.absolutePath
}
