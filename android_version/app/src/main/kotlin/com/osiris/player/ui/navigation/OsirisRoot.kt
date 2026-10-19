package com.osiris.player.ui.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.osiris.player.ui.challenge.ChallengeBoardScreen
import com.osiris.player.ui.challenge.ChallengeDetailScreen
import com.osiris.player.ui.challenge.CoursesScreen
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.community.CommunitiesScreen
import com.osiris.player.ui.community.CommunityDetailScreen
import com.osiris.player.ui.community.RankingsScreen
import com.osiris.player.ui.exercise.ExerciseCameraScreen
import com.osiris.player.ui.exercise.ExerciseHubScreen
import com.osiris.player.ui.progress.ProgressScreen
import com.osiris.player.ui.run.RunScreen
import com.osiris.player.ui.session.LoginScreen
import com.osiris.player.ui.session.OnboardingScreen
import com.osiris.player.ui.settings.SettingsScreen
import com.osiris.player.ui.today.TodayScreen
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.presentation.AppGraph

/** Route names. Arguments are path segments or optional query parameters. */
object Routes {
    const val LOGIN = "login"
    const val ONBOARD = "onboard"
    const val TODAY = "today"
    const val RUN = "run?challengeId={challengeId}"
    const val CHALLENGES = "challenges"
    const val CHALLENGE = "challenge/{id}"
    const val COURSES = "courses"
    const val COMMUNITIES = "communities"
    const val COMMUNITY = "community/{slug}"
    const val RANKINGS = "rankings"
    const val PROGRESS = "progress"
    const val SETTINGS = "settings"
    const val EXERCISE = "exercise"
    const val EXERCISE_CAMERA = "exercise/{key}"

    fun run(challengeId: Int? = null) = if (challengeId == null) "run" else "run?challengeId=$challengeId"
    fun challenge(id: Int) = "challenge/$id"
    fun community(slug: String) = "community/${android.net.Uri.encode(slug)}"
    fun exerciseCamera(key: String) = "exercise/$key"
}

/** Restores the session, then shows sign-in or the player's app. */
@Composable
fun OsirisRoot(graph: AppGraph) {
    val session = rememberShared { graph.session() }
    val state by session.state.collectAsStateWithLifecycle()
    when (state) {
        AuthState.Restoring -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        AuthState.SignedOut -> SignedOutNav(graph)
        is AuthState.SignedIn -> SignedInNav(graph)
    }
}

@Composable
private fun SignedOutNav(graph: AppGraph) {
    val nav = rememberNavController()
    NavHost(nav, startDestination = Routes.LOGIN) {
        composable(Routes.LOGIN) { LoginScreen(graph, onCreateAccount = { nav.navigate(Routes.ONBOARD) }) }
        composable(Routes.ONBOARD) { OnboardingScreen(graph, onBack = { nav.popBackStack() }) }
    }
}

@Composable
private fun SignedInNav(graph: AppGraph) {
    val nav = rememberNavController()
    NavHost(nav, startDestination = Routes.TODAY) {
        composable(Routes.TODAY) { TodayScreen(graph, nav) }
        composable(
            Routes.RUN,
            arguments = listOf(navArgument("challengeId") { type = NavType.IntType; defaultValue = -1 }),
        ) { entry ->
            val id = entry.arguments?.getInt("challengeId")?.takeIf { it >= 0 }
            RunScreen(graph, challengeId = id, onBack = nav::popBackStack, onOpenChallenge = { nav.navigate(Routes.challenge(it)) })
        }
        composable(Routes.CHALLENGES) { ChallengeBoardScreen(graph, onBack = nav::popBackStack, onOpen = { nav.navigate(Routes.challenge(it)) }) }
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
        composable(Routes.RANKINGS) { RankingsScreen(graph, onBack = nav::popBackStack, onSettings = { nav.navigate(Routes.SETTINGS) }) }
        composable(Routes.PROGRESS) { ProgressScreen(graph, onBack = nav::popBackStack) }
        composable(Routes.SETTINGS) { SettingsScreen(graph, onBack = nav::popBackStack) }
        composable(Routes.EXERCISE) { ExerciseHubScreen(graph, onBack = nav::popBackStack, onOpen = { nav.navigate(Routes.exerciseCamera(it)) }) }
        composable(Routes.EXERCISE_CAMERA, arguments = listOf(navArgument("key") { type = NavType.StringType })) { entry ->
            ExerciseCameraScreen(graph, key = entry.arguments!!.getString("key")!!, onDone = nav::popBackStack)
        }
    }
}

/** Navigates to a top-level route from the home screen. */
fun NavHostController.open(route: String) = navigate(route) { launchSingleTop = true }
