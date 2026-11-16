// The Android player app: Jetpack Compose screens over the shared view models.
// Business logic lives in shared/; this module only renders state and adapts platform
// services (location, camera + ML Kit pose, share sheet, secure storage, Google Play Billing)
// to the shared code.
//
// Build:   ./gradlew :android_version:app:assembleDebug                  (dev backend, 10.0.2.2)
//          ./gradlew :android_version:app:assembleRelease                (defaults to prod)
//          ./gradlew :android_version:app:bundleRelease                  (defaults to prod)
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// The same environment file the shared core compiles in (see :shared:core:generateEnv).
// Release builds default to `prod` so a signed APK/AAB never ships pointing at 10.0.2.2.
val isReleaseRequested = gradle.startParameter.taskNames.any {
    it.contains("Release", ignoreCase = true)
}
val osirisEnvName = providers.gradleProperty("osiris.env").orNull
    ?: if (isReleaseRequested) "prod" else "dev"
val osirisEnv = java.util.Properties().apply {
    if (osirisEnvName != "dev") {
        rootProject.file("config/environments/local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
    }
    rootProject.file("config/environments/$osirisEnvName.properties").inputStream().use { load(it) }
    if (osirisEnvName == "dev") {
        rootProject.file("config/environments/local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
    }
}

val verifyReleaseEnv by tasks.registering {
    description = "Fails fast if a release artifact is built against the dev environment or cleartext HTTP."
    val env = osirisEnvName
    val androidBaseUrl = osirisEnv.getProperty("api.baseUrl.android").orEmpty().trim()
    doLast {
        check(env != "dev") {
            "Release builds cannot use osiris.env=dev ($androidBaseUrl is unreachable on devices and blocked by cleartext policy). " +
                "Omit -Posiris.env (defaults to prod) or pass -Posiris.env=prod."
        }
        check(androidBaseUrl.startsWith("https://")) {
            "Release builds require an https:// api.baseUrl.android, got '$androidBaseUrl' (osiris.env=$env)."
        }
    }
}

tasks.matching {
    it.name in setOf("preReleaseBuild", "assembleRelease", "bundleRelease", "packageRelease", "packageReleaseBundle")
}.configureEach {
    dependsOn(verifyReleaseEnv)
}

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

val resolvedVersionCode = providers.gradleProperty("osiris.versionCode").orNull?.toIntOrNull()
    ?: System.getenv("OSIRIS_VERSION_CODE")?.toIntOrNull()
    ?: 2
val resolvedVersionName = providers.gradleProperty("osiris.versionName").orNull
    ?: System.getenv("OSIRIS_VERSION_NAME")?.takeIf { it.isNotBlank() }
    ?: "1.0.1"
val playBillingPublicKey = (
    osirisEnv.getProperty("billing.playPublicKey")
        ?: System.getenv("OSIRIS_PLAY_BILLING_PUBLIC_KEY")
        ?: ""
    ).replace("\\", "\\\\").replace("\"", "\\\"")

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
        // Mapbox public token from config/environments/local.properties (git-ignored); empty disables the map.
        resValue("string", "mapbox_access_token", osirisEnv.getProperty("MAPBOX_ACCESS_TOKEN").orEmpty())
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
