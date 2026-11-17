package com.osiris.shared.data

import com.osiris.shared.core.error.AppError
import com.osiris.shared.data.payments.Sha256
import com.osiris.shared.data.payments.StoreAccount
import io.ktor.util.hex
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class PaymentsRepositoryTest {
    private val verified = """{"product_id":"osiris_crystals_starter","kind":"consumable","state":"credited",
        "crystals_credited":1500,"balance":1620,"consume":true,"entitled":true}"""

    @Test
    fun `account binding matches the server's vectors for user 42`() {
        // Computed with Python: hashlib.sha256(b"osiris:42") and uuid.uuid5(uuid.NAMESPACE_URL, "osiris:42").
        assertEquals("df7e2e42324356cfe97e6fe75ee3e9467aabecf5393e9b8a5ba23d3dbb9e745d", StoreAccount.playObfuscatedAccountId(42))
        assertEquals("3992d9c9-b83f-5732-b590-2b6edfe75473", StoreAccount.appStoreAccountToken(42))
    }

    @Test
    fun `sha256 matches standard vectors across block boundaries`() {
        assertEquals("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", hex(Sha256.digest(ByteArray(0))))
        assertEquals(
            "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3",
            hex(Sha256.digest(ByteArray(1000) { 'a'.code.toByte() })),
        )
        val jdk = java.security.MessageDigest.getInstance("SHA-256")
        for (size in 50..130) {
            val input = ByteArray(size) { it.toByte() }
            assertEquals(hex(jdk.digest(input)), hex(Sha256.digest(input)), "size $size")
        }
    }

    @Test
    fun `google play verify sends product and token and reads the server's figures`() = test {
        val app = TestApp()
        app.server.json("POST /api/v2/payments/google-play/verify") { verified }
        val v = app.graph.payments.verifyGooglePlay("osiris_crystals_starter", "tok").getOrThrow()
        val body = app.server.calls.single().body!!.jsonObject
        assertEquals("tok", body["purchase_token"]!!.jsonPrimitive.content)
        assertEquals("osiris_crystals_starter", body["product_id"]!!.jsonPrimitive.content)
        assertEquals(1500, v.crystalsCredited)
        assertEquals(1620, v.balance)
        assertTrue(v.entitled && v.consume)
    }

    @Test
    fun `app store verify posts the signed transaction`() = test {
        val app = TestApp()
        app.server.json("POST /api/v2/payments/app-store/verify") { verified }
        assertEquals(1620, app.graph.payments.verifyAppStore("a.b.c").getOrThrow().balance)
        assertEquals("a.b.c", app.server.calls.single().body!!.jsonObject["signed_transaction"]!!.jsonPrimitive.content)
    }

    @Test
    fun `unconfigured store answers 503 and nothing is granted`() = test {
        val app = TestApp()
        app.server.json("POST /api/v2/payments/google-play/verify", status = 503) { """{"detail":"Purchases are unavailable"}""" }
        val error = app.graph.payments.verifyGooglePlay("osiris_crystals_starter", "tok").errorOrNull()
        assertEquals(503, (error as AppError.Http).status)
    }

    @Test
    fun `entitlements come from the store-neutral path`() = test {
        val app = TestApp()
        app.server.json("GET /api/v2/payments/entitlements") {
            """{"osiris_pass":true,"osiris_pass_product_id":"osiris_pass_monthly","osiris_pass_state":"active","founder_pack":false}"""
        }
        val e = app.graph.payments.entitlements().getOrThrow()
        assertTrue(e.osirisPass)
        assertEquals("osiris_pass_monthly", e.osirisPassProductId)
        assertFalse(e.founderPack)
    }
}
