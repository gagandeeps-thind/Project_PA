import org.jetbrains.kotlin.gradle.ExperimentalKotlinGradlePluginApi
import org.jetbrains.kotlin.gradle.dsl.KotlinMultiplatformExtension

// Plugins go on the root classpath (not `plugins {}` with `apply false`) so the Android Gradle
// Plugin can be left out entirely on machines without the Android SDK: Google Maven is then
// never contacted and every shared module still builds.
buildscript {
    val androidEnabled = gradle.extra["osiris.android"] as Boolean
    repositories {
        if (androidEnabled) google()
        mavenCentral()
        gradlePluginPortal()
    }
    dependencies {
        classpath(libs.kotlin.gradle.plugin)
        classpath(libs.kotlin.serialization.plugin)
        classpath(libs.compose.compiler.plugin)
        classpath(libs.sqldelight.gradle.plugin)
        if (androidEnabled) classpath(libs.android.gradle.plugin)
    }
}

val androidEnabled = gradle.extra["osiris.android"] as Boolean

// Conventions for every shared Kotlin Multiplatform module: the same targets, compiler
// options and test setup everywhere, so a module only declares its own dependencies.
subprojects {
    if (path.startsWith(":shared:")) {
        apply(plugin = "org.jetbrains.kotlin.multiplatform")
        if (androidEnabled) {
            extra["osiris.androidNamespace"] = "com.osiris.shared." + name
            apply(from = rootProject.file("gradle/android-library.gradle"))
        }
        extensions.configure<KotlinMultiplatformExtension> {
            jvm {
                compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
            }
            // Set here rather than in android-library.gradle: Groovy cannot resolve the JvmTarget class.
            if (androidEnabled) {
                androidTarget {
                    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
                }
            }
            iosArm64()
            iosSimulatorArm64()
            iosX64()
            @OptIn(ExperimentalKotlinGradlePluginApi::class)
            compilerOptions {
                allWarningsAsErrors.set(true)
                optIn.addAll("kotlin.time.ExperimentalTime", "kotlinx.coroutines.ExperimentalCoroutinesApi")
                freeCompilerArgs.add("-Xexpect-actual-classes")
            }
            sourceSets.getByName("commonTest").dependencies {
                implementation(kotlin("test"))
            }
        }
        tasks.withType<JavaCompile>().configureEach {
            sourceCompatibility = "17"
            targetCompatibility = "17"
        }
        tasks.withType<Test>().configureEach {
            testLogging {
                events("failed", "skipped")
                showStandardStreams = providers.gradleProperty("osiris.testOutput").orNull == "true"
                exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
            }
        }
    }
}
