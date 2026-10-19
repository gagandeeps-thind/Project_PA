import java.util.Properties

// Platform-neutral building blocks: configuration, errors, results, logging, ids.
// No dependency on other Osiris modules.

val envName = providers.gradleProperty("osiris.env").getOrElse("dev")
val envDir = rootProject.layout.projectDirectory.dir("config/environments")
val generatedDir = layout.buildDirectory.dir("generated/osirisEnv/commonMain/kotlin")

val generateEnv by tasks.registering {
    description = "Compiles config/environments/<osiris.env>.properties (+ local.properties) into GeneratedEnv.kt"
    val envFile = envDir.file("$envName.properties")
    val localFile = envDir.file("local.properties")
    inputs.file(envFile)
    inputs.files(localFile.asFile.takeIf { it.exists() } ?: files())
    inputs.property("env", envName)
    outputs.dir(generatedDir)
    doLast {
        val props = Properties()
        val selected = envFile.asFile
        require(selected.exists()) { "Unknown osiris.env '$envName': ${selected.path} does not exist" }
        selected.inputStream().use(props::load)
        localFile.asFile.takeIf { it.exists() }?.inputStream()?.use(props::load)
        val required = listOf(
            "environment", "api.baseUrl.android", "api.baseUrl.ios", "api.baseUrl.jvm",
            "api.connectTimeoutMs", "api.requestTimeoutMs", "http.logging", "features.legacy", "features.poseRecording",
        )
        val missing = required.filter { props.getProperty(it).isNullOrBlank() }
        require(missing.isEmpty()) { "${selected.name} is missing: ${missing.joinToString()}" }
        fun s(key: String) = "\"" + props.getProperty(key).trim().replace("\\", "\\\\").replace("\"", "\\\"") + "\""
        fun l(key: String) = props.getProperty(key).trim().toLong().toString() + "L"
        fun b(key: String) = props.getProperty(key).trim().toBooleanStrict().toString()
        val out = generatedDir.get().file("com/osiris/shared/core/config/GeneratedEnv.kt").asFile
        out.parentFile.mkdirs()
        out.writeText(
            """
            |// Generated from config/environments/$envName.properties by :shared:core:generateEnv. Do not edit.
            |package com.osiris.shared.core.config
            |
            |internal object GeneratedEnv {
            |    const val ENVIRONMENT: String = ${s("environment")}
            |    const val API_BASE_URL_ANDROID: String = ${s("api.baseUrl.android")}
            |    const val API_BASE_URL_IOS: String = ${s("api.baseUrl.ios")}
            |    const val API_BASE_URL_JVM: String = ${s("api.baseUrl.jvm")}
            |    const val API_CONNECT_TIMEOUT_MS: Long = ${l("api.connectTimeoutMs")}
            |    const val API_REQUEST_TIMEOUT_MS: Long = ${l("api.requestTimeoutMs")}
            |    const val HTTP_LOGGING: Boolean = ${b("http.logging")}
            |    const val FEATURE_LEGACY: Boolean = ${b("features.legacy")}
            |    const val FEATURE_POSE_RECORDING: Boolean = ${b("features.poseRecording")}
            |}
            |""".trimMargin(),
        )
    }
}

kotlin {
    sourceSets {
        commonMain {
            kotlin.srcDir(generateEnv)
            dependencies {
                api(libs.kotlinx.coroutines.core)
            }
        }
    }
}
