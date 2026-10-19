package com.osiris.shared.domain.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RegistrationTest {
    private fun registration(password: String) = Registration(
        email = "ada@example.com",
        password = password,
        displayName = "Ada",
        goal = Goal.FITNESS,
        locationConsent = true,
    )

    @Test
    fun passwordsWithinTheServerLimitAreValid() {
        assertTrue(registration("a".repeat(72)).validate().isEmpty())
    }

    @Test
    fun passwordsOverSeventyTwoBytesAreRefusedEvenWhenShorterInCharacters() {
        // 40 characters, 80 bytes: bcrypt on the server would refuse it.
        assertEquals("At most 72 characters", registration("é".repeat(40)).validate()[Registration.FIELD_PASSWORD])
        assertEquals("At most 72 characters", registration("a".repeat(73)).validate()[Registration.FIELD_PASSWORD])
    }
}
