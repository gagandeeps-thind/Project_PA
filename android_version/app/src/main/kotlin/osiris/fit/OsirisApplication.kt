package osiris.fit

import android.app.Application
import osiris.fit.platform.billing.BillingManager
import osiris.fit.platform.billing.BillingService
import osiris.fit.platform.billing.PlaySignaturePurchaseVerifier
import osiris.fit.platform.billing.ServerPurchaseVerifier
import osiris.fit.platform.crash.CrashLog
import com.osiris.shared.core.config.AppConfig
import com.osiris.shared.data.storage.AndroidPlatform
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.presentation.AppGraph
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import org.osmdroid.config.Configuration

/** Builds the shared graph and Google Play Billing service once per process. */
class OsirisApplication : Application() {
    lateinit var graph: AppGraph
        private set

    lateinit var billing: BillingService
        private set

    override fun onCreate() {
        super.onCreate()
        CrashLog.install(this, "${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
        val config = AppConfig.fromBuild()
        graph = AppGraph(config, AndroidPlatform.create(this, recordingAllowed = config.features.poseRecording && BuildConfig.DEBUG))
        val store = graph.store()
        billing = BillingManager(
            context = this,
            verifier = PlaySignaturePurchaseVerifier(BuildConfig.PLAY_BILLING_PUBLIC_KEY, ServerPurchaseVerifier(graph.data.payments)),
            accountId = store::playAccountId,
            sellsPass = store.sellsPass,
        ).also { it.startConnection() }
        // A purchase the server could not confirm while nobody was signed in is retried at each sign-in.
        graph.data.scope.launch(Dispatchers.Main) {
            graph.data.auth.state
                .map { (it as? AuthState.SignedIn)?.user?.id }
                .distinctUntilChanged()
                .filterNotNull()
                .collect { billing.refreshCatalogAndPurchases() }
        }
        // OpenStreetMap's tile policy requires an identifying user agent.
        Configuration.getInstance().userAgentValue = packageName
    }
}
