package com.osiris.player.ui.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Explore
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.osiris.player.ui.challenge.ChallengeBoardScreen
import com.osiris.player.ui.challenge.ChallengeDetailScreen
import com.osiris.player.ui.challenge.CoursesScreen
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.community.CommunitiesScreen
import com.osiris.player.ui.community.CommunityDetailScreen
import com.osiris.player.ui.community.RankingsScreen
import com.osiris.player.ui.design.FrostBackground
import com.osiris.player.ui.design.FrostBar
import com.osiris.player.ui.design.FrostBarItem
import com.osiris.player.ui.discover.DiscoverScreen
import com.osiris.player.ui.exercise.ExerciseCameraScreen
import com.osiris.player.ui.exercise.ExerciseHubScreen
import com.osiris.player.ui.permission.PermissionPrimerScreen
import com.osiris.player.ui.profile.ProfileScreen
import com.osiris.player.ui.run.RunScreen
import com.osiris.player.ui.session.LoginScreen
import com.osiris.player.ui.session.OnboardingScreen
import com.osiris.player.ui.settings.SettingsScreen
import com.osiris.player.ui.social.SocialScreen
import com.osiris.player.ui.today.TodayScreen
import com.osiris.player.ui.wallet.WalletScreen
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.navigation.Destination
import com.osiris.shared.presentation.navigation.RootState
import com.osiris.shared.presentation.navigation.Tab

/** Route names. Arguments are path segments or optional query parameters. */
object Routes {
    const val LOGIN = "login"
    const val ONBOARD = "onboard"
    const val TODAY = "today"
    const val DISCOVER = "discover"
    const val SOCIAL = "social"
    const val WALLET = "wallet"
    const val PROFILE = "profile"
    const val RUN = "run?challengeId={challengeId}"
    const val CHALLENGES = "challenges"
    const val CHALLENGE = "challenge/{id}"
    const val COURSES = "courses"
    const val COMMUNITIES = "communities"
    const val COMMUNITY = "community/{slug}"
    const val RANKINGS = "rankings"
    const val SETTINGS = "settings"
    const val EXERCISE = "exercise"
    const val EXERCISE_CAMERA = "exercise/{key}"

    fun run(challengeId: Int? = null) = if (challengeId == null) "run" else "run?challengeId=$challengeId"
    fun challenge(id: Int) = "challenge/$id"
    fun community(slug: String) = "community/${android.net.Uri.encode(slug)}"
    fun exerciseCamera(key: String) = "exercise/$key"
}

/** The bar's sections and the route each one opens. Wallet shows only in builds that have one. */
private class Section(val tab: Tab, val route: String, val label: String, val icon: ImageVector)

private fun sections(hasWallet: Boolean) = listOfNotNull(
    Section(Tab.HOME, Routes.TODAY, "Home", Icons.Outlined.Home),
    Section(Tab.DISCOVER, Routes.DISCOVER, "Discover", Icons.Outlined.Explore),
    Section(Tab.SOCIAL, Routes.SOCIAL, "Social", Icons.Outlined.Groups),
    Section(Tab.WALLET, Routes.WALLET, "Wallet", Icons.Outlined.AccountBalanceWallet).takeIf { hasWallet },
    Section(Tab.PROFILE, Routes.PROFILE, "Profile", Icons.Outlined.Person),
)

/**
 * The app root, guarded by the shared navigator: permission primer on first launch, then sign-in,
 * then the tabbed app. A restored session skips straight to Home. [link] is the latest deep link
 * the OS delivered; [onLinkHandled] clears it once the navigator has taken it.
 */
@Composable
fun OsirisRoot(graph: AppGraph, link: String?, onLinkHandled: () -> Unit) {
    val navigator = rememberShared { graph.navigator() }
    val state by navigator.state.collectAsStateWithLifecycle()
    LaunchedEffect(link) {
        if (link != null) {
            navigator.open(link)
            onLinkHandled()
        }
    }
    FrostBackground {
        when (val s = state) {
            RootState.Restoring -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            RootState.PermissionPrimer -> PermissionPrimerScreen(graph)
            is RootState.SignedOut -> SignedOutNav(graph, s)
            is RootState.SignedIn -> SignedInNav(graph, s.pending, onPendingOpened = navigator::pendingOpened)
        }
    }
}

@Composable
private fun SignedOutNav(graph: AppGraph, state: RootState.SignedOut) {
    val nav = rememberNavController()
    val start = if (state.invite != null || state.referral != null) Routes.ONBOARD else Routes.LOGIN
    NavHost(nav, startDestination = start) {
        composable(Routes.LOGIN) { LoginScreen(graph, onCreateAccount = { nav.navigate(Routes.ONBOARD) }) }
        composable(Routes.ONBOARD) {
            OnboardingScreen(
                graph,
                onBack = { if (!nav.popBackStack()) nav.navigate(Routes.LOGIN) },
                inviteToken = state.invite,
                referralCode = state.referral,
            )
        }
    }
}

@Composable
private fun SignedInNav(graph: AppGraph, pending: Destination?, onPendingOpened: () -> Unit) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route
    val sections = remember(graph) { sections(graph.hasWallet) }
    LaunchedEffect(pending) {
        when (pending) {
            null -> return@LaunchedEffect
            is Destination.Section -> sections.firstOrNull { it.tab == pending.tab }?.let { nav.selectTab(it.route) }
            is Destination.Challenge -> nav.open(Routes.challenge(pending.id))
            is Destination.Community -> nav.open(Routes.community(pending.slug))
            // A signed-in player already has an account; the invite's challenge is on Discover.
            is Destination.Invite, is Destination.Referral -> nav.selectTab(Routes.DISCOVER)
        }
        onPendingOpened()
    }
    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f)) { SignedInGraph(graph, nav) }
        if (sections.any { it.route == route }) {
            FrostBar(
                sections.map { s -> FrostBarItem(s.label, s.icon, selected = s.route == route, onClick = { nav.selectTab(s.route) }) },
                Modifier.navigationBarsPadding(),
            )
        }
    }
}

@Composable
private fun SignedInGraph(graph: AppGraph, nav: NavHostController) {
    NavHost(nav, startDestination = Routes.TODAY) {
        composable(Routes.TODAY) { TodayScreen(graph, nav) }
        composable(
            Routes.RUN,
            arguments = listOf(navArgument("challengeId") { type = NavType.IntType; defaultValue = -1 }),
        ) { entry ->
            val id = entry.arguments?.getInt("challengeId")?.takeIf { it >= 0 }
            RunScreen(graph, challengeId = id, onBack = nav::popBackStack, onOpenChallenge = { nav.navigate(Routes.challenge(it)) })
        }
        composable(Routes.DISCOVER) {
            DiscoverScreen(
                graph,
                onOpen = { nav.navigate(Routes.challenge(it)) },
                onCreate = { nav.open(Routes.COURSES) },
                onNearby = { nav.open(Routes.CHALLENGES) },
            )
        }
        composable(Routes.CHALLENGES) {
            ChallengeBoardScreen(graph, onBack = nav::popBackStack, onOpen = { nav.navigate(Routes.challenge(it)) })
        }
        composable(Routes.CHALLENGE, arguments = listOf(navArgument("id") { type = NavType.IntType })) { entry ->
            ChallengeDetailScreen(
                graph,
                id = entry.arguments!!.getInt("id"),
                onBack = nav::popBackStack,
                onRun = { nav.navigate(Routes.run(it)) },
            )
        }
        composable(Routes.COURSES) { CoursesScreen(graph, onBack = nav::popBackStack, onOpenChallenge = { nav.navigate(Routes.challenge(it)) }) }
        composable(Routes.COMMUNITIES) {
            CommunitiesScreen(graph, onBack = nav::popBackStack, onOpen = { nav.navigate(Routes.community(it)) })
        }
        composable(Routes.COMMUNITY, arguments = listOf(navArgument("slug") { type = NavType.StringType })) { entry ->
            CommunityDetailScreen(
                graph,
                slug = entry.arguments!!.getString("slug")!!,
                onBack = nav::popBackStack,
                onOpenChallenge = { nav.navigate(Routes.challenge(it)) },
            )
        }
        composable(Routes.SOCIAL) {
            SocialScreen(graph, onLocal = { nav.open(Routes.RANKINGS) }, onCommunities = { nav.open(Routes.COMMUNITIES) })
        }
        composable(Routes.RANKINGS) { RankingsScreen(graph, onBack = nav::popBackStack, onSettings = { nav.open(Routes.SETTINGS) }) }
        if (graph.hasWallet) composable(Routes.WALLET) { WalletScreen(graph) }
        composable(Routes.PROFILE) {
            ProfileScreen(graph, actions = {
                IconButton(onClick = { nav.open(Routes.SETTINGS) }) { Icon(Icons.Outlined.Settings, "Settings") }
            })
        }
        composable(Routes.SETTINGS) { SettingsScreen(graph, onBack = nav::popBackStack) }
        composable(Routes.EXERCISE) { ExerciseHubScreen(graph, onBack = nav::popBackStack, onOpen = { nav.navigate(Routes.exerciseCamera(it)) }) }
        composable(Routes.EXERCISE_CAMERA, arguments = listOf(navArgument("key") { type = NavType.StringType })) { entry ->
            ExerciseCameraScreen(graph, key = entry.arguments!!.getString("key")!!, onDone = nav::popBackStack)
        }
    }
}

/** Navigates to a top-level route from the home screen. */
fun NavHostController.open(route: String) = navigate(route) { launchSingleTop = true }

/** Switches tab, keeping one back stack entry per tab and restoring its state. */
private fun NavHostController.selectTab(route: String) = navigate(route) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
