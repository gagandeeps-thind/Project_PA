package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.LoginResponse
import com.osiris.shared.domain.model.RegisterResponse
import com.osiris.shared.domain.model.Registration
import com.osiris.shared.domain.model.TokenResponse
import com.osiris.shared.domain.model.UserProfile
import kotlin.time.Instant

/** Sign-in, sign-up and session endpoints. */
class AuthApi(private val api: ApiClient) {
    suspend fun login(email: String, password: String, now: Instant): LoginResponse =
        api.post(
            "/api/v1/auth/login",
            ApiClient.body("email" to email, "password" to password, "device_timestamp" to now.toString()),
        )

    suspend fun register(r: Registration, utcOffsetMinutes: Int, installId: String): RegisterResponse =
        api.post(
            "/api/v2/auth/register",
            ApiClient.body(
                "email" to r.email.trim(),
                "password" to r.password,
                "display_name" to r.displayName.trim(),
                "goal" to r.goal.wire,
                "location_consent" to r.locationConsent,
                "utc_offset_minutes" to utcOffsetMinutes,
                "referral_code" to r.referralCode?.trim()?.takeIf { it.isNotEmpty() },
                "invite_token" to r.inviteToken?.trim()?.takeIf { it.isNotEmpty() },
                "install_id" to installId,
            ),
        )

    suspend fun user(userId: Int): UserProfile = api.get("/api/v1/users/$userId")

    /** Signs out every other device; returns this device's fresh token. */
    suspend fun revokeOtherSessions(): TokenResponse = api.post("/api/v2/me/sessions/revoke")
}
