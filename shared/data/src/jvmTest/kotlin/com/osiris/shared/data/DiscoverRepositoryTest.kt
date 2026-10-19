package com.osiris.shared.data

import com.osiris.shared.domain.model.BoardExercise
import com.osiris.shared.domain.model.BoardKind
import com.osiris.shared.domain.model.BoardPeriod
import com.osiris.shared.domain.model.HubSection
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class DiscoverRepositoryTest {
    @Test
    fun `hub asks for one section and returns its items`() = test {
        val app = TestApp()
        app.server.json("GET /api/v2/challenge-hub") {
            """{"section":"finished","items":[{"challenge":{"id":4,"title":"Loop","status":"closed"},"participants":2,
               "winners":[{"rank":1,"name":"Private runner","elapsed_seconds":1290.0}],"xp_paid":40}]}"""
        }
        val items = app.graph.challenges.hub(HubSection.FINISHED).getOrThrow()
        assertEquals("section=finished", app.server.calls.single().query)
        assertEquals("Private runner", items.single().winners.single().name)
        assertEquals(40, items.single().xpPaid)
    }

    @Test
    fun `global board sends the board, period and exercise`() = test {
        val app = TestApp()
        app.server.json("GET /api/v2/leaderboards/global") {
            """{"board":"reps","period":"all","exercise":"squat","unit":"reps","lower_is_better":false,
               "explainer":"","rows":[{"rank":1,"name":"Ana","value":120.0,"is_me":true}],"ranked_players":1}"""
        }
        val board = app.graph.communities.globalBoard(BoardKind.REPS, BoardPeriod.ALL, BoardExercise.SQUAT).getOrThrow()
        assertEquals("board=reps&period=all&exercise=squat", app.server.calls.single().query)
        assertEquals("120 reps", board.format(board.rows.single().value))
    }

    @Test
    fun `builds without the wallet flag have no wallet`() {
        assertNull(TestApp().graph.wallet)
    }
}
