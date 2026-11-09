package com.osiris.player

import android.app.Application
import com.osiris.player.platform.billing.BillingManager
import com.osiris.player.platform.billing.BillingService
import com.osiris.player.platform.billing.PlaySignaturePurchaseVerifier
import com.osiris.player.platform.billing.ServerPurchaseVerifier
import com.osiris.shared.core.config.AppConfig
import com.osiris.shared.data.storage.AndroidPlatform
import com.osiris.shared.presentation.AppGraph
import org.osmdroid.config.Configuration

/** Builds the shared graph and Google Play Billing service once per process. */
class OsirisApplication : Application() {
    lateinit var graph: AppGraph
        private set

    lateinit var billing: BillingService
        private set

    override fun onCreate() {
        super.onCreate()
        val config = AppConfig.fromBuild()
        graph = AppGraph(config, AndroidPlatform.create(this, recordingAllowed = config.features.poseRecording && BuildConfig.DEBUG))
        billing = BillingManager(
            context = this,
            verifier = PlaySignaturePurchaseVerifier(BuildConfig.PLAY_BILLING_PUBLIC_KEY, ServerPurchaseVerifier(graph.data.payments)),
        ).also { it.startConnection() }
        // OpenStreetMap's tile policy requires an identifying user agent.
        Configuration.getInstance().userAgentValue = packageName
    }
}
