package com.osiris.shared.core.platform

/** The runtime the shared code is executing on. */
enum class Platform { ANDROID, IOS, JVM }

/** Which platform this build of the shared code targets. */
expect val currentPlatform: Platform
