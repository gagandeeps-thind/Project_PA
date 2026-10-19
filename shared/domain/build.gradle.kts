// Business rules and models, free of I/O: the rep engine, run and challenge rules, formatting,
// and the repository contracts the data layer implements.
apply(plugin = "org.jetbrains.kotlin.plugin.serialization")

kotlin {
    sourceSets {
        commonMain.dependencies {
            api(project(":shared:core"))
            api(libs.kotlinx.serialization.json)
            api(libs.kotlinx.datetime)
        }
    }
}

// The exercise catalog the backend serves, also bundled with the apps for offline first start.
// Tests read it from here so app, tests and server never drift apart.
val catalogAsset = rootProject.layout.projectDirectory.file("shared/assets/exercise_catalog.json")
val recordingsDir = rootProject.layout.projectDirectory.dir("shared/testdata/recordings")
tasks.withType<Test>().configureEach {
    systemProperty("osiris.catalog", catalogAsset.asFile.absolutePath)
    systemProperty("osiris.recordings", recordingsDir.asFile.absolutePath)
    inputs.file(catalogAsset)
    inputs.dir(recordingsDir)
}
