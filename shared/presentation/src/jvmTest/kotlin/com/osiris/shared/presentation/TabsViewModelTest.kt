package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.data.wallet.MockWalletRepository
import com.osiris.shared.domain.model.BoardKind
import com.osiris.shared.domain.model.BoardPeriod
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.Finisher
import com.osiris.shared.domain.model.GlobalBoard
import com.osiris.shared.domain.model.HubChallenge
import com.osiris.shared.domain.model.HubSection
import com.osiris.shared.domain.model.Progression
import com.osiris.shared.domain.wallet.Chain
import com.osiris.shared.domain.wallet.PaymentMethod
import com.osiris.shared.domain.wallet.TransactionKind
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.UiMessage
import com.osiris.shared.presentation.discover.DiscoverViewModel
import com.osiris.shared.presentation.profile.ProfileViewModel
import com.osiris.shared.presentation.social.GlobalBoardsViewModel
import com.osiris.shared.presentation.wallet.WalletViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.hours
import kotlin.time.Instant
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest

class TabsViewModelTest {
    private val now = Instant.parse("2026-10-19T12:00:00Z")

    private fun TestScope.main() = UnconfinedTestDispatcher(testScheduler)

    private fun challenge(title: String) =
        ChallengeSummary(id = 4, title = title, status = "open", courseDistanceM = 5000.0, closesAt = now + 5.hours)

    @Test
    fun `discover writes each section's card text and a failed section fails alone`() = runTest {
        val challenges = FakeChallenges().apply {
            hub = mapOf(
                HubSection.LIVE to ok(listOf(HubChallenge(challenge("Park 5K"), participants = 3))),
                HubSection.UPCOMING to ok(listOf(HubChallenge(challenge("Hills"), startsInSeconds = 90 * 60))),
                HubSection.FINISHED to ok(
                    listOf(HubChallenge(challenge("Loop"), winners = listOf(Finisher(1, "Ana", 1290.0)), xpPaid = 40)),
                ),
                HubSection.COMMUNITY to fail(AppError.Offline()),
            )
        }
        val vm = DiscoverViewModel(challenges, FixedClock(now), main())
        val s = vm.state.value.sections
        assertEquals("5.00 km  •  3 players  •  5h 0m left", s.getValue(HubSection.LIVE).valueOrNull!!.single().detail)
        assertEquals("5.00 km  •  starts in 1h 30m", s.getValue(HubSection.UPCOMING).valueOrNull!!.single().detail)
        assertEquals("1. Ana 21:30  •  40 XP paid", s.getValue(HubSection.FINISHED).valueOrNull!!.single().detail)
        assertIs<Loadable.Failed>(s.getValue(HubSection.COMMUNITY))
        vm.clear()
    }

    @Test
    fun `a slow board for an old selection never replaces the current one`() = runTest {
        val slow = CompletableDeferred<Unit>()
        val communities = FakeCommunities().apply {
            boards = { kind, period, _ ->
                if (kind == BoardKind.DISTANCE) slow.await()
                ok(GlobalBoard(board = kind.wire, period = period.wire, unit = "s", lowerIsBetter = true))
            }
        }
        val vm = GlobalBoardsViewModel(communities, main())
        vm.select(BoardKind.PACE)
        slow.complete(Unit)
        assertEquals("pace", vm.state.value.board.valueOrNull?.board)
        assertEquals("21:30", vm.state.value.board.valueOrNull?.format(1290.0))
        vm.select(BoardPeriod.ALL)
        assertEquals("all", vm.state.value.board.valueOrNull?.period)
        vm.clear()
    }

    @Test
    fun `wallet filters history, validates addresses and keeps balances to completed movements`() = runTest {
        val vm = WalletViewModel(MockWalletRepository(FixedClock(now)), main())
        val overview = vm.state.value.overview.valueOrNull!!
        // 50.00 - 5.00 + 12.00 - 5.00 + 5.00; the pending withdrawal is not counted yet.
        assertEquals("$57.00", overview.balances.single().format())
        vm.filter(TransactionKind.ENTRY_FEE)
        assertEquals(2, vm.state.value.transactions.size)

        vm.addCryptoWallet(Chain.ETHEREUM, "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAeD")
        assertEquals(UiMessage.Kind.ERROR, vm.message.value?.kind)
        vm.messageShown()
        vm.addCryptoWallet(Chain.ETHEREUM, "0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed")
        val saved = vm.state.value.overview.valueOrNull!!.methods.filterIsInstance<PaymentMethod.CryptoWallet>().single()
        assertEquals("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed", saved.address)

        vm.remove(saved)
        assertTrue(vm.state.value.overview.valueOrNull!!.methods.none { it is PaymentMethod.CryptoWallet })
        vm.clear()
    }

    @Test
    fun `profile gauge measures progress through the current rank`() = runTest {
        val player = FakePlayer().apply {
            progressionResult = ok(
                Progression(
                    xp = 1000, performanceRank = "Silver", rankFloorXp = 500, nextRankXp = 1500,
                    challengesWon = 1, challengesPlayed = 4, lifetimeDistanceKm = 42.25, globalRank = 12,
                ),
            )
        }
        val vm = ProfileViewModel(player, main())
        val p = vm.state.value.valueOrNull!!
        assertEquals(0.5, p.gauge)
        assertEquals("500 XP to next rank", p.toNext)
        val metrics = p.metrics.associate { it.label to it.value }
        assertEquals("42.3 km", metrics["Distance"])
        assertEquals("25%", metrics["Win rate"])
        assertEquals("#12", metrics["Global rank"])
        vm.clear()
    }
}
