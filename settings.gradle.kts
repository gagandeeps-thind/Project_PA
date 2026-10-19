// Kotlin Multiplatform build for the Osiris player apps.
//
//   shared/           business logic shared by Android and iOS (Kotlin Multiplatform)
//   android_version/  the Android app (Jetpack Compose) on top of shared/
//   ios_version/      the iOS app (SwiftUI, Xcode) on top of the OsirisShared framework
//
// The Android modules need the Android SDK. Without one (ANDROID_HOME, ANDROID_SDK_ROOT or
// sdk.dir in local.properties), the build still compiles and tests shared/ on the JVM and
// type-checks its iOS code, so the shared core can be verified on any machine.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "osiris"

fun androidSdkAvailable(): Boolean {
    providers.gradleProperty("osiris.android").orNull?.let { return it.toBoolean() }
    if (!System.getenv("ANDROID_HOME").isNullOrBlank() || !System.getenv("ANDROID_SDK_ROOT").isNullOrBlank()) return true
    val local = file("local.properties")
    return local.exists() && local.readLines().any { it.trim().startsWith("sdk.dir=") }
}

val androidEnabled = androidSdkAvailable()
gradle.extra["osiris.android"] = androidEnabled

include(":shared:core", ":shared:domain", ":shared:data", ":shared:presentation")
if (androidEnabled) {
    include(":android_version:app")
} else {
    logger.lifecycle("Osiris: no Android SDK found, building shared/ only (JVM tests + iOS type-check).")
}
