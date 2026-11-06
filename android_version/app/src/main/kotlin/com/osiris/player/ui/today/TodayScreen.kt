package com.osiris.player.ui.today

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.TextAutoSize
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.HealthAndSafety
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.PersonAddAlt
import androidx.compose.material.icons.outlined.Public
import androidx.compose.material.icons.outlined.Route
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Videocam
import androidx.compose.material.icons.outlined.WbTwilight
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.osiris.player.platform.location.LocationClient
import com.osiris.player.platform.share.ShareEffect
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.social.PostMedia
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.design.EnergyRing
import com.osiris.player.ui.design.IconOrb
import com.osiris.player.ui.design.KeyButton
import com.osiris.player.ui.design.LocalLight
import com.osiris.player.ui.design.RaisedButton
import com.osiris.player.ui.design.accentKey
import com.osiris.player.ui.design.bleed
import com.osiris.player.ui.design.softEdges
import com.osiris.player.ui.design.well
import com.osiris.player.ui.exercise.exerciseIcon
import com.osiris.player.ui.navigation.Routes
import com.osiris.player.ui.navigation.open
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.core.design.FrostMatte
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.Quest
import com.osiris.shared.domain.model.StarterChallenge
import com.osiris.shared.domain.model.SuggestedChallenge
import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.model.WeeklyGoal
import com.osiris.shared.domain.model.WorkoutPlan
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.today.HomeScreenState
import com.osiris.shared.presentation.today.TodayViewModel
import kotlin.math.absoluteValue
import kotlinx.coroutines.flow.firstOrNull

@Suppress("CyclomaticComplexMethod")
@Composable
fun TodayScreen(graph: AppGraph, nav: NavHostController) {
    val vm = rememberShared { graph.today() }
    val home by vm.home.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val location = remember { LocationClient(context) }

    LaunchedEffect(Unit) {
        val fix = if (location.hasPermission()) runCatching { location.fixes().firstOrNull() }.getOrNull() else null
        if (fix != null) vm.onPosition(fix.position) else vm.onNoPosition()
    }

    ShareEffect(home.share, onShared = vm::shared)

    OsirisScaffold(
        "Osiris",
        vm,
        actions = {
            IconButton(onClick = { vm.openNotifications(true) }) {
                BadgedBox(
                    badge = {
                        if (home.unreadNotifications > 0) {
                            Badge(containerColor = OsirisColors.Secondary) {
                                Text("${home.unreadNotifications}")
                            }
                        }
                    },
                ) {
                    Icon(Icons.Outlined.Notifications, contentDescription = "Notifications")
                }
            }
            IconButton(onClick = { nav.open(Routes.SETTINGS) }) {
                Icon(Icons.Outlined.Settings, contentDescription = "Settings")
            }
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = false,
            onRefresh = vm::refresh,
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            LoadableContent(home.today, onRetry = vm::refresh) { t ->
                TodayHomeContent(
                    t = t,
                    home = home,
                    vm = vm,
                    baseUrl = graph.config.apiBaseUrl,
                    onStartRun = { challengeId ->
                        vm.onStartQuest()
                        nav.open(Routes.run(challengeId))
                    },
                    onStartWorkoutPlan = { plan ->
                        if (plan.option.isCameraExercise) {
                            nav.open(
                                Routes.exerciseCamera(
                                    key = plan.optionKey,
                                    sets = plan.sets,
                                    reps = plan.repsPerSet,
                                    holdS = plan.holdSecondsPerSet,
                                ),
                            )
                        } else {
                            vm.onStartQuest()
                            nav.open(Routes.run())
                        }
                    },
                    onChallenge = { nav.open(Routes.challenge(it)) },
                    onOpen = nav::open,
                )
            }
        }
    }

    if (home.notificationsOpen) {
        NotificationsSheet(
            notifications = home.notifications,
            onMarkRead = vm::markNotificationRead,
            onMarkAllRead = vm::markAllNotificationsRead,
            onOpenRoute = { route ->
                when (route) {
                    "exercise" -> nav.open(Routes.EXERCISE)
                    "challenges" -> nav.open(Routes.CHALLENGES)
                    "communities" -> nav.open(Routes.COMMUNITIES)
                    else -> route.removePrefix("group/").toIntOrNull()?.takeIf { route.startsWith("group/") }
                        ?.let { nav.open(Routes.group(it)) }
                }
            },
            onDismiss = { vm.openNotifications(false) },
        )
    }

    if (home.workoutCustomizerOpen) {
        WorkoutCustomizerSheet(
            plan = home.workoutPlan,
            onSelectOption = vm::selectWorkoutOption,
            onSetReps = vm::setWorkoutReps,
            onSetSets = vm::setWorkoutSets,
            onSetHoldSeconds = vm::setWorkoutHoldSeconds,
            onSetDistanceKm = vm::setWorkoutDistanceKm,
            onStart = {
                vm.openWorkoutCustomizer(false)
                val plan = home.workoutPlan
                if (plan.option.isCameraExercise) {
                    nav.open(
                        Routes.exerciseCamera(
                            key = plan.optionKey,
                            sets = plan.sets,
                            reps = plan.repsPerSet,
                            holdS = plan.holdSecondsPerSet,
                        ),
                    )
                } else {
                    vm.onStartQuest()
                    nav.open(Routes.run())
                }
            },
            onDismiss = { vm.openWorkoutCustomizer(false) },
        )
    }

    if (home.trendingSheetOpen) {
        TrendingOsiriansSheet(
            osirians = home.trendingOsirians,
            onFollowToggle = { person ->
                if (person.following) vm.unfollowOsirian(person.userId) else vm.followOsirian(person.userId)
            },
            onDismiss = { vm.openTrendingOsirians(false) },
        )
    }

    if (home.postComposerOpen) {
        val streakWeeks = home.today.valueOrNull?.streakWeeks ?: 1
        PostComposerSheet(
            plan = home.workoutPlan,
            streakWeeks = streakWeeks,
            onPublish = vm::publishPost,
            onDismiss = { vm.openPostComposer(false) },
        )
    }

    val activePostId = home.activeCommentsPostId
    if (activePostId != null) {
        CommentsSheet(
            comments = home.activePostComments,
            onAddComment = { body -> vm.addComment(activePostId, body) },
            onDismiss = { vm.openComments(null) },
        )
    }

    var resumedOnce by rememberSaveable { mutableStateOf(false) }
    LifecycleResumeEffect(Unit) {
        if (resumedOnce) vm.refresh() else resumedOnce = true
        onPauseOrDispose {}
    }
}

@Composable
private fun TodayHomeContent(
    t: TodayData,
    home: HomeScreenState,
    vm: TodayViewModel,
    onStartRun: (Int?) -> Unit,
    onStartWorkoutPlan: (WorkoutPlan) -> Unit,
    onChallenge: (Int) -> Unit,
    onOpen: (String) -> Unit,
    baseUrl: String,
) {
    LazyColumn(
        modifier = Modifier.softEdges(),
        contentPadding = PaddingValues(20.dp, 24.dp, 20.dp, 36.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        item { HomeHeader(t) }
        if (t.needsLocationConsent) item { ConsentBanner(vm::grantLocationConsent) }

        // 1. The one focal thing on the screen, and the only orange action.
        item { QuestCard(t.today, onStart = { onStartRun(null) }) }
        item { WeekStrip(t.week) }

        // 2. Streak Start & Camera-Verified Workout Customizer (e.g. Push-ups — 10 × 3)
        item {
            StreakStartWorkoutCard(
                streakWeeks = t.streakWeeks,
                plan = home.workoutPlan,
                onCustomize = { vm.openWorkoutCustomizer(true) },
                onStartWorkout = { onStartWorkoutPlan(home.workoutPlan) },
            )
        }
        item { Shortcuts(t.tomorrow.title, onOpen) }

        // 3. Suggested Global Challenges: Circular-Floating Card Deck
        if (home.suggestedChallenges.isNotEmpty()) {
            item {
                SuggestedChallengesCircularDeck(
                    challenges = home.suggestedChallenges,
                    joiningId = home.joiningChallengeId,
                    onJoin = vm::joinSuggestedChallenge,
                    onStartJoined = { id -> onStartRun(id) },
                    onOpenDetail = onChallenge,
                )
            }
        }
        t.starterChallenge?.let { c -> item { StarterChallengeCard(c, onChallenge) } }

        // 4. Suggested Osirians Carousel (Follow, 'x' dismiss, "See All" trending)
        item {
            SuggestedOsiriansSection(
                osirians = home.suggestedOsirians,
                onFollowToggle = { person ->
                    if (person.following) vm.unfollowOsirian(person.userId) else vm.followOsirian(person.userId)
                },
                onDismiss = vm::dismissOsirian,
                onSeeAll = { vm.openTrendingOsirians(true) },
            )
        }

        // 5. People's Posts Header + Feed
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("People's Posts", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "Workouts, claimed domains, streaks & Mana Crystal rewards",
                        style = MaterialTheme.typography.bodySmall,
                        color = OsirisColors.Faint,
                    )
                }
                RaisedButton(
                    onClick = { vm.openPostComposer(true) },
                    modifier = Modifier.height(38.dp),
                ) {
                    Icon(Icons.Filled.Add, null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Post", fontSize = 13.sp)
                }
            }
        }

        if (home.feedPosts.isEmpty()) {
            item {
                FrostCard(contentPadding = 18.dp) {
                    Text(
                        "No posts yet. Complete a workout or tap + Post to share your streak, claimed domain, or crystal earnings!",
                        style = MaterialTheme.typography.bodyMedium,
                        color = OsirisColors.Muted,
                    )
                }
            }
        } else {
            items(home.feedPosts, key = { it.id }) { post ->
                PostCard(
                    post = post,
                    onReact = { reaction -> vm.reactToPost(post.id, reaction) },
                    onOpenComments = { vm.openComments(post.id) },
                    onShare = { vm.sharePost(post.id) },
                    media = if (post.hasMedia) {
                        { PostMedia(post, baseUrl) }
                    } else {
                        null
                    },
                )
            }
        }

        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.HealthAndSafety, null, Modifier.size(18.dp), tint = OsirisColors.Faint)
                Spacer(Modifier.width(8.dp))
                Text(t.safetyNote, color = OsirisColors.Faint, fontSize = 12.sp)
            }
            Text(
                t.tagline,
                color = OsirisColors.Faint,
                fontSize = 12.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )
        }
    }
}

/** Who you are and how far you have come: the name large, the streak as the one spark of orange beside it. */
@Composable
private fun HomeHeader(t: TodayData) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text("Hi ${t.displayName}", style = MaterialTheme.typography.headlineMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                "${t.performanceRank} ${t.identity}  ·  ${t.xp} XP",
                style = MaterialTheme.typography.bodySmall,
                color = OsirisColors.Muted,
            )
        }
        if (t.streakWeeks > 0) {
            Row(
                Modifier
                    .padding(start = 12.dp)
                    .well(RoundedCornerShape(FrostMatte.Radius.PILL.dp), LocalLight.current)
                    .padding(start = 10.dp, end = 14.dp, top = 8.dp, bottom = 8.dp)
                    .semantics(mergeDescendants = true) {},
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Filled.LocalFireDepartment, null, tint = OsirisColors.Energy, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(4.dp))
                Text("${t.streakWeeks}-week streak", style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}

/**
 * Circular-Floating Card Deck for Global Challenges joinable from anywhere.
 * Each card displays the challenge name, a 1-line description, and the Join Challenge button.
 */
@Composable
private fun SuggestedChallengesCircularDeck(
    challenges: List<SuggestedChallenge>,
    joiningId: Int?,
    onJoin: (Int) -> Unit,
    onStartJoined: (Int) -> Unit,
    onOpenDetail: (Int) -> Unit,
) {
    val count = challenges.size.coerceAtLeast(1)
    val virtualCount = if (count > 1) count * 200 else 1
    val startPage = if (count > 1) (virtualCount / 2) - ((virtualCount / 2) % count) else 0
    val pagerState = rememberPagerState(initialPage = startPage, pageCount = { virtualCount })

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Public, null, tint = OsirisColors.Secondary, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text("Suggested Challenges", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            Text(
                "Global Deck",
                style = MaterialTheme.typography.labelSmall,
                color = OsirisColors.Secondary,
            )
        }
        HorizontalPager(
            state = pagerState,
            modifier = Modifier.bleed(20.dp),
            contentPadding = PaddingValues(horizontal = 38.dp, vertical = 16.dp),
            pageSpacing = 12.dp,
        ) { page ->
            val challenge = challenges[page % count]
            val pageOffset = ((pagerState.currentPage - page) + pagerState.currentPageOffsetFraction).absoluteValue
            val scale = 1f - (pageOffset.coerceIn(0f, 1f) * 0.08f)
            val rotationZ = ((pagerState.currentPage - page) + pagerState.currentPageOffsetFraction).coerceIn(-1f, 1f) * -2.5f

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .graphicsLayer {
                        scaleX = scale
                        scaleY = scale
                        this.rotationZ = rotationZ
                    },
            ) {
                FrostCard(
                    onClick = { onOpenDetail(challenge.id) },
                    radius = FrostMatte.Radius.LARGE,
                    contentPadding = 18.dp,
                    fill = OsirisColors.Primary.copy(alpha = 0.14f),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(10.dp))
                                .background(OsirisColors.Secondary.copy(alpha = 0.18f))
                                .padding(horizontal = 8.dp, vertical = 4.dp),
                        ) {
                            Text(
                                "GLOBAL · ${challenge.distanceLabel}",
                                style = MaterialTheme.typography.labelSmall,
                                color = OsirisColors.Secondary,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                        Spacer(Modifier.weight(1f))
                        Text(
                            "+${challenge.winXp} XP · ${challenge.participants} Osirians",
                            style = MaterialTheme.typography.labelSmall,
                            color = OsirisColors.Muted,
                        )
                    }
                    Spacer(Modifier.height(10.dp))
                    Text(
                        challenge.title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        challenge.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = OsirisColors.Muted,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(14.dp))
                    if (challenge.joined) {
                        RaisedButton(
                            onClick = { onStartJoined(challenge.id) },
                            modifier = Modifier.fillMaxWidth().height(42.dp),
                        ) {
                            Icon(Icons.Filled.CheckCircle, null, tint = OsirisColors.Success, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Joined · Start Challenge")
                        }
                    } else {
                        KeyButton(
                            onClick = { onJoin(challenge.id) },
                            enabled = joiningId != challenge.id,
                            modifier = Modifier.fillMaxWidth().height(42.dp),
                        ) {
                            Text(if (joiningId == challenge.id) "Joining…" else "Join Challenge")
                        }
                    }
                }
            }
        }
    }
}

/**
 * Streak Start card with one-tap access to the Workout Customizer (`Push-ups — 10 × 3`, etc.)
 * and on-device ML pose verification.
 */
@Composable
private fun StreakStartWorkoutCard(
    streakWeeks: Int,
    plan: WorkoutPlan,
    onCustomize: () -> Unit,
    onStartWorkout: () -> Unit,
) {
    FrostCard(radius = FrostMatte.Radius.LARGE, contentPadding = 18.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconOrb(Icons.Filled.LocalFireDepartment, size = 40.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    if (streakWeeks > 0) "Streak Start · ${streakWeeks}w Active Streak" else "Streak Start Workout",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    plan.badgeLabel,
                    style = MaterialTheme.typography.labelSmall,
                    color = OsirisColors.Secondary,
                )
            }
            RaisedButton(
                onClick = onCustomize,
                modifier = Modifier.height(36.dp),
            ) {
                Icon(Icons.Filled.Tune, null, modifier = Modifier.size(15.dp))
                Spacer(Modifier.width(5.dp))
                Text("Customize", fontSize = 12.sp)
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .well(RoundedCornerShape(FrostMatte.Radius.MEDIUM.dp), LocalLight.current)
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                if (plan.option.isCameraExercise) exerciseIcon(plan.optionKey) else Icons.Outlined.Route,
                null,
                tint = OsirisColors.Secondary,
                modifier = Modifier.size(22.dp),
            )
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(plan.measureLabel, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(
                    if (plan.option.isCameraExercise) {
                        "Local on-device AI pose estimation counts reps & form in real time"
                    } else {
                        "GPS-verified outdoor route & territory tracking"
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = OsirisColors.Muted,
                    fontSize = 11.sp,
                )
            }
        }
        Spacer(Modifier.height(12.dp))
        KeyButton(
            onClick = onStartWorkout,
            modifier = Modifier.fillMaxWidth().height(48.dp),
        ) {
            Icon(
                if (plan.option.isCameraExercise) Icons.Outlined.Videocam else Icons.Filled.PlayArrow,
                null,
                modifier = Modifier.size(18.dp),
            )
            Spacer(Modifier.width(8.dp))
            Text("Start ${plan.measureLabel}")
        }
    }
}

@Composable
private fun WorkoutCustomizerSheet(
    plan: WorkoutPlan,
    onSelectOption: (String) -> Unit,
    onSetReps: (Int) -> Unit,
    onSetSets: (Int) -> Unit,
    onSetHoldSeconds: (Int) -> Unit,
    onSetDistanceKm: (Double) -> Unit,
    onStart: () -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 12.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text("Customize Streak Workout", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(
                "Pick GPS Run/Walk/Domain Claim or any of 16 camera-verified bodyweight exercises.",
                style = MaterialTheme.typography.bodySmall,
                color = OsirisColors.Muted,
            )

            Text("1. Select Exercise / Activity", style = MaterialTheme.typography.titleSmall, color = OsirisColors.Secondary)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(WorkoutPlan.WORKOUT_OPTIONS, key = { it.key }) { opt ->
                    FilterChip(
                        selected = plan.optionKey == opt.key,
                        onClick = { onSelectOption(opt.key) },
                        label = { Text("${opt.name} (${opt.category})") },
                    )
                }
            }

            Text("2. Customize Measure", style = MaterialTheme.typography.titleSmall, color = OsirisColors.Secondary)
            if (!plan.option.isCameraExercise) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    RaisedButton(onClick = { onSetDistanceKm(plan.targetDistanceKm - 0.5) }) { Text("- 0.5 km") }
                    Text(
                        "${Format.fixed(plan.targetDistanceKm, 1)} km",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    RaisedButton(onClick = { onSetDistanceKm(plan.targetDistanceKm + 0.5) }) { Text("+ 0.5 km") }
                }
            } else if (plan.option.isHold) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    RaisedButton(onClick = { onSetHoldSeconds(plan.holdSecondsPerSet - 15) }) { Text("-15s") }
                    Text("${plan.holdSecondsPerSet}s hold", fontWeight = FontWeight.Bold)
                    RaisedButton(onClick = { onSetHoldSeconds(plan.holdSecondsPerSet + 15) }) { Text("+15s") }
                    Spacer(Modifier.width(8.dp))
                    RaisedButton(onClick = { onSetSets(plan.sets - 1) }) { Text("- Set") }
                    Text("× ${plan.sets} sets", fontWeight = FontWeight.Bold)
                    RaisedButton(onClick = { onSetSets(plan.sets + 1) }) { Text("+ Set") }
                }
            } else {
                val presets = listOf(10 to 3, 12 to 3, 15 to 3, 15 to 4, 20 to 4, 25 to 5)
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(presets, key = { "${it.first}x${it.second}" }) { (r, s) ->
                        FilterChip(
                            selected = plan.repsPerSet == r && plan.sets == s,
                            onClick = {
                                onSetReps(r)
                                onSetSets(s)
                            },
                            label = { Text("$r × $s") },
                        )
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    RaisedButton(onClick = { onSetReps(plan.repsPerSet - 1) }) { Text("- Rep") }
                    Text("${plan.repsPerSet} reps", fontWeight = FontWeight.Bold)
                    RaisedButton(onClick = { onSetReps(plan.repsPerSet + 1) }) { Text("+ Rep") }
                    Spacer(Modifier.width(6.dp))
                    RaisedButton(onClick = { onSetSets(plan.sets - 1) }) { Text("- Set") }
                    Text("× ${plan.sets} sets", fontWeight = FontWeight.Bold)
                    RaisedButton(onClick = { onSetSets(plan.sets + 1) }) { Text("+ Set") }
                }
            }

            FrostCard(contentPadding = 14.dp, fill = OsirisColors.Primary.copy(alpha = 0.14f)) {
                Text("Selected Plan: ${plan.measureLabel}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                val orientation = if (plan.option.cameraOrientation == "front") "Face the camera" else "Side-on to the camera"
                Text(
                    if (plan.option.isCameraExercise) {
                        "Camera position: $orientation · GPU/NNAPI Pose Engine"
                    } else {
                        "Outdoor GPS verification"
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = OsirisColors.Muted,
                )
            }

            KeyButton(
                onClick = onStart,
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                Text("Start ${plan.measureLabel}")
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

/** The screen's focal point: today's quest distance inside its progress ring, over the one orange action. */
@Composable
private fun QuestCard(quest: Quest, onStart: () -> Unit) {
    FrostCard(radius = FrostMatte.Radius.LARGE, contentPadding = 20.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                quest.heading,
                style = MaterialTheme.typography.labelMedium,
                color = OsirisColors.Muted,
                modifier = Modifier.weight(1f),
            )
            Text("+${quest.xp} XP", style = MaterialTheme.typography.labelMedium, color = OsirisColors.Primary)
        }
        EnergyRing(quest.fraction.toFloat(), Modifier.fillMaxWidth(0.74f).align(Alignment.CenterHorizontally)) {
            Column(Modifier.padding(horizontal = 36.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                // Shrinks to fit the ring, for long distances and large system text.
                BasicText(
                    Format.fixed(quest.progressM / 1000, 2),
                    style = MaterialTheme.typography.displayLarge.copy(color = OsirisColors.White),
                    maxLines = 1,
                    autoSize = TextAutoSize.StepBased(minFontSize = 28.sp, maxFontSize = 72.sp),
                )
                Text("/ ${Format.km(quest.targetM.toDouble())}", style = MaterialTheme.typography.titleSmall, color = OsirisColors.Muted)
            }
        }
        Text(
            quest.title,
            style = MaterialTheme.typography.titleLarge,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(4.dp))
        Text(
            quest.description,
            style = MaterialTheme.typography.bodyMedium,
            color = OsirisColors.Muted,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(16.dp))
        if (quest.completed) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.CheckCircle, null, tint = OsirisColors.Success)
                Spacer(Modifier.width(8.dp))
                Text(if (quest.rewarded) "Done. +${quest.xp} XP earned." else "Done!", Modifier.weight(1f))
                TextButton(onClick = onStart) { Text("Go again") }
            }
        } else {
            KeyButton(onClick = onStart, energy = true, modifier = Modifier.fillMaxWidth().height(56.dp)) {
                Icon(Icons.Filled.PlayArrow, null)
                Spacer(Modifier.width(6.dp))
                Text(if (quest.optional) "Start (optional)" else "Start")
            }
        }
    }
}

/** The week as beads in a groove: one inflated bead per active day, an empty socket for the rest. */
@Composable
private fun WeekStrip(week: WeeklyGoal) {
    val summary = if (week.completed) {
        "Weekly goal met. Rest days never break your streak."
    } else {
        "${week.activeDays} of ${week.activeDaysTarget} active days this week, ${Format.km(week.distanceM)}"
    }
    Row(
        Modifier
            .fillMaxWidth()
            .well(RoundedCornerShape(FrostMatte.Radius.PILL.dp), LocalLight.current)
            .padding(horizontal = 14.dp, vertical = 12.dp)
            .semantics(mergeDescendants = true) { contentDescription = summary },
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(week.activeDaysTarget) { i ->
            val day = Modifier.size(22.dp)
            if (i < week.activeDays) {
                Spacer(day.accentKey(CircleShape))
            } else {
                Spacer(day.border(1.5.dp, OsirisColors.Faint.copy(alpha = 0.5f), CircleShape))
            }
        }
        Text(
            "${week.activeDays} of ${week.activeDaysTarget} days",
            style = MaterialTheme.typography.titleSmall,
            color = OsirisColors.Muted,
            textAlign = TextAlign.End,
            maxLines = 1,
            modifier = Modifier.weight(1f),
        )
    }
}

/** Asymmetric block: tomorrow's quest tall on the left, two shortcuts stacked right, two pills below. */
@Composable
private fun Shortcuts(tomorrow: String, onOpen: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.height(188.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            FrostCard(Modifier.weight(1.15f).fillMaxHeight(), radius = FrostMatte.Radius.LARGE) {
                Text("Tomorrow", style = MaterialTheme.typography.labelMedium, color = OsirisColors.Muted)
                Spacer(Modifier.weight(1f))
                IconOrb(Icons.Outlined.WbTwilight, size = 40.dp)
                Spacer(Modifier.height(10.dp))
                Text(tomorrow, style = MaterialTheme.typography.headlineSmall)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Shortcut(Icons.Outlined.Groups, "Clubs", Modifier.weight(1f)) { onOpen(Routes.COMMUNITIES) }
                Shortcut(Icons.Filled.FitnessCenter, "Bodyweight", Modifier.weight(1f)) { onOpen(Routes.EXERCISE) }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Pill(Icons.Outlined.Route, "My courses") { onOpen(Routes.COURSES) }
            Pill(Icons.Outlined.PersonAddAlt, "Invite a friend") { onOpen(Routes.SETTINGS) }
        }
    }
}

@Composable
private fun Shortcut(icon: ImageVector, label: String, modifier: Modifier, onClick: () -> Unit) {
    FrostCard(modifier.fillMaxWidth(), onClick = onClick, contentPadding = 16.dp) {
        Spacer(Modifier.weight(1f))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            IconOrb(icon, size = 36.dp)
        }
    }
}

/** Secondary destinations as outlined pills: an interactive border, no fill to compete with the cards. */
@Composable
private fun Pill(icon: ImageVector, label: String, onClick: () -> Unit) {
    RaisedButton(
        onClick = onClick,
        modifier = Modifier.height(44.dp),
    ) {
        Icon(icon, null, Modifier.size(18.dp))
        Spacer(Modifier.width(8.dp))
        Text(label, style = MaterialTheme.typography.titleSmall)
    }
}

@Composable
private fun ConsentBanner(onAllow: () -> Unit) {
    FrostCard(contentPadding = 0.dp, fill = OsirisColors.Secondary.copy(alpha = 0.15f)) {
        ListItem(
            leadingContent = { Icon(Icons.Outlined.LocationOn, null) },
            headlineContent = { Text("Allow location during runs") },
            supportingContent = { Text("Needed to verify your distance. Your route is never shown to others.") },
            trailingContent = { TextButton(onClick = onAllow) { Text("Allow") } },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        )
    }
}

@Composable
private fun StarterChallengeCard(c: StarterChallenge, onOpen: (Int) -> Unit) {
    val away = c.distanceKm?.let { "  •  about ${Format.fixed(it, 1)} km away" }.orEmpty()
    FrostCard(onClick = { onOpen(c.id) }, contentPadding = 0.dp) {
        ListItem(
            leadingContent = { Icon(Icons.Outlined.Flag, null, tint = OsirisColors.Primary) },
            headlineContent = { Text(c.title) },
            supportingContent = { Text("${Format.fixed(c.courseDistanceM / 1000, 1)} km course$away  •  free") },
            trailingContent = { Icon(Icons.Filled.ChevronRight, null) },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        )
    }
}
