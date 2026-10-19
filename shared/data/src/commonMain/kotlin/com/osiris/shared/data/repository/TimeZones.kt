package com.osiris.shared.data.repository

import kotlin.time.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.offsetAt

/** The phone's UTC offset at [now], in minutes; the server sizes "today" with it. */
fun utcOffsetMinutes(now: Instant, zone: TimeZone = TimeZone.currentSystemDefault()): Int =
    zone.offsetAt(now).totalSeconds / 60
