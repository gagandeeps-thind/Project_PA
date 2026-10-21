package com.osiris.shared.presentation.navigation

/** The five bottom-bar sections, in bar order. */
enum class Tab(val path: String) {
    HOME("home"),
    DISCOVER("discover"),
    SOCIAL("social"),
    WALLET("wallet"),
    PROFILE("profile"),
}

/** Where a link or a tap can take the player. */
sealed interface Destination {
    data class Section(val tab: Tab) : Destination
    data class Challenge(val id: Int) : Destination
    data class Community(val slug: String) : Destination

    /** A friend's challenge invite. Signed out, it opens account creation with the invite attached. */
    data class Invite(val token: String) : Destination

    /** A referral link. Only meaningful before an account exists. */
    data class Referral(val code: String) : Destination
}

/**
 * Turns `osiris://…` links and `https://<webLinkHost>/…` links into destinations. The https
 * paths are the ones the backend's public pages use (`/i/<invite>`, `/join/<code>`). Anything
 * else, including https links to other hosts, is rejected so a crafted link cannot steer the app.
 */
class DeepLinkParser(private val webLinkHost: String) {
    fun parse(link: String): Destination? {
        val trimmed = link.trim()
        val segments: List<String>? = when {
            trimmed.startsWith(APP_SCHEME) -> pathSegments(trimmed.removePrefix(APP_SCHEME))
            trimmed.startsWith(HTTPS) -> webSegments(trimmed.removePrefix(HTTPS))
            else -> null
        }
        return segments?.let(::destination)
    }

    private fun webSegments(rest: String): List<String>? {
        val host = rest.substringBefore('/').substringBefore('?').substringBefore('#').lowercase()
        if (webLinkHost.isEmpty() || host != webLinkHost.lowercase()) return null
        val segments = pathSegments(rest.substringAfter('/', ""))
        return when (segments.firstOrNull()) {
            "i" -> listOf("invite") + segments.drop(1)
            "join" -> segments
            else -> null
        }
    }

    private fun destination(segments: List<String>): Destination? {
        val head = segments.firstOrNull() ?: return null
        val arg = segments.getOrNull(1)?.takeIf { it.isNotEmpty() && segments.size == 2 }
        return when (head) {
            "challenge" -> arg?.toIntOrNull()?.takeIf { it > 0 }?.let(Destination::Challenge)
            "community" -> arg?.takeIf(::isSafeToken)?.let(Destination::Community)
            "invite" -> arg?.takeIf(::isSafeToken)?.let(Destination::Invite)
            "join" -> arg?.takeIf(::isSafeToken)?.let(Destination::Referral)
            else -> Tab.entries.firstOrNull { it.path == head && segments.size == 1 }?.let(Destination::Section)
        }
    }

    private fun pathSegments(path: String): List<String> =
        path.substringBefore('?').substringBefore('#').split('/').filter { it.isNotEmpty() }

    private fun isSafeToken(value: String) = value.length <= MAX_TOKEN && value.all { it.isLetterOrDigit() || it == '-' || it == '_' }

    private companion object {
        const val APP_SCHEME = "osiris://"
        const val HTTPS = "https://"
        const val MAX_TOKEN = 128
    }
}
