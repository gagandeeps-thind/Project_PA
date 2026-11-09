package com.osiris.shared.presentation

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.ActiveFriend
import com.osiris.shared.domain.model.ContentReportReason
import com.osiris.shared.domain.model.DirectMessage
import com.osiris.shared.domain.model.DiscoverPage
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.Inbox
import com.osiris.shared.domain.model.MessageThread
import com.osiris.shared.domain.model.ReportKind
import com.osiris.shared.domain.model.ReportTarget
import com.osiris.shared.domain.model.SocialFeedPage
import com.osiris.shared.domain.model.SocialPostDraft
import com.osiris.shared.domain.model.SocialProfile
import com.osiris.shared.domain.model.SocialUser
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.SocialRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.UiMessage
import com.osiris.shared.presentation.social.ChatViewModel
import com.osiris.shared.presentation.social.ComposePostViewModel
import com.osiris.shared.presentation.social.ContentSafetyViewModel
import com.osiris.shared.presentation.social.InboxViewModel
import com.osiris.shared.presentation.social.SocialDiscoverViewModel
import com.osiris.shared.presentation.social.SocialFeedViewModel
import com.osiris.shared.presentation.social.SocialProfileViewModel
import com.osiris.shared.presentation.social.SocialSearchViewModel
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

private val at = Instant.parse("2026-11-05T08:00:00Z")
private fun user(id: Int, following: Boolean = false, followsMe: Boolean = false) =
    SocialUser(id, "Player $id", "h$id", following = following, followsMe = followsMe)
private fun post(id: Int, author: Int = 2) = FeedPost(id = id, userId = author, authorName = "Player $author")
private fun message(id: Int, mine: Boolean, read: Boolean = true) =
    DirectMessage(id, if (mine) 1 else 2, if (mine) 2 else 1, "m$id", at, read = read, mine = mine)

class FakeSocial : SocialRepository {
    val feedCalls = mutableListOf<Int?>()
    val discoverCalls = mutableListOf<Pair<String?, Int>>()
    val searches = mutableListOf<String>()
    val created = mutableListOf<SocialPostDraft>()
    val deleted = mutableListOf<Int>()
    val sent = mutableListOf<Pair<Int, String>>()
    val readMarks = mutableListOf<Int>()
    val threadCalls = mutableListOf<Int?>()
    var pages: Map<Int?, Outcome<SocialFeedPage>> = mapOf(
        null to ok(SocialFeedPage(listOf(ActiveFriend(2, "Player 2", minutes = 30)), listOf(post(3), post(2)), nextBeforeId = 2)),
        2 to ok(SocialFeedPage(items = listOf(post(2), post(1)))),
    )
    var discoverResult: Outcome<DiscoverPage> = ok(DiscoverPage(listOf("run"), listOf(post(10, author = 5))))
    var profileResult: Outcome<SocialProfile> =
        ok(SocialProfile(user(5, followsMe = false), followersCount = 3, posts = listOf(post(10, 5))))
    var threadResult: Outcome<MessageThread> = ok(MessageThread(user(2), true, listOf(message(1, false, read = false))))
    var olderResult: Outcome<MessageThread> = ok(MessageThread(user(2), true, emptyList()))
    var unread = 4
    val reports = mutableListOf<Pair<ReportTarget, ContentReportReason>>()
    val blocks = mutableListOf<Int>()
    var blockResult: Outcome<Unit> = ok(Unit)

    override suspend fun feed(beforeId: Int?) = pages.getValue(beforeId).also { feedCalls += beforeId }
    override suspend fun discover(activity: String?, offset: Int) = discoverResult.also { discoverCalls += activity to offset }
    override suspend fun search(query: String): Outcome<List<SocialUser>> {
        searches += query
        return ok(listOf(user(8)))
    }
    override suspend fun profile(userId: Int) = profileResult
    override suspend fun createPost(draft: SocialPostDraft): Outcome<FeedPost> {
        created += draft
        return ok(post(50, author = 1))
    }
    override suspend fun deletePost(postId: Int) = ok(Unit).also { deleted += postId }
    override suspend fun inbox() = ok(Inbox(unreadTotal = unread))
    override suspend fun thread(userId: Int, beforeId: Int?) =
        (if (beforeId == null) threadResult else olderResult).also { threadCalls += beforeId }
    override suspend fun send(userId: Int, body: String): Outcome<DirectMessage> {
        sent += userId to body
        return ok(message(99, mine = true))
    }
    override suspend fun markRead(userId: Int) = ok(Inbox()).also { readMarks += userId }
    override suspend fun report(target: ReportTarget, reason: ContentReportReason) =
        ok("Thanks. Our team will review this report.").also { reports += target to reason }
    override suspend fun block(userId: Int) = blockResult.also { blocks += userId }
}

/** A player whose reactions fail, to check optimistic kudos roll back. */
private class FailingReactions(private val base: FakePlayer = FakePlayer()) : PlayerRepository by base {
    override suspend fun reactToPost(postId: Int, reaction: String): Outcome<FeedPost> = fail(AppError.Offline())
    override suspend fun followOsirian(userId: Int) = fail(AppError.Offline())
}

class SocialViewModelsTest {
    private fun TestScope.main() = UnconfinedTestDispatcher(testScheduler)

    @Test
    fun `a report sends the chosen target and reason and confirms`() = runTest {
        val social = FakeSocial()
        val vm = ContentSafetyViewModel(social, main())
        vm.askReport(ReportKind.COMMENT, 7)
        vm.report(ContentReportReason.SPAM)
        assertEquals(listOf(ReportTarget(ReportKind.COMMENT, 7) to ContentReportReason.SPAM), social.reports)
        assertNull(vm.state.value.prompt)
        assertEquals(UiMessage.Kind.SUCCESS, vm.message.value!!.kind)
        vm.clear()
    }

    @Test
    fun `a block tells the screen once it lands and stays quiet when it fails`() = runTest {
        val social = FakeSocial()
        val vm = ContentSafetyViewModel(social, main())
        vm.askBlock(5, "Player 5")
        vm.confirmBlock()
        assertEquals(listOf(5), social.blocks)
        assertEquals(5, vm.state.value.blockedUserId)
        vm.blockHandled()
        social.blockResult = fail(AppError.Offline())
        vm.askBlock(6, "Player 6")
        vm.confirmBlock()
        assertNull(vm.state.value.blockedUserId)
        assertEquals(UiMessage.Kind.ERROR, vm.message.value!!.kind)
        vm.clear()
    }

    @Test
    fun `the feed loads the first page, the stories row and the unread count, then pages without repeats`() = runTest {
        val social = FakeSocial()
        val vm = SocialFeedViewModel(FakePlayer(), social, main())
        val s = vm.state.value
        assertEquals(listOf(3, 2), s.posts.valueOrNull!!.map { it.id })
        assertEquals(listOf(2), s.activeToday.map { it.userId })
        assertEquals(4, s.unreadMessages)
        assertTrue(s.canLoadMore)
        vm.loadMore()
        assertEquals(listOf(3, 2, 1), vm.state.value.posts.valueOrNull!!.map { it.id })
        assertFalse(vm.state.value.canLoadMore)
        vm.loadMore()
        assertEquals(listOf(null, 2), social.feedCalls)
        vm.prepend(post(50, author = 1))
        assertEquals(50, vm.state.value.posts.valueOrNull!!.first().id)
        vm.clear()
    }

    @Test
    fun `a failed refresh keeps the shown feed and says why, a failed first load fails`() = runTest {
        val social = FakeSocial()
        val vm = SocialFeedViewModel(FakePlayer(), social, main())
        social.pages = mapOf(null to fail(AppError.Offline()))
        vm.refresh()
        assertEquals(2, vm.state.value.posts.valueOrNull!!.size)
        assertEquals(UiMessage.Kind.ERROR, vm.message.value!!.kind)
        assertFalse(vm.state.value.refreshing)
        val cold = SocialFeedViewModel(FakePlayer(), social, main())
        assertIs<Loadable.Failed>(cold.state.value.posts)
        vm.clear()
        cold.clear()
    }

    @Test
    fun `kudos toggles at once, double-tap only adds, and a failure puts the post back`() = runTest {
        val vm = SocialFeedViewModel(FakePlayer(), FakeSocial(), main())
        vm.toggleKudos(3)
        val liked = vm.state.value.posts.valueOrNull!!.first { it.id == 3 }
        assertEquals("fire", liked.myReaction)
        assertEquals(1, liked.totalReactions)
        vm.kudosByDoubleTap(3)
        assertEquals("fire", vm.state.value.posts.valueOrNull!!.first { it.id == 3 }.myReaction)

        val failing = SocialFeedViewModel(FailingReactions(), FakeSocial(), main())
        failing.toggleKudos(3)
        val back = failing.state.value.posts.valueOrNull!!.first { it.id == 3 }
        assertNull(back.myReaction)
        assertEquals(0, back.totalReactions)
        assertEquals(UiMessage.Kind.ERROR, failing.message.value!!.kind)
        vm.clear()
        failing.clear()
    }

    @Test
    fun `comments, share and delete edit the list in place`() = runTest {
        val player = FakePlayer()
        val social = FakeSocial()
        val vm = SocialFeedViewModel(player, social, main())
        vm.openComments(3)
        vm.addComment(3, "  strong  ")
        assertEquals(1, vm.state.value.posts.valueOrNull!!.first { it.id == 3 }.commentCount)
        assertEquals(listOf("strong"), vm.sheets.value.comments.map { it.body })
        vm.share(3)
        assertTrue(vm.sheets.value.share!!.text.endsWith("/p/3"))
        vm.shared(completed = true)
        assertNull(vm.sheets.value.share)
        assertEquals("share_completed", player.events.last().first)
        vm.delete(2)
        assertEquals(listOf(3), vm.state.value.posts.valueOrNull!!.map { it.id })
        assertEquals(listOf(2), social.deleted)
        vm.clear()
    }

    @Test
    fun `discover filters by activity, opens a post and rolls back a failed follow`() = runTest {
        val social = FakeSocial()
        val vm = SocialDiscoverViewModel(FailingReactions(), social, main())
        assertEquals("run", vm.state.value.chips.first())
        assertEquals(1, vm.state.value.chips.count { it == "run" })
        vm.select("cycle")
        vm.select("cycle")
        assertEquals(listOf<Pair<String?, Int>>(null to 0, "cycle" to 0), social.discoverCalls)
        vm.open(10)
        assertEquals(10, vm.state.value.openPost!!.id)
        vm.follow(5)
        assertFalse(5 in vm.state.value.followed)
        assertTrue(vm.state.value.endReached)
        vm.loadMore()
        assertEquals(2, social.discoverCalls.size)
        vm.clear()
    }

    @Test
    fun `search waits for two characters and the debounce, and follow flips at once`() = runTest {
        val social = FakeSocial()
        val vm = SocialSearchViewModel(social, FakePlayer(), main())
        vm.query("a")
        assertNull(vm.state.value.results)
        vm.query("an")
        vm.query("ana")
        assertIs<Loadable.Loading>(vm.state.value.results)
        advanceTimeBy(SocialSearchViewModel.DEBOUNCE_MS + 1)
        assertEquals(listOf("ana"), social.searches)
        vm.toggleFollow(8)
        assertTrue(vm.state.value.results!!.valueOrNull!!.single().following)
        vm.clear()
    }

    @Test
    fun `following from a profile updates the count and opens messaging`() = runTest {
        val vm = SocialProfileViewModel(5, FakePlayer(), FakeSocial(), main())
        assertFalse(vm.state.value.profile.valueOrNull!!.canMessage)
        vm.toggleFollow()
        val p = vm.state.value.profile.valueOrNull!!
        assertTrue(p.user.following)
        assertEquals(10, p.followersCount)
        assertTrue(p.canMessage)
        vm.delete(10)
        assertEquals(0, vm.state.value.profile.valueOrNull!!.posts.size)
        vm.clear()
    }

    @Test
    fun `chat marks unread messages read, sends a trimmed message and merges older pages`() = runTest {
        val social = FakeSocial()
        val vm = ChatViewModel(2, social, main(), pollMs = 0)
        assertEquals(listOf(2), social.readMarks)
        assertFalse(vm.state.value.canSend)
        vm.edit("  see you at 6  ")
        vm.send()
        assertEquals(listOf(2 to "see you at 6"), social.sent)
        assertEquals("", vm.state.value.draft)
        assertEquals(listOf(1, 99), vm.state.value.messages.valueOrNull!!.map { it.id })
        vm.loadOlder()
        assertTrue(vm.state.value.reachedStart)
        assertEquals(listOf(null, 1), social.threadCalls)
        vm.clear()
    }

    @Test
    fun `chat polls for new messages while open`() = runTest {
        val social = FakeSocial()
        val vm = ChatViewModel(2, social, main(), pollMs = 1_000)
        social.threadResult = ok(MessageThread(user(2), true, listOf(message(1, false), message(2, false))))
        advanceTimeBy(1_001)
        assertEquals(listOf(1, 2), vm.state.value.messages.valueOrNull!!.map { it.id })
        vm.clear()
    }

    @Test
    fun `a failed first load of a chat can be retried`() = runTest {
        val social = FakeSocial().apply { threadResult = fail(AppError.Offline()) }
        val vm = ChatViewModel(2, social, main(), pollMs = 0)
        assertIs<Loadable.Failed>(vm.state.value.messages)
        social.threadResult = ok(MessageThread(user(2), true, listOf(message(1, false))))
        vm.reload()
        assertEquals(listOf(1), vm.state.value.messages.valueOrNull!!.map { it.id })
        vm.clear()
    }

    @Test
    fun `a player who may not message sees the thread but cannot send`() = runTest {
        val social = FakeSocial().apply { threadResult = ok(MessageThread(user(2), false, emptyList())) }
        val vm = ChatViewModel(2, social, main(), pollMs = 0)
        vm.edit("hi")
        assertFalse(vm.state.value.canSend)
        vm.send()
        assertTrue(social.sent.isEmpty())
        vm.clear()
    }

    @Test
    fun `the inbox loads contacts for a new message once`() = runTest {
        val vm = InboxViewModel(FakeSocial(), FakeTraining(), main())
        assertEquals(4, vm.state.value.inbox.valueOrNull!!.unreadTotal)
        vm.openNewMessage()
        vm.openNewMessage()
        assertEquals(listOf("Ana"), vm.state.value.newMessageOptions.map { it.displayName })
        vm.clear()
    }

    @Test
    fun `the composer caps workouts at four and posts photo, workouts and chart together`() = runTest {
        val social = FakeSocial()
        val vm = ComposePostViewModel(social, FakeTraining(), preselectedSessionId = 1, dispatcher = main())
        assertEquals("Run", vm.state.value.activityName("run"))
        assertTrue(vm.state.value.canPost)
        listOf(2, 3, 4, 5).forEach(vm::toggleSession)
        assertEquals(listOf(1, 2, 3, 4), vm.state.value.selected)
        assertEquals(UiMessage.Kind.INFO, vm.message.value!!.kind)
        vm.toggleSession(1)
        vm.toggleChart()
        vm.photo("/9j/base64")
        vm.followersOnly(true)
        vm.caption("Leg day")
        vm.post()
        val sent = social.created.single()
        assertEquals(listOf(2, 3, 4), sent.trainingSessionIds)
        assertEquals(SocialPostDraft.CHART_WEEKLY, sent.chart)
        assertEquals("followers", sent.visibility)
        assertEquals("/9j/base64", sent.photoJpegBase64)
        assertEquals(50, vm.state.value.posted!!.id)
        vm.clear()
    }

    @Test
    fun `an empty composer cannot post`() = runTest {
        val social = FakeSocial()
        val vm = ComposePostViewModel(social, FakeTraining(), dispatcher = main())
        assertFalse(vm.state.value.canPost)
        vm.post()
        assertTrue(social.created.isEmpty())
        vm.clear()
    }
}
