// The Android player app: Jetpack Compose screens over the shared view models.
// Business logic lives in shared/; this module only renders state and adapts platform
// services (location, camera + ML Kit pose, share sheet, secure storage, Google Play Billing)
// to the shared code.
//
// Build:   ./gradlew :android_version:app:assembleDebug                  (dev backend, 10.0.2.2)
//          ./gradlew :android_version:app:assembleRelease                (always prod, signed)
//          scripts/build_android_release.sh <versionCode> [versionName]  (the Play bundle)
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// The same environment file the shared core compiles in (see :shared:core:generateEnv).
val osirisEnvName = rootProject.extra["osirisEnvName"] as String
val osirisEnv = java.util.Properties().apply {
    rootProject.file("config/environments/$osirisEnvName.properties").inputStream().use { load(it) }
    val local = java.util.Properties()
    rootProject.file("config/environments/local.properties").takeIf { it.exists() }?.inputStream()?.use { local.load(it) }
    // A developer's local overrides never reach a prod build; only the Mapbox token (not in git) is taken.
    if (osirisEnvName == "prod") local.keys.retainAll(setOf("MAPBOX_ACCESS_TOKEN"))
    putAll(local)
}
// Mapbox public token: CI passes it as a Gradle property or env var, a workstation keeps it in local.properties.
val mapboxAccessToken = (
    providers.gradleProperty("osiris.mapboxAccessToken").orNull
        ?: System.getenv("OSIRIS_MAPBOX_ACCESS_TOKEN")
        ?: osirisEnv.getProperty("MAPBOX_ACCESS_TOKEN")
        ?: ""
    ).trim()

// Release signing credentials loaded from keystore.properties / key.properties (git-ignored)
// or CI/CD environment variables (see keystore.properties.template).
val keystorePropsFile = listOf(
    rootProject.file("keystore.properties"),
    rootProject.file("key.properties"),
    rootProject.file("android_version/keystore.properties"),
    rootProject.file("android_version/key.properties"),
).firstOrNull { it.exists() }

val keystoreProps = java.util.Properties().apply {
    keystorePropsFile?.inputStream()?.use { load(it) }
}

fun signingProp(propKey: String, vararg envKeys: String): String? =
    keystoreProps.getProperty(propKey)?.trim()?.takeIf { it.isNotEmpty() }
        ?: envKeys.firstNotNullOfOrNull { System.getenv(it)?.trim()?.takeIf { v -> v.isNotEmpty() } }

val releaseStoreFile = signingProp("storeFile", "OSIRIS_KEYSTORE_FILE", "ANDROID_KEYSTORE_FILE")
    ?.let { path ->
        val candidate = File(path)
        if (candidate.isAbsolute) candidate else rootProject.file(path)
    }
val releaseStorePassword = signingProp("storePassword", "OSIRIS_KEYSTORE_PASSWORD", "ANDROID_KEYSTORE_PASSWORD")
val releaseKeyAlias = signingProp("keyAlias", "OSIRIS_KEY_ALIAS", "ANDROID_KEY_ALIAS")
val releaseKeyPassword = signingProp("keyPassword", "OSIRIS_KEY_PASSWORD", "ANDROID_KEY_PASSWORD")
val hasReleaseSigning = releaseStoreFile != null &&
    releaseStoreFile.exists() &&
    !releaseStorePassword.isNullOrBlank() &&
    !releaseKeyAlias.isNullOrBlank() &&
    !releaseKeyPassword.isNullOrBlank()

val explicitVersionCode = providers.gradleProperty("osiris.versionCode").orNull?.toIntOrNull()
    ?: System.getenv("OSIRIS_VERSION_CODE")?.toIntOrNull()
val resolvedVersionCode = explicitVersionCode ?: 2
val resolvedVersionName = providers.gradleProperty("osiris.versionName").orNull
    ?: System.getenv("OSIRIS_VERSION_NAME")?.takeIf { it.isNotBlank() }
    ?: "1.0.1"
val playBillingPublicKey = (
    osirisEnv.getProperty("billing.playPublicKey")
        ?: System.getenv("OSIRIS_PLAY_BILLING_PUBLIC_KEY")
        ?: ""
    ).replace("\\", "\\\\").replace("\"", "\\\"")

// A release artifact that points at a dev server, is unsigned, or reuses a version code is useless
// and easy to upload by mistake, so those builds stop here instead of succeeding.
gradle.taskGraph.whenReady {
    val names = allTasks.filter { it.project == project }.map { it.name }
    val bundle = "packageReleaseBundle" in names
    if (bundle || "packageRelease" in names) {
        val problems = listOfNotNull(
            (
                "the environment is '$osirisEnvName'; release builds are prod only " +
                    "(pass -Posiris.env=prod, or name the release task in full without -Posiris.env)"
                ).takeIf { osirisEnvName != "prod" },
            "signing credentials are missing (keystore.properties or OSIRIS_KEYSTORE_*; see keystore.properties.template)"
                .takeIf { !hasReleaseSigning },
            "a positive whole-number version code is required for a bundle (-Posiris.versionCode=<N> or OSIRIS_VERSION_CODE)"
                .takeIf { bundle && (explicitVersionCode == null || explicitVersionCode < 1) },
        )
        if (problems.isNotEmpty()) {
            throw GradleException("Cannot build the Android release:\n - " + problems.joinToString("\n - "))
        }
        if (mapboxAccessToken.isEmpty()) {
            logger.warn(
                "WARNING: no Mapbox token (osiris.mapboxAccessToken, OSIRIS_MAPBOX_ACCESS_TOKEN or " +
                    "config/environments/local.properties); this release ships with the Arise map disabled.",
            )
        }
    }
}

apply(plugin = "com.android.application")
apply(plugin = "org.jetbrains.kotlin.android")
apply(plugin = "org.jetbrains.kotlin.plugin.compose")

extensions.configure<com.android.build.api.dsl.ApplicationExtension> {
    namespace = "osiris.fit"
    compileSdk = libs.versions.android.compileSdk.get().toInt()

    defaultConfig {
        // Unique application ID for Google Play Store distribution.
        applicationId = "osiris.fit"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.targetSdk.get().toInt()
        versionCode = resolvedVersionCode
        versionName = resolvedVersionName
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // Empty disables the map.
        resValue("string", "mapbox_access_token", mapboxAccessToken)
        manifestPlaceholders["webLinkHost"] = osirisEnv.getProperty("links.webHost")
        buildConfigField("String", "PLAY_BILLING_PUBLIC_KEY", "\"$playBillingPublicKey\"")
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = releaseStoreFile
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
                enableV4Signing = true
            }
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("release")
            }
            // ML Kit's pose library is ~20 MB per ABI and made up 77 MB of the 87 MB release APK.
            // Phones are ARM; x86 builds only serve emulators and ChromeOS, which run ARM code too.
            // Debug keeps every ABI for fast emulator runs; a Play bundle splits per device anyway.
            ndk {
                abiFilters += setOf("arm64-v8a", "armeabi-v7a")
                debugSymbolLevel = "SYMBOL_TABLE"
            }
        }
    }

    bundle {
        language { enableSplit = true }
        density { enableSplit = true }
        abi { enableSplit = true }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}", "/META-INF/INDEX.LIST", "/META-INF/io.netty.versions.properties")
    }
}

extensions.configure<org.jetbrains.kotlin.compose.compiler.gradle.ComposeCompilerGradlePluginExtension> {
    stabilityConfigurationFiles.add(layout.projectDirectory.file("compose-stability.conf"))
    providers.gradleProperty("osiris.composeReports").orNull?.let { reportsDestination.set(layout.buildDirectory.dir(it)) }
}

extensions.configure<org.jetbrains.kotlin.gradle.dsl.KotlinAndroidProjectExtension> {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
        allWarningsAsErrors.set(true)
        optIn.addAll("kotlin.time.ExperimentalTime", "androidx.compose.material3.ExperimentalMaterial3Api")
    }
}

dependencies {
    "implementation"(project(":shared:presentation"))
    "implementation"(libs.kotlinx.coroutines.android)
    "implementation"(libs.kotlinx.coroutines.play.services)

    "implementation"(platform(libs.compose.bom))
    "implementation"(libs.compose.ui)
    "implementation"(libs.compose.material3)
    "implementation"(libs.compose.material.icons)
    "implementation"(libs.compose.ui.tooling.preview)
    "debugImplementation"(libs.compose.ui.tooling)

    "implementation"(libs.androidx.core.ktx)
    "implementation"(libs.androidx.activity.compose)
    "implementation"(libs.androidx.lifecycle.viewmodel.compose)
    "implementation"(libs.androidx.lifecycle.runtime.compose)
    "implementation"(libs.androidx.lifecycle.service)
    "implementation"(libs.androidx.navigation.compose)

    "implementation"(libs.camerax.core)
    "implementation"(libs.camerax.camera2)
    "implementation"(libs.camerax.lifecycle)
    "implementation"(libs.camerax.view)
    "implementation"(libs.mlkit.pose.detection)
    "implementation"(libs.play.services.location)
    "implementation"(libs.play.billing.ktx)
    "implementation"(libs.osmdroid)
    "implementation"(libs.haze)
    "implementation"(libs.mapbox.maps)
    "implementation"(libs.health.connect)
    "implementation"(libs.guava)

    "testImplementation"(libs.junit)
    "testImplementation"(libs.kotlinx.coroutines.test)
    "androidTestImplementation"(platform(libs.compose.bom))
    "androidTestImplementation"(libs.compose.ui.test.junit4)
    "debugImplementation"(libs.compose.ui.test.manifest)
}
