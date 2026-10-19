// The Android player app: Jetpack Compose screens over the shared view models.
// Business logic lives in shared/; this module only renders state and adapts platform
// services (location, camera + ML Kit pose, share sheet, secure storage) to the shared code.
//
// Build:   ./gradlew :android_version:app:assembleDebug                  (dev backend, 10.0.2.2)
//          ./gradlew :android_version:app:assembleRelease -Posiris.env=prod
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

apply(plugin = "com.android.application")
apply(plugin = "org.jetbrains.kotlin.android")
apply(plugin = "org.jetbrains.kotlin.plugin.compose")

extensions.configure<com.android.build.api.dsl.ApplicationExtension> {
    namespace = "com.osiris.player"
    compileSdk = libs.versions.android.compileSdk.get().toInt()

    defaultConfig {
        // A new id, so the KMP app installs next to the Flutter app during the parity check.
        applicationId = "com.osiris.player"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.targetSdk.get().toInt()
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
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
    "implementation"(libs.osmdroid)

    "testImplementation"(libs.junit)
    "androidTestImplementation"(platform(libs.compose.bom))
    "androidTestImplementation"(libs.compose.ui.test.junit4)
    "debugImplementation"(libs.compose.ui.test.manifest)
}
