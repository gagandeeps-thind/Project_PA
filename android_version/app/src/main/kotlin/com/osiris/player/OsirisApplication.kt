package com.osiris.player

import android.app.Application
import com.osiris.shared.core.config.AppConfig
import com.osiris.shared.data.storage.AndroidPlatform
import com.osiris.shared.presentation.AppGraph
import org.osmdroid.config.Configuration

/** Builds the shared graph once per process; screens reach it through [graph]. */
class OsirisApplication : Application() {
    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        val config = AppConfig.fromBuild()
        graph = AppGraph(config, AndroidPlatform.create(this, recordingAllowed = config.features.poseRecording && BuildConfig.DEBUG))
        // OpenStreetMap's tile policy requires an identifying user agent.
        Configuration.getInstance().userAgentValue = packageName
    }
}
