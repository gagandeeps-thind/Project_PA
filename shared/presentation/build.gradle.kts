// Screen state and user intents, shared by the Android (Compose) and iOS (SwiftUI) apps.
// View models expose StateFlow and plain functions; they never see Android or UIKit types.
import org.jetbrains.kotlin.gradle.plugin.mpp.KotlinNativeTarget

kotlin {
    targets.withType<KotlinNativeTarget>().configureEach {
        binaries.framework {
            // The one framework the iOS app links: Swift imports `OsirisShared`.
            baseName = "OsirisShared"
            isStatic = true
            export(project(":shared:core"))
            export(project(":shared:domain"))
        }
    }
    sourceSets {
        commonMain.dependencies {
            api(project(":shared:core"))
            api(project(":shared:domain"))
            api(project(":shared:data"))
            api(libs.kotlinx.coroutines.core)
        }
        commonTest.dependencies {
            implementation(libs.kotlinx.coroutines.test)
            implementation(libs.multiplatform.settings.test)
        }
    }
}

// View-model tests replay a labeled pose recording through the real rep engine.
tasks.withType<Test>().configureEach {
    systemProperty("osiris.catalog", rootProject.file("Osiris_customer/assets/exercise_catalog.json").absolutePath)
    systemProperty("osiris.recordings", rootProject.file("Osiris_customer/test/exercise/recordings").absolutePath)
}
