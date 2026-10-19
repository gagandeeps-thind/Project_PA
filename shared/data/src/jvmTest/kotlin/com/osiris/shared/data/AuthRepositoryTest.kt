package com.osiris.shared.data

import com.osiris.shared.core.error.AppError
import com.osiris.shared.data.FakeServer.Companion.reply
import com.osiris.shared.domain.model.Goal
import com.osiris.shared.domain.model.Registration
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.domain.run.LocationFix
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class AuthRepositoryTest {
    private fun TestApp.serveLogin(role: String = "player") {
        server.json("POST /api/v1/auth/login") { """{"access_token":"tok-1","role":"$role","id":7}""" }
        server.json("GET /api/v1/users/7") { PLAYER }
    }

    @Test
    fun `a player signs in, the token is stored and sent on later calls`() = test {
        val app = TestApp().apply { serveLogin() }
        val user = app.graph.auth.login("p@x.io", "secret123").getOrThrow()
        assertEquals(7, user.id)
        assertIs<AuthState.SignedIn>(app.graph.auth.state.value)
        assertEquals("tok-1", app.secure.get("auth_token"))
        assertEquals("Bearer tok-1", app.server.calls.last().auth)
    }

    @Test
    fun `merchants and admins are refused and nothing is stored`() = test {
        val app = TestApp().apply { serveLogin(role = "merchant") }
        val error = app.graph.auth.login("m@x.io", "secret123").errorOrNull()
        assertIs<AppError.Validation>(error)
        assertNull(app.secure.get("auth_token"))
        assertEquals(0, app.server.count("GET /api/v1/users/7"))
    }

    @Test
    fun `a wrong password shows the server's message`() = test {
        val app = TestApp()
        app.server.json("POST /api/v1/auth/login", 401) { """{"detail":"Invalid email or password"}""" }
        val error = app.graph.auth.login("p@x.io", "nope-nope").errorOrNull()
        assertEquals("Invalid email or password", error?.userMessage)
        assertEquals(AuthState.SignedOut, app.graph.auth.state.value)
    }

    @Test
    fun `restore signs the player back in from secure storage`() = test {
        val app = TestApp()
        app.secure.put("auth_token", "tok-1")
        app.secure.put("user_id", "7")
        app.server.json("GET /api/v1/users/7") { PLAYER }
        app.graph.auth.restore()
        assertEquals(7, (app.graph.auth.state.value as AuthState.SignedIn).user.id)
    }

    @Test
    fun `an offline start keeps the player signed in with the cached profile`() = test {
        val first = TestApp().apply { serveLogin() }
        first.graph.auth.login("p@x.io", "secret123").getOrThrow()
        val second = TestApp(settings = first.settings, secure = first.secure).apply { server.offline = true }
        second.graph.auth.restore()
        assertEquals(7, (second.graph.auth.state.value as AuthState.SignedIn).user.id)
    }

    @Test
    fun `an expired token on restore signs out and clears the stored session`() = test {
        val app = TestApp()
        app.secure.put("auth_token", "old")
        app.secure.put("user_id", "7")
        app.server.json("GET /api/v1/users/7", 401) { """{"detail":"Token expired"}""" }
        app.graph.auth.restore()
        assertEquals(AuthState.SignedOut, app.graph.auth.state.value)
        assertNull(app.secure.get("auth_token"))
    }

    @Test
    fun `any 401 later in the session signs the player out`() = test {
        val app = TestApp().apply { serveLogin() }
        app.graph.auth.login("p@x.io", "secret123").getOrThrow()
        app.server.json("GET /api/v2/me/progression", 401) { """{"detail":"revoked"}""" }
        assertIs<AppError.Unauthorized>(app.graph.player.progression().errorOrNull())
        assertEquals(AuthState.SignedOut, app.graph.auth.state.value)
    }

    @Test
    fun `sign-up sends no body metrics, signs in and completes onboarding`() = test {
        val app = TestApp()
        app.server.json("POST /api/v2/auth/register") { """{"access_token":"tok-2","profile":{"user_id":7}}""" }
        app.server.json("GET /api/v1/users/7") { PLAYER }
        app.server.json("PUT /api/v2/me/profile") { """{"user_id":7,"onboarding_completed":true}""" }
        val reg = Registration("p@x.io", "secret123", "Pat", Goal.RUNNING, locationConsent = false, referralCode = " ")
        app.graph.auth.register(reg).getOrThrow()
        val body = app.server.calls.first { it.path == "/api/v2/auth/register" }.body!!.jsonObject
        assertEquals("running", body["goal"]!!.jsonPrimitive.content)
        assertTrue("referral_code" !in body && "weight_kg" !in body && "install_id" in body)
        assertEquals(1, app.server.count("PUT /api/v2/me/profile"))
    }

    @Test
    fun `invalid sign-up input is refused before any request`() = test {
        val app = TestApp()
        val error = app.graph.auth.register(Registration("nope", "short", "P", Goal.FITNESS, false)).errorOrNull()
        assertIs<AppError.Validation>(error)
        assertTrue(app.server.calls.none { it.path == "/api/v2/auth/register" })
    }

    @Test
    fun `signing out discards the unfinished run queued on this phone`() = test {
        val app = TestApp().apply { serveLogin() }
        app.server.json("POST /api/v2/runs") { """{"id":11}""" }
        app.server.json("POST /api/v2/runs/11/start") { "{}" }
        app.graph.auth.login("p@x.io", "secret123").getOrThrow()
        val t0 = Instant.parse("2026-05-01T06:00:00Z")
        app.graph.runs.start(null, t0).getOrThrow()
        app.server.offline = true
        app.graph.runs.addFix(LocationFix(52.0, 4.0), t0)
        app.graph.auth.logout()
        assertNull(app.graph.runs.active.value)
        assertNull(app.settings.getStringOrNull("osiris.active_run.v1"))
    }

    @Test
    fun `sign out everywhere adopts the fresh token`() = test {
        val app = TestApp().apply { serveLogin() }
        app.graph.auth.login("p@x.io", "secret123").getOrThrow()
        app.server.on("POST /api/v2/me/sessions/revoke") { reply(200, """{"access_token":"tok-new"}""") }
        app.graph.auth.signOutEverywhere().getOrThrow()
        assertEquals("tok-new", app.secure.get("auth_token"))
    }
}
