package com.osiris.shared.data.network

import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.cio.CIO

actual fun platformHttpEngine(): HttpClientEngine = CIO.create()
