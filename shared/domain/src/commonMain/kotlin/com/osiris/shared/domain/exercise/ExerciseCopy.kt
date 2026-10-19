package com.osiris.shared.domain.exercise

import com.osiris.shared.domain.common.Format

/** Player-facing copy for exercise results, identical on both apps. */
object ExerciseCopy {
    private val reasons = mapOf(
        "too_fast" to "Some reps were too fast to be controlled",
        "too_slow" to "A rep took too long",
        "form_break" to "Form broke on some reps",
        "wrong_position" to "Body position did not match the exercise",
        "low_visibility" to "You were partly out of view",
        "tracking_glitch" to "The camera lost track of you",
        "unsteady_tracking" to "Tracking was too unsteady to count. Move closer or add light",
        "partial_range" to "Some reps were not full range",
        "no_valid_reps" to "No reps counted",
        "low_valid_ratio" to "Most reps did not count",
        "replay_suspected" to "Rep timing was machine-perfect",
        "rate_implausible" to "More reps per minute than is possible",
        "no_entry_transition" to "Start outside the position, then move into it",
        "static_pose" to "No natural movement was seen",
        "hold_too_short" to "The hold was too short",
    )

    /** Unknown codes fall back to the code, so a new server reason still shows something. */
    fun reason(code: String): String = reasons[code] ?: code

    fun verdictTitle(verdict: Verdict): String = when (verdict) {
        Verdict.VERIFIED -> "Verified"
        Verdict.REVIEW -> "Sent for review"
        Verdict.REJECTED -> "Not verified"
    }

    /** `12 reps` or `45 s` for a personal best or a set. */
    fun amount(spec: ExerciseSpec?, reps: Int, holdS: Double): String =
        if (spec?.isHold == true || (spec == null && holdS > 0)) "${Format.fixed(holdS, 0)} s" else "$reps reps"

    fun best(spec: ExerciseSpec, best: Double): String =
        if (spec.isHold) "${Format.fixed(best, 0)} s" else "${Format.fixed(best, 0)} reps"
}
