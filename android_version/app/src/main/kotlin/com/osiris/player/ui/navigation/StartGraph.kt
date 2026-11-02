package com.osiris.player.ui.navigation

import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.osiris.player.ui.start.CameraSet
import com.osiris.player.ui.start.StartCard
import com.osiris.player.ui.start.StartScreen
import com.osiris.player.ui.start.TrainingPage
import com.osiris.player.ui.training.GroupChallengeDetailScreen
import com.osiris.player.ui.training.GroupChallengesScreen
import com.osiris.player.ui.training.LiveSessionScreen
import com.osiris.shared.domain.model.StartMode
import com.osiris.shared.presentation.AppGraph
import kotlin.time.Instant

private const val CAMERA_SET_PARTS = 3

private fun modeOf(wire: String?) = StartMode.entries.firstOrNull { it.wire == wire } ?: StartMode.TRAIN

/** "pushup|<set id>|<started at>" as the camera route saves it, back into a [CameraSet]. */
private fun cameraSetOf(raw: String?): CameraSet? {
    val parts = raw?.split("|")?.takeIf { it.size == CAMERA_SET_PARTS } ?: return null
    return runCatching { CameraSet(parts[0], parts[1], Instant.parse(parts[2])) }.getOrNull()
}

/** The Start tab and everything it opens: Train and Challenge, live sessions, group challenges. */
fun NavGraphBuilder.startGraph(graph: AppGraph, nav: NavHostController) {
    composable(Routes.START) {
        StartScreen(
            onOpen = { card ->
                when (card) {
                    StartCard.TRAIN -> nav.open(Routes.training(StartMode.TRAIN))
                    StartCard.CHALLENGE -> nav.open(Routes.training(StartMode.CHALLENGE))
                    StartCard.CAMERA -> nav.open(Routes.EXERCISE)
                    StartCard.COURSES -> nav.open(Routes.COURSES)
                }
            },
            onWallet = { nav.open(Routes.WALLET) },
        )
    }
    composable(Routes.TRAINING, arguments = listOf(navArgument("mode") { type = NavType.StringType })) { entry ->
        val mode = modeOf(entry.arguments?.getString("mode"))
        val handle = entry.savedStateHandle
        val cameraSet by handle.getStateFlow<String?>(Routes.CAMERA_SET, null).collectAsStateWithLifecycle()
        TrainingPage(
            graph,
            mode,
            onBack = nav::popBackStack,
            onLive = { nav.navigate(Routes.live(mode, it.key)) },
            onCamera = { nav.navigate(Routes.exerciseCamera(it.key, start = mode)) },
            onChallenge = { nav.navigate(Routes.challenge(it)) },
            onGroups = { nav.navigate(Routes.GROUPS) },
            onGroup = { nav.navigate(Routes.group(it)) },
            cameraSet = cameraSetOf(cameraSet),
            onCameraSetHandled = { handle[Routes.CAMERA_SET] = null },
        )
    }
    composable(
        Routes.LIVE,
        arguments = listOf(navArgument("mode") { type = NavType.StringType }, navArgument("activity") { type = NavType.StringType }),
    ) { entry ->
        LiveSessionScreen(
            graph,
            activityKey = entry.arguments!!.getString("activity")!!,
            mode = modeOf(entry.arguments?.getString("mode")),
            onDone = nav::popBackStack,
        )
    }
    composable(Routes.GROUPS) {
        GroupChallengesScreen(graph, onBack = nav::popBackStack, onOpen = { nav.navigate(Routes.group(it)) })
    }
    composable(Routes.GROUP, arguments = listOf(navArgument("id") { type = NavType.IntType })) { entry ->
        GroupChallengeDetailScreen(graph, entry.arguments!!.getInt("id"), onBack = nav::popBackStack)
    }
}
