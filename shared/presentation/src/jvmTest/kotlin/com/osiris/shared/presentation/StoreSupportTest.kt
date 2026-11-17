package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.UserProfile
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.domain.repository.PaymentsRepository
import com.osiris.shared.domain.wallet.PurchaseVerification
import com.osiris.shared.domain.wallet.StoreEntitlements
import com.osiris.shared.presentation.wallet.StoreSupport
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest

class StoreSupportTest {
    private class FakePayments(var appStore: Outcome<PurchaseVerification>) : PaymentsRepository {
        override suspend fun verifyGooglePlay(productId: String, purchaseToken: String) = appStore
        override suspend fun verifyAppStore(signedTransaction: String) = appStore
        override suspend fun entitlements(): Outcome<StoreEntitlements> = ok(StoreEntitlements(founderPack = true))
    }

    @Test
    fun accountBindingFollowsTheSignedInPlayer() {
        val auth = FakeAuth()
        val store = StoreSupport(auth, FakePayments(ok(PurchaseVerification())), sellsPass = false)
        assertNull(store.playAccountId())
        assertNull(store.appStoreAccountToken())
        auth.state.value = AuthState.SignedIn(UserProfile(id = 42))
        assertEquals("df7e2e42324356cfe97e6fe75ee3e9467aabecf5393e9b8a5ba23d3dbb9e745d", store.playAccountId())
        assertEquals("3992d9c9-b83f-5732-b590-2b6edfe75473", store.appStoreAccountToken())
    }

    @Test
    fun appStoreTransactionIsFinishedOnlyWhenTheServerRecordedIt() = runTest {
        val payments = FakePayments(ok(PurchaseVerification(crystalsCredited = 500, balance = 510, entitled = true)))
        val store = StoreSupport(FakeAuth(), payments, sellsPass = false)
        val done = store.verifyAppStore("a.b.c")
        assertTrue(done.finish)
        assertEquals(510, done.verification?.balance)

        payments.appStore = fail(AppError.Http(503, null, "Purchases are temporarily unavailable."))
        val closed = store.verifyAppStore("a.b.c")
        assertFalse(closed.finish)
        assertEquals("Purchases are temporarily unavailable.", closed.error)
        assertTrue(store.entitlements()!!.founderPack)
    }
}
