package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.AriseAttackResult
import com.osiris.shared.domain.model.AriseDomain
import com.osiris.shared.domain.model.AriseDomains
import com.osiris.shared.domain.model.AriseRoute
import com.osiris.shared.domain.model.AriseWorkout
import com.osiris.shared.domain.model.AriseWorkoutResult
import com.osiris.shared.domain.model.HeatCell
import com.osiris.shared.domain.model.Heatmap
import com.osiris.shared.domain.model.MapStyle
import com.osiris.shared.domain.model.Overlay
import com.osiris.shared.domain.model.TerrainLayer
import com.osiris.shared.domain.model.WorkoutSet
import com.osiris.shared.domain.repository.AriseRepository
import com.osiris.shared.domain.run.LatLng
import com.osiris.shared.domain.run.LocationFix
import com.osiris.shared.domain.run.Sport
import com.osiris.shared.presentation.arise.AriseViewModel
import com.osiris.shared.presentation.arise.RouteMode
import com.osiris.shared.presentation.arise.WorkoutTarget
import com.osiris.shared.presentation.arise.WorkoutViewModel
import com.osiris.shared.presentation.run.RunDialog
import com.osiris.shared.presentation.run.RunViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runTest

class FakeArise : AriseRepository {
    val loadedAround = mutableListOf<LatLng>()
    var fail = false
    val published = mutableListOf<Triple<Int, String, Boolean>>()
    var routes = listOf(route(5))

    override suspend fun nearbyRoutes(position: LatLng, radiusKm: Double): Outcome<List<AriseRoute>> {
        loadedAround += position
        return if (fail) Outcome.Failure(AppError.Offline()) else ok(routes)
    }

    override suspend fun publishRoute(runId: Int, name: String, hideEnds: Boolean): Outcome<AriseRoute> {
        published += Triple(runId, name, hideEnds)
        return ok(route(runId))
    }

    override fun cached(id: Int): AriseRoute? = routes.firstOrNull { it.id == id }

    var claimError: AppError? = null
    var attackStatus = "won"
    var workoutDone = true
    val completed = mutableListOf<String>()
    var domainsLoaded = 0

    override suspend fun nearbyDomains(position: LatLng, radiusKm: Double): Outcome<AriseDomains> {
        domainsLoaded++
        return ok(AriseDomains(suggested = listOf(domain(8)), hard = listOf(domain(9))))
    }

    override suspend fun claimDomain(runId: Int): Outcome<AriseDomain> =
        claimError?.let { Outcome.Failure(it) } ?: ok(domain(30))

    override suspend fun exceed(domainId: Int): Outcome<AriseWorkout> = ok(workout)

    override suspend fun completeExceed(domainId: Int): Outcome<AriseWorkoutResult> {
        completed += "exceed:$domainId"
        return ok(AriseWorkoutResult(workoutDone, domain(domainId)))
    }

    override suspend fun attack(domainId: Int, runId: Int): Outcome<AriseAttackResult> =
        ok(
            AriseAttackResult(
                44, attackStatus, if (attackStatus == "failed") listOf("TOO_SLOW") else emptyList(), workout, domain(domainId),
            ),
        )

    override suspend fun completeAttack(attackId: Int): Outcome<AriseAttackResult> {
        completed += "attack:$attackId"
        return ok(AriseAttackResult(attackId, if (workoutDone) "won" else "needs_workout", emptyList(), workout, domain(8)))
    }

    override fun cachedAttack(attackId: Int): AriseAttackResult? =
        AriseAttackResult(attackId, "needs_workout", emptyList(), workout, domain(8))

    val heatAsked = mutableListOf<Heatmap>()

    override suspend fun heatmap(kind: Heatmap, south: Double, west: Double, north: Double, east: Double): Outcome<List<HeatCell>> {
        heatAsked += kind
        return ok(listOf(HeatCell((south + north) / 2, (west + east) / 2, 4)))
    }

    override fun cachedDomain(id: Int): AriseDomain? = domain(id)

    override suspend fun setPhoto(domainId: Int, jpegBase64: String): Outcome<AriseDomain> = ok(domain(domainId))

    companion object {
        val workout = AriseWorkout(listOf(WorkoutSet("pushup", 10, 10), WorkoutSet("squat", 15, 20)), 25)

        fun domain(id: Int) = AriseDomain(
            id = id, ownerId = 2, ownerName = "Runner 2", areaSqkm = 0.2, distanceM = 1600.0, durationS = 540.0,
            centroidLat = 52.37, centroidLng = 4.89,
            geometry = listOf(LatLng(52.37, 4.89), LatLng(52.38, 4.89), LatLng(52.38, 4.90)),
        )

        fun route(id: Int) = AriseRoute(
            id = id, name = "River loop", activityType = "trail", distanceM = 2400.0, benchmarkSeconds = 900.0,
            hideEnds = true, ownerName = "Runner 1", line = listOf(LatLng(52.37, 4.89), LatLng(52.38, 4.89)),
        )
    }
}

class AriseViewModelTest {
    private fun TestScope.main() = UnconfinedTestDispatcher(testScheduler)

    private fun TestScope.vm(arise: AriseRepository = FakeArise()) = AriseViewModel(arise, dispatcher = main())

    @Test
    fun `the map opens on Standard with POIs and bike lanes, flat, no heatmap or terrain`() = runTest {
        val s = vm().state.value
        assertEquals(MapStyle.STANDARD, s.style)
        assertEquals(setOf(Overlay.POIS, Overlay.BIKE_LANES), s.overlays)
        assertFalse(s.threeD)
        assertNull(s.heatmap)
        assertNull(s.terrain)
    }

    @Test
    fun `heatmap and terrain are single choice and picking the same one again clears it`() = runTest {
        val vm = vm()
        vm.setHeatmap(Heatmap.GLOBAL)
        vm.setHeatmap(Heatmap.NIGHT)
        assertEquals(Heatmap.NIGHT, vm.state.value.heatmap)
        vm.setHeatmap(Heatmap.NIGHT)
        assertNull(vm.state.value.heatmap)
        vm.setTerrain(TerrainLayer.AVALANCHE)
        vm.setTerrain(TerrainLayer.ASPECT)
        assertEquals(TerrainLayer.ASPECT, vm.state.value.terrain)
        vm.setTerrain(TerrainLayer.ASPECT)
        assertNull(vm.state.value.terrain)
    }

    @Test
    fun `overlays toggle independently`() = runTest {
        val vm = vm()
        vm.toggleOverlay(Overlay.POIS)
        assertEquals(setOf(Overlay.BIKE_LANES), vm.state.value.overlays)
        vm.toggleOverlay(Overlay.POIS)
        assertTrue(Overlay.POIS in vm.state.value.overlays)
    }

    @Test
    fun `attack mode closes the plus menu and the plus menu leaves attack mode`() = runTest {
        val vm = vm()
        vm.toggleFab()
        vm.toggleAttack()
        assertTrue(vm.state.value.attackMode)
        assertFalse(vm.state.value.fabOpen)
        vm.toggleFab()
        assertTrue(vm.state.value.fabOpen)
        assertFalse(vm.state.value.attackMode)
    }

    @Test
    fun `style and 3D switch`() = runTest {
        val vm = vm()
        vm.setStyle(MapStyle.WINTER)
        vm.toggle3D()
        assertEquals(MapStyle.WINTER, vm.state.value.style)
        assertTrue(vm.state.value.threeD)
    }

    @Test
    fun `routes load around the first position and again only after moving a kilometre`() = runTest {
        val arise = FakeArise()
        val vm = vm(arise)
        vm.onLocation(LatLng(52.37, 4.89))
        vm.onLocation(LatLng(52.371, 4.89))
        assertEquals(1, arise.loadedAround.size)
        assertEquals(listOf(5), vm.state.value.routes.map { it.id })
        vm.onLocation(LatLng(52.39, 4.89))
        assertEquals(2, arise.loadedAround.size)
    }

    @Test
    fun `a failed load waits before trying again instead of retrying on every fix`() = runTest {
        val arise = FakeArise().apply { fail = true }
        val vm = vm(arise)
        vm.onLocation(LatLng(52.37, 4.89))
        vm.onLocation(LatLng(52.37, 4.89))
        assertEquals(1, arise.loadedAround.size)
        advanceTimeBy(31_000)
        arise.fail = false
        vm.onLocation(LatLng(52.37, 4.89))
        assertEquals(2, arise.loadedAround.size)
        assertEquals(listOf(5), vm.state.value.routes.map { it.id })
    }

    @Test
    fun `trail is greyed out only when the terrain check says there is no forest`() = runTest {
        val vm = vm()
        vm.openPicker(RouteMode.RECORD)
        assertEquals(RouteMode.RECORD, vm.state.value.picker?.mode)
        assertTrue(vm.state.value.picker!!.enabled(Sport.TRAIL))
        vm.onTrailCheck(false)
        assertFalse(vm.state.value.picker!!.enabled(Sport.TRAIL))
        assertTrue(vm.state.value.picker!!.enabled(Sport.HIKE))
        vm.closePicker()
        assertNull(vm.state.value.picker)
    }

    @Test
    fun `server activity types map to sports and unknown ones run`() {
        assertEquals(Sport.TRAIL, Sport.fromWire("trail"))
        assertEquals(Sport.RUN, Sport.fromWire("jog"))
    }

    @Test
    fun `tapping a route selects it and the selection can be cleared`() = runTest {
        val vm = vm()
        vm.onLocation(LatLng(52.37, 4.89))
        vm.selectRoute(5)
        assertEquals(5, vm.state.value.selectedRoute?.id)
        vm.selectRoute(null)
        assertNull(vm.state.value.selectedRoute)
    }

    @Test
    fun `a heatmap loads around the player and clearing it empties the layer`() = runTest {
        val arise = FakeArise()
        val vm = vm(arise)
        vm.setHeatmap(Heatmap.NIGHT)
        assertTrue(vm.state.value.heat.isEmpty())
        vm.onLocation(LatLng(52.37, 4.89))
        assertEquals(listOf(Heatmap.NIGHT), arise.heatAsked)
        assertEquals(4, vm.state.value.heat.single().w)
        vm.setHeatmap(Heatmap.NIGHT)
        assertTrue(vm.state.value.heat.isEmpty())
    }

    @Test
    fun `attack mode loads the domains around the player`() = runTest {
        val arise = FakeArise()
        val vm = vm(arise)
        vm.onLocation(LatLng(52.37, 4.89))
        vm.toggleAttack()
        assertEquals(listOf(8), vm.state.value.domains?.suggested?.map { it.id })
        assertEquals(1, arise.domainsLoaded)
    }

    private fun TestScope.runVm(arise: FakeArise, record: Boolean = false, attack: Int? = null) = RunViewModel(
        FakeRuns(), FakeChallenges(), FakePlayer(), sport = Sport.RUN, record = record, attackDomainId = attack, arise = arise,
        clock = FixedClock(Instant.parse("2026-06-21T12:00:00Z")), dispatcher = main(),
    ).apply {
        onLocation(LocationFix(52.37, 4.89))
        start()
        finish()
    }

    @Test
    fun `a recorded loop claims a domain and asks finish or exceed, then offers the route`() = runTest {
        val vm = runVm(FakeArise(), record = true)
        vm.dismissDialog()
        val ask = assertIs<RunDialog.FinishOrExceed>(vm.state.value.dialog)
        assertEquals(30, ask.domain.id)
        assertFalse(ask.captured)
        vm.dismissDialog()
        assertIs<RunDialog.PublishRoute>(vm.state.value.dialog)
        vm.clear()
    }

    @Test
    fun `a recorded run that is not a loop goes straight to publishing`() = runTest {
        val arise = FakeArise().apply { claimError = AppError.Http(422, "NOT_A_LOOP", "Finish where you started") }
        val vm = runVm(arise, record = true)
        vm.dismissDialog()
        assertIs<RunDialog.PublishRoute>(vm.state.value.dialog)
        vm.clear()
    }

    @Test
    fun `an attack run draws the domain's outline to run around`() = runTest {
        val vm = RunViewModel(
            FakeRuns(), FakeChallenges(), FakePlayer(), attackDomainId = 8, arise = FakeArise(), dispatcher = main(),
        )
        val ring = vm.state.value.course?.route
        assertEquals(4, ring?.size)
        assertEquals(ring?.first(), ring?.last())
        vm.clear()
    }

    @Test
    fun `an attack run reports a capture, a workout to do, or why it failed`() = runTest {
        val won = runVm(FakeArise(), attack = 8)
        assertTrue(assertIs<RunDialog.FinishOrExceed>(won.state.value.dialog).captured)
        won.clear()
        val workout = runVm(FakeArise().apply { attackStatus = "needs_workout" }, attack = 8)
        assertEquals(44, assertIs<RunDialog.AttackWorkout>(workout.state.value.dialog).attackId)
        workout.clear()
        val failed = runVm(FakeArise().apply { attackStatus = "failed" }, attack = 8)
        val info = assertIs<RunDialog.Info>(failed.state.value.dialog)
        assertEquals("Attack failed", info.title)
        assertTrue("slower" in info.body)
        failed.clear()
    }

    @Test
    fun `the workout walks through sets with rests and submits`() = runTest {
        val arise = FakeArise().apply { workoutDone = false }
        val vm = WorkoutViewModel(arise, WorkoutTarget.Exceed(30), dispatcher = main())
        assertEquals(2, vm.state.value.workout?.sets?.size)
        vm.setDone(0)
        assertEquals(10, vm.state.value.restLeft)
        advanceTimeBy(10_500)
        assertNull(vm.state.value.restLeft)
        vm.submit()
        assertEquals(listOf("exceed:30"), arise.completed)
        assertFalse(vm.state.value.finished)
        arise.workoutDone = true
        vm.setDone(1)
        vm.submit()
        assertTrue(vm.state.value.finished)
        vm.clear()
    }

    @Test
    fun `an attack workout comes from the attack result`() = runTest {
        val arise = FakeArise()
        val vm = WorkoutViewModel(arise, WorkoutTarget.Attack(44), dispatcher = main())
        assertEquals(25, vm.state.value.workout?.totalReps)
        vm.submit()
        assertEquals(listOf("attack:44"), arise.completed)
        assertTrue(vm.state.value.finished)
        vm.clear()
    }

    @Test
    fun `a recorded run offers to publish the route instead of a private course`() = runTest {
        val arise = FakeArise().apply { claimError = AppError.Http(422, "NOT_A_LOOP", "Not a loop") }
        val vm = RunViewModel(
            FakeRuns(), FakeChallenges(), FakePlayer(), sport = Sport.TRAIL, record = true, arise = arise,
            clock = FixedClock(Instant.parse("2026-06-21T12:00:00Z")), dispatcher = main(),
        )
        assertEquals(Sport.TRAIL, vm.state.value.sport)
        vm.onLocation(LocationFix(52.37, 4.89))
        vm.start()
        vm.finish()
        assertIs<RunDialog.Celebrate>(vm.state.value.dialog)
        vm.dismissDialog()
        val offer = assertIs<RunDialog.PublishRoute>(vm.state.value.dialog)
        vm.publishRoute(offer.runId, "Forest loop", hideEnds = false)
        assertEquals(listOf(Triple(11, "Forest loop", false)), arise.published)
        assertNull(vm.state.value.dialog)
        vm.clear()
    }
}
