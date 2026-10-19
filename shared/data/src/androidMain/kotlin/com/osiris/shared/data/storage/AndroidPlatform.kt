package com.osiris.shared.data.storage

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import app.cash.sqldelight.driver.android.AndroidSqliteDriver
import com.osiris.shared.core.logging.platformLogger
import com.osiris.shared.data.db.OsirisDatabase
import com.osiris.shared.data.network.platformHttpEngine
import com.russhwolf.settings.SharedPreferencesSettings
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object AndroidPlatform {
    const val DATABASE_NAME = "osiris_exercise.db"

    fun create(context: Context, recordingAllowed: Boolean): PlatformDependencies {
        val app = context.applicationContext
        return PlatformDependencies(
            settings = SharedPreferencesSettings(app.getSharedPreferences("osiris", Context.MODE_PRIVATE)),
            secureStore = KeystoreSecureStore(app),
            httpEngine = platformHttpEngine(),
            openDatabase = {
                AndroidSqliteDriver(
                    schema = OsirisDatabase.Schema,
                    context = app,
                    name = DATABASE_NAME,
                    callback = object : AndroidSqliteDriver.Callback(OsirisDatabase.Schema) {
                        override fun onConfigure(db: androidx.sqlite.db.SupportSQLiteDatabase) {
                            db.setForeignKeyConstraintsEnabled(true)
                        }
                    },
                )
            },
            logger = platformLogger(),
            recordingsDir = if (recordingAllowed) File(app.filesDir, "pose_recordings").absolutePath else null,
        )
    }
}

/**
 * AES-256-GCM with a non-exportable key in the Android Keystore; ciphertexts live in a private
 * SharedPreferences file. A key lost after a device restore makes values unreadable, which reads
 * as "signed out" rather than a crash.
 */
internal class KeystoreSecureStore(context: Context) : SecureStore {
    private val prefs = context.getSharedPreferences("osiris.secure", Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return gen.generateKey()
    }

    override suspend fun get(key: String): String? = withContext(Dispatchers.IO) {
        val stored = prefs.getString(key, null) ?: return@withContext null
        runCatching {
            val bytes = Base64.decode(stored, Base64.NO_WRAP)
            val iv = bytes.copyOfRange(0, IV_BYTES)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
            String(cipher.doFinal(bytes, IV_BYTES, bytes.size - IV_BYTES), Charsets.UTF_8)
        }.getOrElse {
            prefs.edit().remove(key).apply()
            null
        }
    }

    override suspend fun put(key: String, value: String) = withContext(Dispatchers.IO) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val sealed = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        prefs.edit().putString(key, Base64.encodeToString(sealed, Base64.NO_WRAP)).apply()
    }

    override suspend fun remove(key: String) = withContext(Dispatchers.IO) {
        prefs.edit().remove(key).apply()
    }

    private companion object {
        const val KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "osiris.session"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
    }
}
