// I/O: the HTTP API (Ktor), the on-device database (SQLDelight), key-value and secure storage,
// and the repository implementations behind the domain contracts.
apply(plugin = "org.jetbrains.kotlin.plugin.serialization")
apply(plugin = "app.cash.sqldelight")

val androidEnabled = gradle.extra["osiris.android"] as Boolean

kotlin {
    sourceSets {
        commonMain.dependencies {
            api(project(":shared:domain"))
            implementation(libs.ktor.client.core)
            implementation(libs.ktor.client.content.negotiation)
            implementation(libs.ktor.serialization.json)
            implementation(libs.ktor.client.logging)
            implementation(libs.sqldelight.runtime)
            implementation(libs.sqldelight.coroutines)
            api(libs.multiplatform.settings)
        }
        commonTest.dependencies {
            implementation(libs.ktor.client.mock)
            implementation(libs.kotlinx.coroutines.test)
            implementation(libs.multiplatform.settings.test)
        }
        jvmMain.dependencies {
            implementation(libs.ktor.client.cio)
            implementation(libs.sqldelight.jvm.driver)
        }
        jvmTest.dependencies {
            // A real WebSocket server for the support chat test; MockEngine has no WebSockets.
            implementation(libs.ktor.server.cio)
            implementation(libs.ktor.server.websockets)
        }
        iosMain.dependencies {
            implementation(libs.ktor.client.darwin)
            implementation(libs.sqldelight.native.driver)
        }
        if (androidEnabled) {
            getByName("androidMain").dependencies {
                implementation(libs.ktor.client.okhttp)
                implementation(libs.sqldelight.android.driver)
            }
        }
    }
}

extensions.configure<app.cash.sqldelight.gradle.SqlDelightExtension> {
    databases {
        create("OsirisDatabase") {
            packageName.set("com.osiris.shared.data.db")
        }
    }
}

// The bundled exercise catalog ships inside the shared code so both apps start offline with the
// same rules. Source of truth: Osiris_backend services/exercises.py, exported to shared/assets/exercise_catalog.json.
val catalogAsset = rootProject.layout.projectDirectory.file("shared/assets/exercise_catalog.json")
val bundledDir = layout.buildDirectory.dir("generated/osirisCatalog/commonMain/kotlin")
val generateBundledCatalog by tasks.registering {
    inputs.file(catalogAsset)
    outputs.dir(bundledDir)
    doLast {
        val json = catalogAsset.asFile.readText()
        // Raw strings cannot contain three quotes; the catalog never does, but fail loudly if it ever does.
        require(!json.contains("\"\"\"")) { "catalog contains a triple quote" }
        val out = bundledDir.get().file("com/osiris/shared/data/exercise/BundledCatalog.kt").asFile
        out.parentFile.mkdirs()
        out.writeText(
            "// Generated from shared/assets/exercise_catalog.json by :shared:data:generateBundledCatalog. Do not edit.\n" +
                "package com.osiris.shared.data.exercise\n\n" +
                "internal object BundledCatalog {\n" +
                "    const val JSON: String = \"\"\"" + json.replace("$", "\${'$'}") + "\"\"\"\n" +
                "}\n",
        )
    }
}
kotlin.sourceSets.getByName("commonMain").kotlin.srcDir(generateBundledCatalog)

// The committed API contract; jvmTest checks the Kotlin models and endpoints against it.
tasks.withType<Test>().configureEach {
    systemProperty("osiris.openapi", rootProject.file("Documentation/openapi.json").absolutePath)
}
