package com.osiris.player.ui.navigation

import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.osiris.player.ui.social.ChatScreen
import com.osiris.player.ui.social.ComposePostScreen
import com.osiris.player.ui.social.DiscoverNav
import com.osiris.player.ui.social.GlobalBoardsScreen
import com.osiris.player.ui.social.InboxScreen
import com.osiris.player.ui.social.SocialDiscoverScreen
import com.osiris.player.ui.social.SocialNav
import com.osiris.player.ui.social.SocialProfileScreen
import com.osiris.player.ui.social.SocialScreen
import com.osiris.player.ui.social.SocialSearchScreen
import com.osiris.shared.presentation.AppGraph

/** Social tab routes. */
object SocialRoutes {
    const val COMPOSE = "social/compose"
    const val DISCOVER = "social/discover"
    const val SEARCH = "social/search"
    const val INBOX = "social/inbox"
    const val CHAT = "social/chat/{id}"
    const val USER = "social/user/{id}"
    const val BOARDS = "social/boards"

    fun chat(userId: Int) = "social/chat/$userId"
    fun user(userId: Int) = "social/user/$userId"
}

/** The Social tab and everything it opens: composer, Discover, search, messages and profiles. */
fun NavGraphBuilder.socialGraph(graph: AppGraph, nav: NavHostController) {
    val idArg = listOf(navArgument("id") { type = NavType.IntType })
    composable(Routes.SOCIAL) {
        SocialScreen(
            graph,
            SocialNav(
                onCompose = { nav.open(SocialRoutes.COMPOSE) },
                onDiscover = { nav.open(SocialRoutes.DISCOVER) },
                onSearch = { nav.open(SocialRoutes.SEARCH) },
                onMessages = { nav.open(SocialRoutes.INBOX) },
                onProfile = { nav.navigate(SocialRoutes.user(it)) },
            ),
        )
    }
    composable(SocialRoutes.COMPOSE) { ComposePostScreen(graph, onDone = nav::popBackStack) }
    composable(SocialRoutes.DISCOVER) {
        SocialDiscoverScreen(
            graph,
            DiscoverNav(
                onBack = nav::popBackStack,
                onProfile = { nav.navigate(SocialRoutes.user(it)) },
                onLeaderboards = { nav.open(SocialRoutes.BOARDS) },
                onCommunities = { nav.open(Routes.COMMUNITIES) },
            ),
        )
    }
    composable(SocialRoutes.SEARCH) {
        SocialSearchScreen(graph, onBack = nav::popBackStack, onProfile = { nav.navigate(SocialRoutes.user(it)) })
    }
    composable(SocialRoutes.INBOX) {
        InboxScreen(graph, onBack = nav::popBackStack, onChat = { nav.navigate(SocialRoutes.chat(it)) })
    }
    composable(SocialRoutes.CHAT, arguments = idArg) { entry ->
        val id = entry.arguments!!.getInt("id")
        ChatScreen(graph, id, onBack = nav::popBackStack, onProfile = { nav.navigate(SocialRoutes.user(it)) })
    }
    composable(SocialRoutes.USER, arguments = idArg) { entry ->
        val id = entry.arguments!!.getInt("id")
        SocialProfileScreen(
            graph,
            id,
            onBack = nav::popBackStack,
            onMessage = { nav.navigate(SocialRoutes.chat(it)) },
            onCompose = { nav.open(SocialRoutes.COMPOSE) },
        )
    }
    composable(SocialRoutes.BOARDS) {
        GlobalBoardsScreen(
            graph,
            onBack = nav::popBackStack,
            onLocal = { nav.open(Routes.RANKINGS) },
            onCommunities = { nav.open(Routes.COMMUNITIES) },
        )
    }
}
