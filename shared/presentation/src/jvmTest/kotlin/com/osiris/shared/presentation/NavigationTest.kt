package com.osiris.shared.presentation

import com.osiris.shared.domain.model.UserProfile
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.domain.repository.DevicePermission
import com.osiris.shared.domain.repository.PermissionStatus
import com.osiris.shared.presentation.navigation.AppNavigatorViewModel
import com.osiris.shared.presentation.navigation.DeepLinkParser
import com.osiris.shared.presentation.navigation.Destination
import com.osiris.shared.presentation.navigation.RootState
import com.osiris.shared.presentation.navigation.Tab
import com.osiris.shared.presentation.permission.PermissionPrimerViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest

class NavigationTest {
    private val links = DeepLinkParser("osiris.example")

    private fun TestScope.main() = UnconfinedTestDispatcher(testScheduler)

    @Test
    fun `app links and the backend's public pages parse to destinations`() {
        assertEquals(Destination.Challenge(42), links.parse("osiris://challenge/42"))
        assertEquals(Destination.Community("north-runners"), links.parse("osiris://community/north-runners?ref=x"))
        assertEquals(Destination.Invite("abc_123"), links.parse("osiris://invite/abc_123"))
        assertEquals(Destination.Invite("abc_123"), links.parse("https://osiris.example/i/abc_123"))
        assertEquals(Destination.Referral("RUN42"), links.parse("https://OSIRIS.example/join/RUN42#top"))
        assertEquals(Destination.Section(Tab.WALLET), links.parse("osiris://wallet"))
    }

    @Test
    fun `links to other hosts, unknown paths and unsafe arguments are rejected`() {
        assertNull(links.parse("https://evil.example/i/abc"))
        assertNull(links.parse("https://osiris.example.evil.com/i/abc"))
        assertNull(links.parse("https://osiris.example/p/abc"))
        assertNull(links.parse("http://osiris.example/i/abc"))
        assertNull(links.parse("osiris://challenge/-1"))
        assertNull(links.parse("osiris://challenge/42/extra"))
        assertNull(links.parse("osiris://community/..%2Fadmin"))
        assertNull(links.parse("osiris://invite/" + "a".repeat(129)))
        assertNull(links.parse("javascript:alert(1)"))
        assertNull(DeepLinkParser("").parse("https://anything/i/abc"))
    }

    @Test
    fun `first launch shows the primer, then sign-in, and never the app while signed out`() = runTest {
        val auth = FakeAuth()
        val setup = FakeDeviceSetup()
        val vm = AppNavigatorViewModel(auth, setup, links, main())
        assertEquals(RootState.PermissionPrimer, vm.state.value)
        setup.completePrimer()
        assertEquals(RootState.SignedOut(invite = null, referral = null), vm.state.value)
        vm.clear()
    }

    @Test
    fun `a restored session opens the app directly`() = runTest {
        val auth = FakeAuth()
        auth.state.value = AuthState.SignedIn(UserProfile(id = 7))
        val vm = AppNavigatorViewModel(auth, FakeDeviceSetup(primerDone = false), links, main())
        assertEquals(RootState.SignedIn(pending = null), vm.state.value)
        vm.clear()
    }

    @Test
    fun `a challenge link opened while signed out waits for sign-in`() = runTest {
        val auth = FakeAuth()
        val vm = AppNavigatorViewModel(auth, FakeDeviceSetup(primerDone = true), links, main())
        assertTrue(vm.open("osiris://challenge/9"))
        assertEquals(RootState.SignedOut(invite = null, referral = null), vm.state.value)
        auth.login("p@x.io", "secret123")
        assertEquals(RootState.SignedIn(Destination.Challenge(9)), vm.state.value)
        vm.pendingOpened()
        assertEquals(RootState.SignedIn(pending = null), vm.state.value)
        vm.clear()
    }

    @Test
    fun `invite and referral links prefill account creation`() = runTest {
        val vm = AppNavigatorViewModel(FakeAuth(), FakeDeviceSetup(primerDone = true), links, main())
        vm.open("https://osiris.example/i/tok1")
        assertEquals(RootState.SignedOut(invite = "tok1", referral = null), vm.state.value)
        vm.open("https://osiris.example/join/REF9")
        assertEquals(RootState.SignedOut(invite = null, referral = "REF9"), vm.state.value)
        assertFalse(vm.open("https://elsewhere.example/i/tok1"))
        vm.clear()
    }

    @Test
    fun `a referral link means nothing to a signed-in player`() = runTest {
        val auth = FakeAuth()
        auth.state.value = AuthState.SignedIn(UserProfile(id = 7))
        val vm = AppNavigatorViewModel(auth, FakeDeviceSetup(primerDone = true), links, main())
        vm.open("osiris://join/REF9")
        assertEquals(RootState.SignedIn(pending = null), vm.state.value)
        vm.clear()
    }

    @Test
    fun `the primer can be finished with nothing granted and records the telemetry choice`() = runTest {
        val setup = FakeDeviceSetup()
        val available = setOf(DevicePermission.LOCATION, DevicePermission.CAMERA)
        val vm = PermissionPrimerViewModel(setup, available, dispatcher = main())
        assertEquals(listOf(DevicePermission.LOCATION, DevicePermission.CAMERA), vm.state.value.items.map { it.permission })
        assertFalse(vm.state.value.telemetry)

        vm.request(DevicePermission.LOCATION)
        assertEquals(DevicePermission.LOCATION, vm.state.value.requesting)
        vm.onResult(DevicePermission.LOCATION, PermissionStatus.DENIED)
        assertNull(vm.state.value.requesting)
        assertEquals(PermissionStatus.DENIED, vm.state.value.items.first().status)

        vm.onStatuses(mapOf(DevicePermission.CAMERA to PermissionStatus.GRANTED))
        assertEquals(PermissionStatus.GRANTED, vm.state.value.items.last().status)

        vm.setTelemetry(true)
        assertTrue(setup.telemetryConsent.value)
        vm.finish()
        assertTrue(setup.primerCompleted.value)
        vm.clear()
    }
}
