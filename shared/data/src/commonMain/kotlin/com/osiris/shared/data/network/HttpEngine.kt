package com.osiris.shared.data.network

import io.ktor.client.engine.HttpClientEngine

/** The platform's HTTP engine: OkHttp on Android, NSURLSession on iOS, CIO on the JVM. */
expect fun platformHttpEngine(): HttpClientEngine
