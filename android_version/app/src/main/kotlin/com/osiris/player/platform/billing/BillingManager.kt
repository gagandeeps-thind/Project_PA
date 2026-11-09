package com.osiris.player.platform.billing

import android.app.Activity
import android.content.Context
import com.android.billingclient.api.AcknowledgePurchaseParams
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClient.BillingResponseCode
import com.android.billingclient.api.BillingClient.ProductType
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.ConsumeParams
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.QueryPurchasesParams
import com.android.billingclient.api.acknowledgePurchase
import com.android.billingclient.api.consumePurchase
import com.android.billingclient.api.queryProductDetails
import com.android.billingclient.api.queryPurchasesAsync
import com.osiris.player.BuildConfig
import java.util.concurrent.ConcurrentHashMap
import kotlin.coroutines.CoroutineContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Manages the full Google Play Billing lifecycle for Osiris on Android:
 * - Connects to Google Play via [BillingClient] with pending-purchase support for one-time and prepaid plans.
 * - Automatically retries dropped connections with exponential backoff ([BillingErrorMapper.exponentialBackoffDelayMs]).
 * - Queries dynamic localized pricing globally for one-time products (`INAPP`) and subscriptions (`SUBS`).
 * - Launches the Google Play purchase sheet (`launchBillingFlow`) with base plan and offer tokens.
 * - Verifies purchase authenticity via [PurchaseVerifier], then either consumes consumable packs
 *   (`consumePurchase`) or acknowledges non-consumables and subscriptions (`acknowledgePurchase`)
 *   within Google Play's required window.
 * - Tracks active, grace-period, and expired subscription entitlements in [state].
 */
class BillingManager(
    context: Context,
    private val verifier: PurchaseVerifier = PlaySignaturePurchaseVerifier(BuildConfig.PLAY_BILLING_PUBLIC_KEY),
    private val onConsumableGranted: (productId: String, crystals: Int, purchaseToken: String) -> Unit = { _, _, _ -> },
    coroutineContext: CoroutineContext = SupervisorJob() + Dispatchers.Main.immediate,
) : BillingService, PurchasesUpdatedListener, BillingClientStateListener {

    private val appContext: Context = context.applicationContext
    private val scope: CoroutineScope = CoroutineScope(coroutineContext)
    private val _state = MutableStateFlow(BillingState())
    override val state: StateFlow<BillingState> = _state.asStateFlow()

    private val productDetailsCache = ConcurrentHashMap<String, ProductDetails>()
    private var reconnectJob: Job? = null
    private var retryAttempt: Int = 0
    private var hadActiveSubscription: Boolean = false
    private var inGracePeriod: Boolean = false

    private val billingClient: BillingClient = BillingClient.newBuilder(appContext)
        .setListener(this)
        .enablePendingPurchases(
            PendingPurchasesParams.newBuilder()
                .enableOneTimeProducts()
                .enablePrepaidPlans()
                .build(),
        )
        .build()

    override fun startConnection() {
        val current = _state.value.connectionState
        when {
            current == BillingConnectionState.CLOSED || current == BillingConnectionState.CONNECTING -> Unit
            billingClient.isReady -> {
                _state.update { it.copy(connectionState = BillingConnectionState.CONNECTED) }
                refreshCatalogAndPurchases()
            }
            else -> {
                _state.update { it.copy(connectionState = BillingConnectionState.CONNECTING, isLoading = true) }
                billingClient.startConnection(this)
            }
        }
    }

    override fun onBillingSetupFinished(billingResult: BillingResult) {
        if (billingResult.responseCode == BillingResponseCode.OK) {
            retryAttempt = 0
            reconnectJob?.cancel()
            _state.update { it.copy(connectionState = BillingConnectionState.CONNECTED, feedback = null) }
            refreshCatalogAndPurchases()
        } else if (BillingErrorMapper.isRetriable(billingResult.responseCode)) {
            scheduleReconnect(billingResult)
        } else {
            val feedback = BillingErrorMapper.fromResponseCode(billingResult.responseCode, billingResult.debugMessage)
            _state.update {
                it.copy(
                    connectionState = BillingConnectionState.DISCONNECTED,
                    isLoading = false,
                    feedback = feedback,
                )
            }
        }
    }

    override fun onBillingServiceDisconnected() {
        if (_state.value.connectionState != BillingConnectionState.CLOSED) {
            scheduleReconnect(null)
        }
    }

    private fun scheduleReconnect(lastResult: BillingResult?) {
        if (retryAttempt >= BillingErrorMapper.MAX_RETRY_ATTEMPTS) {
            val feedback = lastResult?.let {
                BillingErrorMapper.fromResponseCode(it.responseCode, it.debugMessage)
            } ?: BillingErrorMapper.fromResponseCode(BillingResponseCode.SERVICE_UNAVAILABLE)
            _state.update {
                it.copy(
                    connectionState = BillingConnectionState.DISCONNECTED,
                    isLoading = false,
                    feedback = feedback,
                )
            }
        } else {
            val currentAttempt = retryAttempt
            retryAttempt += 1
            val delayMs = BillingErrorMapper.exponentialBackoffDelayMs(currentAttempt)
            _state.update { it.copy(connectionState = BillingConnectionState.RECONNECTING) }
            reconnectJob?.cancel()
            reconnectJob = scope.launch {
                delay(delayMs)
                if (!billingClient.isReady && _state.value.connectionState != BillingConnectionState.CLOSED) {
                    billingClient.startConnection(this@BillingManager)
                }
            }
        }
    }

    override fun refreshCatalogAndPurchases() {
        if (!billingClient.isReady) {
            startConnection()
        } else {
            scope.launch {
                _state.update { it.copy(isLoading = true) }
                val inAppProducts = queryProductDetailsForType(PlayBillingCatalog.INAPP_PRODUCT_IDS, ProductType.INAPP)
                val subProducts = queryProductDetailsForType(PlayBillingCatalog.SUBSCRIPTION_PRODUCT_IDS, ProductType.SUBS)
                _state.update {
                    it.copy(
                        oneTimeProducts = inAppProducts,
                        subscriptions = subProducts,
                    )
                }
                refreshActivePurchasesInternal()
                _state.update { it.copy(isLoading = false) }
            }
        }
    }

    private suspend fun queryProductDetailsForType(
        productIds: List<String>,
        productType: String,
    ): List<BillingProduct> {
        if (productIds.isEmpty()) return emptyList()
        val productList = productIds.map { id ->
            QueryProductDetailsParams.Product.newBuilder()
                .setProductId(id)
                .setProductType(productType)
                .build()
        }
        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(productList)
            .build()
        val result = billingClient.queryProductDetails(params)
        return if (result.billingResult.responseCode != BillingResponseCode.OK) {
            val feedback = BillingErrorMapper.fromResponseCode(
                result.billingResult.responseCode,
                result.billingResult.debugMessage,
            )
            _state.update { it.copy(feedback = feedback) }
            emptyList()
        } else {
            val detailsList = result.productDetailsList.orEmpty()
            detailsList.forEach { details -> productDetailsCache[details.productId] = details }
            detailsList.mapNotNull(::mapProductDetails)
        }
    }

    private fun mapProductDetails(details: ProductDetails): BillingProduct? {
        val kind = PlayBillingCatalog.kindOf(details.productId)
        return if (details.productType == ProductType.SUBS) {
            mapSubscriptionProductDetails(details, kind)
        } else {
            mapOneTimeProductDetails(details, kind)
        }
    }

    private fun mapSubscriptionProductDetails(details: ProductDetails, kind: ProductKind): BillingProduct? {
        val offers = details.subscriptionOfferDetails.orEmpty().mapNotNull { offer ->
            val phase = offer.pricingPhases.pricingPhaseList.lastOrNull()
            phase?.let {
                SubscriptionOffer(
                    basePlanId = offer.basePlanId,
                    offerId = offer.offerId,
                    offerToken = offer.offerToken,
                    formattedPrice = it.formattedPrice,
                    priceAmountMicros = it.priceAmountMicros,
                    priceCurrencyCode = it.priceCurrencyCode,
                    billingPeriod = it.billingPeriod,
                    offerTags = offer.offerTags,
                )
            }
        }
        return offers.firstOrNull()?.let { primaryOffer ->
            BillingProduct(
                productId = details.productId,
                kind = kind,
                title = details.title,
                description = details.description,
                formattedPrice = primaryOffer.formattedPrice,
                priceAmountMicros = primaryOffer.priceAmountMicros,
                priceCurrencyCode = primaryOffer.priceCurrencyCode,
                subscriptionOffers = offers,
            )
        }
    }

    private fun mapOneTimeProductDetails(details: ProductDetails, kind: ProductKind): BillingProduct? =
        details.oneTimePurchaseOfferDetails?.let { oneTime ->
            BillingProduct(
                productId = details.productId,
                kind = kind,
                title = details.title,
                description = details.description,
                formattedPrice = oneTime.formattedPrice,
                priceAmountMicros = oneTime.priceAmountMicros,
                priceCurrencyCode = oneTime.priceCurrencyCode,
            )
        }

    override fun launchPurchase(
        activity: Activity,
        productId: String,
        basePlanId: String?,
        offerToken: String?,
        obfuscatedAccountId: String?,
    ) {
        val details = productDetailsCache[productId]
        val productParams = details?.let { buildProductDetailsParams(it, basePlanId, offerToken) }
        when {
            !billingClient.isReady -> {
                _state.update {
                    it.copy(feedback = BillingErrorMapper.fromResponseCode(BillingResponseCode.SERVICE_DISCONNECTED))
                }
                startConnection()
            }
            details == null -> {
                _state.update {
                    it.copy(
                        feedback = BillingErrorMapper.fromResponseCode(
                            BillingResponseCode.ITEM_UNAVAILABLE,
                            "Product $productId is not loaded from Google Play.",
                        ),
                    )
                }
            }
            productParams == null -> {
                _state.update {
                    it.copy(
                        feedback = BillingErrorMapper.fromResponseCode(
                            BillingResponseCode.DEVELOPER_ERROR,
                            "Missing subscription offer token for $productId.",
                        ),
                    )
                }
            }
            else -> {
                val flowBuilder = BillingFlowParams.newBuilder()
                    .setProductDetailsParamsList(listOf(productParams))
                if (!obfuscatedAccountId.isNullOrBlank()) {
                    flowBuilder.setObfuscatedAccountId(obfuscatedAccountId)
                }
                val launchResult = billingClient.launchBillingFlow(activity, flowBuilder.build())
                if (launchResult.responseCode != BillingResponseCode.OK) {
                    val feedback = BillingErrorMapper.fromResponseCode(
                        launchResult.responseCode,
                        launchResult.debugMessage,
                    )
                    _state.update { it.copy(feedback = feedback) }
                }
            }
        }
    }

    private fun buildProductDetailsParams(
        details: ProductDetails,
        basePlanId: String?,
        explicitOfferToken: String?,
    ): BillingFlowParams.ProductDetailsParams? {
        val builder = BillingFlowParams.ProductDetailsParams.newBuilder()
            .setProductDetails(details)
        if (details.productType == ProductType.SUBS) {
            val resolvedToken = explicitOfferToken
                ?: details.subscriptionOfferDetails
                    ?.firstOrNull { basePlanId == null || it.basePlanId == basePlanId }
                    ?.offerToken
                ?: return null
            builder.setOfferToken(resolvedToken)
        }
        return builder.build()
    }

    override fun onPurchasesUpdated(billingResult: BillingResult, purchases: List<Purchase>?) {
        when (billingResult.responseCode) {
            BillingResponseCode.OK -> {
                val updatedPurchases = purchases.orEmpty()
                if (updatedPurchases.isNotEmpty()) {
                    scope.launch {
                        updatedPurchases.forEach { purchase -> handlePurchase(purchase) }
                        refreshActivePurchasesInternal()
                    }
                }
            }
            BillingResponseCode.ITEM_ALREADY_OWNED -> {
                val feedback = BillingErrorMapper.fromResponseCode(
                    billingResult.responseCode,
                    billingResult.debugMessage,
                )
                _state.update { it.copy(feedback = feedback) }
                scope.launch { refreshActivePurchasesInternal() }
            }
            else -> {
                val feedback = BillingErrorMapper.fromResponseCode(
                    billingResult.responseCode,
                    billingResult.debugMessage,
                )
                _state.update { it.copy(feedback = feedback) }
            }
        }
    }

    private suspend fun handlePurchase(purchase: Purchase): BillingPurchaseRecord? =
        when (purchase.purchaseState) {
            Purchase.PurchaseState.PENDING -> {
                _state.update {
                    it.copy(
                        feedback = BillingFeedback(
                            code = null,
                            userMessage = "Purchase is pending payment confirmation. " +
                                "Entitlements will unlock automatically once completed.",
                            isError = false,
                        ),
                    )
                }
                toPurchaseRecord(purchase, PurchaseEntitlementStatus.PENDING)
            }
            Purchase.PurchaseState.PURCHASED -> verifyAndFulfillPurchase(purchase)
            else -> null
        }

    private suspend fun verifyAndFulfillPurchase(purchase: Purchase): BillingPurchaseRecord {
        val verified = verifier.verify(
            packageName = appContext.packageName,
            signedData = purchase.originalJson,
            signature = purchase.signature,
            purchaseToken = purchase.purchaseToken,
            productIds = purchase.products,
        )
        return if (!verified) {
            _state.update {
                it.copy(
                    feedback = BillingFeedback(
                        code = BillingErrorCode.VERIFICATION_FAILED,
                        userMessage = "We couldn't confirm this purchase yet, and you won't be charged again. Pull down to retry.",
                        isError = true,
                    ),
                )
            }
            toPurchaseRecord(purchase, PurchaseEntitlementStatus.FAILED_VERIFICATION)
        } else if (purchase.products.any(PlayBillingCatalog::isConsumable)) {
            consumeVerifiedPurchase(purchase)
        } else {
            acknowledgeVerifiedPurchase(purchase)
        }
    }

    private suspend fun consumeVerifiedPurchase(purchase: Purchase): BillingPurchaseRecord {
        val consumeParams = ConsumeParams.newBuilder()
            .setPurchaseToken(purchase.purchaseToken)
            .build()
        val consumeResult = billingClient.consumePurchase(consumeParams)
        if (consumeResult.billingResult.responseCode == BillingResponseCode.OK) {
            val totalCrystals = purchase.products.sumOf(PlayBillingCatalog::crystalsForProduct)
            purchase.products.forEach { productId ->
                val crystals = PlayBillingCatalog.crystalsForProduct(productId)
                onConsumableGranted(productId, crystals, purchase.purchaseToken)
            }
            _state.update {
                it.copy(
                    grantedConsumableCrystals = it.grantedConsumableCrystals + totalCrystals,
                    feedback = BillingFeedback(
                        code = null,
                        userMessage = "Purchase complete! +$totalCrystals Mana Crystals added.",
                        isError = false,
                    ),
                )
            }
        } else {
            val feedback = BillingErrorMapper.fromResponseCode(
                consumeResult.billingResult.responseCode,
                consumeResult.billingResult.debugMessage,
            )
            _state.update { it.copy(feedback = feedback) }
        }
        return toPurchaseRecord(purchase, PurchaseEntitlementStatus.VERIFIED_AND_GRANTED, acknowledgedOverride = true)
    }

    private suspend fun acknowledgeVerifiedPurchase(purchase: Purchase): BillingPurchaseRecord {
        var acknowledged = purchase.isAcknowledged
        if (!acknowledged) {
            val ackParams = AcknowledgePurchaseParams.newBuilder()
                .setPurchaseToken(purchase.purchaseToken)
                .build()
            val ackResult = billingClient.acknowledgePurchase(ackParams)
            if (ackResult.responseCode == BillingResponseCode.OK) {
                acknowledged = true
                _state.update {
                    it.copy(
                        feedback = BillingFeedback(
                            code = null,
                            userMessage = "Entitlement activated and acknowledged with Google Play.",
                            isError = false,
                        ),
                    )
                }
            } else {
                val feedback = BillingErrorMapper.fromResponseCode(ackResult.responseCode, ackResult.debugMessage)
                _state.update { it.copy(feedback = feedback) }
            }
        }
        return toPurchaseRecord(purchase, PurchaseEntitlementStatus.VERIFIED_AND_GRANTED, acknowledged)
    }

    private suspend fun refreshActivePurchasesInternal() {
        val inAppPurchases = queryPurchasesForType(ProductType.INAPP)
        val subPurchases = queryPurchasesForType(ProductType.SUBS)

        val processedInApp = inAppPurchases.mapNotNull { handlePurchase(it) }
        val processedSubs = subPurchases.mapNotNull { handlePurchase(it) }

        val ownedNonConsumables = processedInApp
            .filter { it.status == PurchaseEntitlementStatus.VERIFIED_AND_GRANTED }
            .flatMap { it.productIds }
            .filter { PlayBillingCatalog.kindOf(it) == ProductKind.NON_CONSUMABLE_INAPP }
            .toSet()

        if (processedSubs.any { it.status == PurchaseEntitlementStatus.VERIFIED_AND_GRANTED }) {
            hadActiveSubscription = true
        }
        val subStatus = BillingErrorMapper.resolveSubscriptionStatus(
            activeSubscriptions = processedSubs,
            hadPreviousSubscription = hadActiveSubscription,
            inGracePeriod = inGracePeriod,
        )
        val activeSubProduct = processedSubs
            .firstOrNull { it.status == PurchaseEntitlementStatus.VERIFIED_AND_GRANTED }
            ?.productIds
            ?.firstOrNull()

        _state.update {
            it.copy(
                activePurchases = processedInApp + processedSubs,
                ownedNonConsumables = ownedNonConsumables,
                subscriptionStatus = subStatus,
                activeSubscriptionProductId = activeSubProduct,
            )
        }
    }

    private suspend fun queryPurchasesForType(productType: String): List<Purchase> {
        val params = QueryPurchasesParams.newBuilder()
            .setProductType(productType)
            .build()
        val result = billingClient.queryPurchasesAsync(params)
        return if (result.billingResult.responseCode == BillingResponseCode.OK) {
            result.purchasesList
        } else {
            emptyList()
        }
    }

    private fun toPurchaseRecord(
        purchase: Purchase,
        status: PurchaseEntitlementStatus,
        acknowledgedOverride: Boolean = purchase.isAcknowledged,
    ): BillingPurchaseRecord = BillingPurchaseRecord(
        orderId = purchase.orderId,
        productIds = purchase.products,
        purchaseToken = purchase.purchaseToken,
        purchaseTimeMillis = purchase.purchaseTime,
        isAcknowledged = acknowledgedOverride,
        isAutoRenewing = purchase.isAutoRenewing,
        status = status,
    )

    override fun updateSubscriptionGracePeriod(inGracePeriod: Boolean) {
        this.inGracePeriod = inGracePeriod
        _state.update { current ->
            val subRecords = current.activePurchases.filter { record ->
                record.productIds.any { id -> PlayBillingCatalog.kindOf(id) == ProductKind.SUBSCRIPTION }
            }
            current.copy(
                subscriptionStatus = BillingErrorMapper.resolveSubscriptionStatus(
                    activeSubscriptions = subRecords,
                    hadPreviousSubscription = hadActiveSubscription,
                    inGracePeriod = inGracePeriod,
                ),
            )
        }
    }

    override fun clearFeedback() {
        _state.update { it.copy(feedback = null) }
    }

    override fun endConnection() {
        reconnectJob?.cancel()
        _state.update { it.copy(connectionState = BillingConnectionState.CLOSED) }
        if (billingClient.isReady) {
            billingClient.endConnection()
        }
        scope.cancel()
    }
}
