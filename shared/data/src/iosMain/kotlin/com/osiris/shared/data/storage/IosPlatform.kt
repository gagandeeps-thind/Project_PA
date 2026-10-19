package com.osiris.shared.data.storage

import app.cash.sqldelight.driver.native.NativeSqliteDriver
import app.cash.sqldelight.driver.native.wrapConnection
import co.touchlab.sqliter.DatabaseConfiguration
import com.osiris.shared.core.logging.platformLogger
import com.osiris.shared.data.db.OsirisDatabase
import com.osiris.shared.data.network.platformHttpEngine
import com.russhwolf.settings.NSUserDefaultsSettings
import kotlinx.cinterop.BetaInteropApi
import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.cinterop.alloc
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.value
import platform.CoreFoundation.CFDictionaryRef
import platform.CoreFoundation.CFTypeRefVar
import platform.Foundation.CFBridgingRelease
import platform.Foundation.CFBridgingRetain
import platform.Foundation.NSData
import platform.Foundation.NSDocumentDirectory
import platform.Foundation.NSFileManager
import platform.Foundation.NSString
import platform.Foundation.NSUTF8StringEncoding
import platform.Foundation.NSUserDefaults
import platform.Foundation.NSUserDomainMask
import platform.Foundation.create
import platform.Foundation.dataUsingEncoding
import platform.Security.SecItemAdd
import platform.Security.SecItemCopyMatching
import platform.Security.SecItemDelete
import platform.Security.errSecSuccess
import platform.Security.kSecAttrAccessible
import platform.Security.kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
import platform.Security.kSecAttrAccount
import platform.Security.kSecAttrService
import platform.Security.kSecClass
import platform.Security.kSecClassGenericPassword
import platform.Security.kSecMatchLimit
import platform.Security.kSecMatchLimitOne
import platform.Security.kSecReturnData
import platform.Security.kSecValueData

object IosPlatform {
    const val DATABASE_NAME = "osiris_exercise.db"

    fun create(recordingAllowed: Boolean): PlatformDependencies = PlatformDependencies(
        settings = NSUserDefaultsSettings(NSUserDefaults.standardUserDefaults),
        secureStore = KeychainSecureStore(),
        httpEngine = platformHttpEngine(),
        openDatabase = {
            NativeSqliteDriver(
                schema = OsirisDatabase.Schema,
                name = DATABASE_NAME,
                onConfiguration = { config: DatabaseConfiguration ->
                    config.copy(extendedConfig = config.extendedConfig.copy(foreignKeyConstraints = true))
                },
            )
        },
        logger = platformLogger(),
        recordingsDir = if (recordingAllowed) documentsDir()?.let { "$it/pose_recordings" } else null,
    )

    @OptIn(ExperimentalForeignApi::class)
    private fun documentsDir(): String? =
        NSFileManager.defaultManager.URLForDirectory(NSDocumentDirectory, NSUserDomainMask, null, true, null)?.path
}

/** Generic-password items in the Keychain, readable only on this device after first unlock. */
@OptIn(ExperimentalForeignApi::class, BetaInteropApi::class)
internal class KeychainSecureStore(private val service: String = "com.osiris.player") : SecureStore {

    private fun query(key: String, extra: Map<Any?, Any?> = emptyMap()): CFDictionaryRef? {
        val map = mutableMapOf<Any?, Any?>(
            kSecClass to kSecClassGenericPassword,
            kSecAttrService to service,
            kSecAttrAccount to key,
        )
        map.putAll(extra)
        @Suppress("UNCHECKED_CAST")
        return CFBridgingRetain(map as Map<Any?, *>) as CFDictionaryRef?
    }

    override suspend fun get(key: String): String? = memScoped {
        val q = query(key, mapOf(kSecReturnData to true, kSecMatchLimit to kSecMatchLimitOne))
        val result = alloc<CFTypeRefVar>()
        val status = SecItemCopyMatching(q, result.ptr)
        CFBridgingRelease(q)
        if (status != errSecSuccess) return@memScoped null
        val data = CFBridgingRelease(result.value) as? NSData ?: return@memScoped null
        NSString.create(data = data, encoding = NSUTF8StringEncoding)?.toString()
    }

    override suspend fun put(key: String, value: String) {
        remove(key)
        @Suppress("CAST_NEVER_SUCCEEDS")
        val data = (value as NSString).dataUsingEncoding(NSUTF8StringEncoding) ?: return
        val q = query(key, mapOf(kSecValueData to data, kSecAttrAccessible to kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly))
        val status = SecItemAdd(q, null)
        CFBridgingRelease(q)
        check(status == errSecSuccess) { "Keychain write failed: $status" }
    }

    override suspend fun remove(key: String) {
        val q = query(key)
        SecItemDelete(q)
        CFBridgingRelease(q)
    }
}
