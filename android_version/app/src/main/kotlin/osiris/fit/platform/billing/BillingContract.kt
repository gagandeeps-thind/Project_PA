package osiris.fit.platform.billing

import android.app.Activity
import kotlinx.coroutines.flow.StateFlow

/**
 * Product catalog for Google Play Store in-app purchases and subscriptions.
 *
 * Product IDs and subscription base plan IDs match the entries configured under
 * Google Play Console -> Monetize with Play -> Products.
 */
object PlayBillingCatalog {
    // Consumable one-time products (Mana Crystal packs; consumed via consumeAsync so players can buy again).
    const val PRODUCT_CRYSTALS_STARTER = "osiris_crystals_starter"
    const val PRODUCT_CRYSTALS_ADVENTURER = "osiris_crystals_adventurer"
    const val PRODUCT_CRYSTALS_CHAMPION = "osiris_crystals_champion"

    // Non-consumable one-time product (permanent account unlock; acknowledged once via acknowledgePurchase).
    const val PRODUCT_FOUNDER_PACK = "osiris_founder_pack"

    // Subscriptions (recurring entitlements; acknowledged within Google Play's 3-day window).
    const val SUB_OSIRIS_PASS_MONTHLY = "osiris_pass_monthly"
    const val SUB_OSIRIS_PASS_ANNUAL = "osiris_pass_annual"

    // Subscription base plan IDs configured in Google Play Console.
    const val BASE_PLAN_MONTHLY = "monthly-base"
    const val BASE_PLAN_ANNUAL = "annual-base"

    val CONSUMABLE_PRODUCT_IDS: Set<String> = setOf(
        PRODUCT_CRYSTALS_STARTER,
        PRODUCT_CRYSTALS_ADVENTURER,
        PRODUCT_CRYSTALS_CHAMPION,
    )

    val NON_CONSUMABLE_PRODUCT_IDS: Set<String> = setOf(
        PRODUCT_FOUNDER_PACK,
    )

    val INAPP_PRODUCT_IDS: List<String> = listOf(
        PRODUCT_CRYSTALS_STARTER,
        PRODUCT_CRYSTALS_ADVENTURER,
        PRODUCT_CRYSTALS_CHAMPION,
        PRODUCT_FOUNDER_PACK,
    )

    val SUBSCRIPTION_PRODUCT_IDS: List<String> = listOf(
        SUB_OSIRIS_PASS_MONTHLY,
        SUB_OSIRIS_PASS_ANNUAL,
    )

    /** Resolves how a Google Play product ID must be fulfilled and acknowledged. */
    fun kindOf(productId: String): ProductKind = when (productId) {
        in CONSUMABLE_PRODUCT_IDS -> ProductKind.CONSUMABLE_INAPP
        in NON_CONSUMABLE_PRODUCT_IDS -> ProductKind.NON_CONSUMABLE_INAPP
        in SUBSCRIPTION_PRODUCT_IDS -> ProductKind.SUBSCRIPTION
        else -> if (productId.contains("pass") || productId.contains("sub")) {
            ProductKind.SUBSCRIPTION
        } else {
            ProductKind.NON_CONSUMABLE_INAPP
        }
    }

    /** True when the product must be consumed via `consumeAsync` to allow repeat purchases. */
    fun isConsumable(productId: String): Boolean = kindOf(productId) == ProductKind.CONSUMABLE_INAPP

    /** One-time products the store queries: crystal packs, plus the Founder Pack only when [sellsPass]. */
    fun inAppProductIds(sellsPass: Boolean): List<String> =
        if (sellsPass) INAPP_PRODUCT_IDS else INAPP_PRODUCT_IDS.filter { it in CONSUMABLE_PRODUCT_IDS }

    /** Subscriptions the store queries: Osiris Pass only when [sellsPass] (`features.passProducts`). */
    fun subscriptionProductIds(sellsPass: Boolean): List<String> = if (sellsPass) SUBSCRIPTION_PRODUCT_IDS else emptyList()

    /** `P1M` -> `Monthly`; the plan label players see instead of the base plan id. */
    fun planLabel(billingPeriod: String): String = when (billingPeriod) {
        "P1W" -> "Weekly"
        "P1M" -> "Monthly"
        "P3M" -> "Every 3 months"
        "P6M" -> "Every 6 months"
        "P1Y" -> "Yearly"
        else -> billingPeriod
    }

    /** Google Play's own page for managing (or cancelling) one subscription. */
    fun manageSubscriptionUrl(productId: String, packageName: String): String =
        "https://play.google.com/store/account/subscriptions?sku=$productId&package=$packageName"
}

/** Category of Google Play product determining its post-purchase lifecycle. */
enum class ProductKind {
    /** Consumable one-time purchase (`consumeAsync`). */
    CONSUMABLE_INAPP,

    /** Non-consumable one-time entitlement (`acknowledgePurchase`). */
    NON_CONSUMABLE_INAPP,

    /** Recurring or prepaid subscription (`acknowledgePurchase`). */
    SUBSCRIPTION,
}

/** Connection lifecycle state of the underlying Google Play `BillingClient`. */
enum class BillingConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    RECONNECTING,
    CLOSED,
}

/**
 * Lifecycle state of the player's subscription entitlement.
 *
 * - [NONE]: No subscription has been purchased on this account.
 * - [ACTIVE]: Subscription is verified, acknowledged, and in good standing.
 * - [IN_GRACE_PERIOD]: Renewal payment failed; player retains access during the Play Store grace period.
 * - [EXPIRED]: Subscription period ended without renewal and entitlement is no longer active.
 */
enum class SubscriptionStatus {
    NONE,
    ACTIVE,
    IN_GRACE_PERIOD,
    EXPIRED,
}

/**
 * Localized pricing and offer token for a subscription base plan or promotional offer.
 *
 * @property basePlanId Base plan identifier in Google Play Console (e.g., `monthly-base`).
 * @property offerId Optional promotional/introductory offer identifier, or null for the base plan price.
 * @property offerToken Token required by `BillingFlowParams.ProductDetailsParams.Builder.setOfferToken`.
 * @property formattedPrice Currency-formatted localized price string from Google Play (e.g., `$4.99`, `€4,99`).
 * @property priceAmountMicros Price in micro-units (1,000,000 micros = 1 currency unit).
 * @property priceCurrencyCode ISO 4217 currency code (e.g., `USD`, `EUR`, `JPY`).
 * @property billingPeriod ISO 8601 billing period (e.g., `P1M` for monthly, `P1Y` for yearly).
 * @property offerTags Tags attached to this base plan or offer in Play Console.
 */
data class SubscriptionOffer(
    val basePlanId: String,
    val offerId: String?,
    val offerToken: String,
    val formattedPrice: String,
    val priceAmountMicros: Long,
    val priceCurrencyCode: String,
    val billingPeriod: String,
    val offerTags: List<String> = emptyList(),
)

/**
 * UI-ready representation of a Google Play in-app product or subscription with localized pricing.
 */
data class BillingProduct(
    val productId: String,
    val kind: ProductKind,
    val title: String,
    val description: String,
    val formattedPrice: String,
    val priceAmountMicros: Long,
    val priceCurrencyCode: String,
    val subscriptionOffers: List<SubscriptionOffer> = emptyList(),
)

/** Verification and fulfillment outcome for a single purchase transaction. */
enum class PurchaseEntitlementStatus {
    PENDING,
    VERIFIED_AND_GRANTED,
    FAILED_VERIFICATION,
}

/** Immutable snapshot of a Google Play purchase processed by the billing layer. */
data class BillingPurchaseRecord(
    val orderId: String?,
    val productIds: List<String>,
    val purchaseToken: String,
    val purchaseTimeMillis: Long,
    val isAcknowledged: Boolean,
    val isAutoRenewing: Boolean,
    val status: PurchaseEntitlementStatus,
)

/** Standard billing error categories surfaced to the UI layer. */
enum class BillingErrorCode {
    USER_CANCELED,
    ITEM_ALREADY_OWNED,
    SERVICE_UNAVAILABLE,
    DEVELOPER_ERROR,
    BILLING_UNAVAILABLE,
    ITEM_UNAVAILABLE,
    NETWORK_ERROR,
    SERVICE_DISCONNECTED,
    VERIFICATION_FAILED,

    /** The Osiris server is not taking purchases right now (503, e.g. Play credentials not configured). */
    PURCHASES_UNAVAILABLE,
    UNKNOWN,
}

/** User-facing status or error message produced by a billing operation. */
data class BillingFeedback(
    val code: BillingErrorCode?,
    val userMessage: String,
    val isError: Boolean,
)

/**
 * Complete observable state of Google Play Billing for the UI layer.
 *
 * @property sellsPass Osiris Pass and the Founder Pack are offered (`features.passProducts`).
 * @property purchasesUnavailable the Osiris server refused to verify (503): buying is paused, nothing was granted.
 */
data class BillingState(
    val connectionState: BillingConnectionState = BillingConnectionState.DISCONNECTED,
    val oneTimeProducts: List<BillingProduct> = emptyList(),
    val subscriptions: List<BillingProduct> = emptyList(),
    val activePurchases: List<BillingPurchaseRecord> = emptyList(),
    val ownedNonConsumables: Set<String> = emptySet(),
    val sellsPass: Boolean = false,
    val purchasesUnavailable: Boolean = false,
    val subscriptionStatus: SubscriptionStatus = SubscriptionStatus.NONE,
    val activeSubscriptionProductId: String? = null,
    val isLoading: Boolean = false,
    val feedback: BillingFeedback? = null,
)

/**
 * Modular boundary between Jetpack Compose UI screens and the Google Play Billing client.
 *
 * Screens observe [state] and invoke high-level actions without importing `com.android.billingclient.api.*`.
 */
interface BillingService {
    val state: StateFlow<BillingState>

    /** Connects to Google Play Billing if not already connected and loads the product catalog. */
    fun startConnection()

    /** Re-queries localized product details and active purchases/subscriptions from Google Play. */
    fun refreshCatalogAndPurchases()

    /**
     * Launches the Google Play purchase sheet for a one-time product or subscription.
     *
     * @param activity Foreground host activity required by `BillingClient.launchBillingFlow`.
     * @param productId Target product or subscription ID from [PlayBillingCatalog].
     * @param basePlanId Optional subscription base plan ID (e.g., `monthly-base`).
     * @param offerToken Optional subscription offer token (resolved from [basePlanId] if omitted).
     * @param obfuscatedAccountId Hashed player id the server checks the purchase against; defaults to
     *   the signed-in player's (`StoreSupport.playAccountId`). With no player signed in nothing is launched.
     */
    fun launchPurchase(
        activity: Activity,
        productId: String,
        basePlanId: String? = null,
        offerToken: String? = null,
        obfuscatedAccountId: String? = null,
    )

    /** Updates whether an active subscription is currently in a Play Store payment grace period. */
    fun updateSubscriptionGracePeriod(inGracePeriod: Boolean)

    /** Dismisses the current user-facing [BillingFeedback] banner. */
    fun clearFeedback()

    /** Releases the underlying `BillingClient` connection when the process or owner terminates. */
    fun endConnection()
}

