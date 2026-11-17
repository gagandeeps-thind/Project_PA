package osiris.fit.ui.wallet

import android.app.Activity
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import osiris.fit.platform.billing.BillingConnectionState
import osiris.fit.platform.billing.BillingFeedback
import osiris.fit.platform.billing.BillingProduct
import osiris.fit.platform.billing.BillingService
import osiris.fit.platform.billing.BillingState
import osiris.fit.platform.billing.PlayBillingCatalog
import osiris.fit.platform.billing.ProductKind
import osiris.fit.platform.billing.SubscriptionOffer
import osiris.fit.platform.billing.SubscriptionStatus
import osiris.fit.ui.common.SectionHeader
import osiris.fit.ui.design.FrostCard
import osiris.fit.ui.theme.OsirisColors

/**
 * Renders Google Play Billing subscriptions, one-time Mana Crystal packs, and entitlement status
 * inside a [LazyListScope]. Depends exclusively on the modular [BillingService] contract.
 */
fun LazyListScope.playStoreBillingItems(
    state: BillingState,
    billing: BillingService,
    activity: Activity?,
) {
    item(key = "play_billing_header") {
        SectionHeader(if (state.sellsPass) "Google Play Store & Osiris Pass" else "Mana Crystal Store")
    }
    state.feedback?.let { feedback ->
        item(key = "play_billing_feedback") {
            BillingFeedbackBanner(feedback = feedback, onDismiss = billing::clearFeedback)
        }
    }
    item(key = "play_subscription_status") {
        StoreStatusCard(state = state, onRefresh = billing::refreshCatalogAndPurchases)
    }
    subscriptionProductItems(state = state, billing = billing, activity = activity)
    oneTimeProductItems(state = state, billing = billing, activity = activity)
}

private fun LazyListScope.subscriptionProductItems(
    state: BillingState,
    billing: BillingService,
    activity: Activity?,
) {
    if (state.subscriptions.isEmpty()) return
    item(key = "play_subscriptions_header") {
        SectionHeader("Subscriptions")
    }
    items(state.subscriptions, key = { "sub_${it.productId}" }) { product ->
        // One pass at a time: while any pass is active, neither plan can be bought again here.
        val hasActiveSub = state.subscriptionStatus == SubscriptionStatus.ACTIVE ||
            state.subscriptionStatus == SubscriptionStatus.IN_GRACE_PERIOD
        SubscriptionProductCard(
            product = product,
            isSubscribed = state.activeSubscriptionProductId == product.productId && hasActiveSub,
            canBuy = !hasActiveSub && !state.purchasesUnavailable,
            onSelectOffer = { offer ->
                activity?.let { act ->
                    billing.launchPurchase(
                        activity = act,
                        productId = product.productId,
                        basePlanId = offer.basePlanId,
                        offerToken = offer.offerToken,
                    )
                }
            },
        )
    }
}

private fun LazyListScope.oneTimeProductItems(
    state: BillingState,
    billing: BillingService,
    activity: Activity?,
) {
    if (state.oneTimeProducts.isEmpty()) return
    item(key = "play_inapp_header") {
        SectionHeader(if (state.sellsPass) "Mana Crystals & Unlocks" else "Mana Crystals")
    }
    items(state.oneTimeProducts, key = { "inapp_${it.productId}" }) { product ->
        val alreadyOwned = product.kind == ProductKind.NON_CONSUMABLE_INAPP &&
            product.productId in state.ownedNonConsumables
        OneTimeProductCard(
            product = product,
            alreadyOwned = alreadyOwned,
            enabled = !alreadyOwned && !state.purchasesUnavailable,
            onBuy = {
                activity?.let { act ->
                    billing.launchPurchase(activity = act, productId = product.productId)
                }
            },
        )
    }
}

@Composable
private fun BillingFeedbackBanner(
    feedback: BillingFeedback,
    onDismiss: () -> Unit,
) {
    val accent = if (feedback.isError) OsirisColors.Warning else OsirisColors.Success
    FrostCard(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = feedback.userMessage,
                color = accent,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onDismiss) {
                Text("DISMISS")
            }
        }
    }
}

@Composable
private fun StoreStatusCard(
    state: BillingState,
    onRefresh: () -> Unit,
) {
    val links = LocalUriHandler.current
    val packageName = LocalContext.current.packageName
    val activePass = state.activeSubscriptionProductId?.takeIf {
        state.sellsPass && state.subscriptionStatus.let { s -> s == SubscriptionStatus.ACTIVE || s == SubscriptionStatus.IN_GRACE_PERIOD }
    }
    FrostCard(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        Column {
            Text(
                text = when {
                    state.purchasesUnavailable -> "PURCHASES TEMPORARILY UNAVAILABLE"
                    state.sellsPass -> subscriptionLabel(state.subscriptionStatus)
                    else -> "MANA CRYSTALS"
                },
                color = if (state.purchasesUnavailable) OsirisColors.Warning else subscriptionColor(state.subscriptionStatus),
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = when {
                    state.purchasesUnavailable ->
                        "Buying is paused while we can't confirm purchases. Nothing was added to your account, " +
                            "and Google Play refunds a purchase we can't confirm within 3 days."
                    state.sellsPass -> subscriptionDetail(state)
                    else -> connectionDetail(state.connectionState)
                },
                color = OsirisColors.Muted,
                style = MaterialTheme.typography.bodySmall,
            )
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = onRefresh, enabled = !state.isLoading) {
                Text(if (state.isLoading) "SYNCING..." else "RESTORE / REFRESH PLAY PURCHASES")
            }
            if (activePass != null) {
                TextButton(onClick = { links.openUri(PlayBillingCatalog.manageSubscriptionUrl(activePass, packageName)) }) {
                    Text("MANAGE SUBSCRIPTION IN GOOGLE PLAY")
                }
            }
        }
    }
}

private fun subscriptionLabel(status: SubscriptionStatus): String = when (status) {
    SubscriptionStatus.ACTIVE -> "OSIRIS PASS: ACTIVE"
    SubscriptionStatus.IN_GRACE_PERIOD -> "OSIRIS PASS: PAYMENT GRACE PERIOD"
    SubscriptionStatus.EXPIRED -> "OSIRIS PASS: EXPIRED"
    SubscriptionStatus.NONE -> "OSIRIS PASS: NOT SUBSCRIBED"
}

private fun subscriptionColor(status: SubscriptionStatus): Color = when (status) {
    SubscriptionStatus.ACTIVE -> OsirisColors.Success
    SubscriptionStatus.IN_GRACE_PERIOD -> OsirisColors.Warning
    SubscriptionStatus.EXPIRED -> OsirisColors.Warning
    SubscriptionStatus.NONE -> OsirisColors.Muted
}

private fun subscriptionDetail(state: BillingState): String = when (state.subscriptionStatus) {
    SubscriptionStatus.ACTIVE ->
        "Your subscription is verified and active."
    SubscriptionStatus.IN_GRACE_PERIOD ->
        "A renewal charge failed. Update your payment method in Google Play to keep uninterrupted access."
    SubscriptionStatus.EXPIRED ->
        "Your previous subscription has expired. Renew below to restore Osiris Pass perks."
    SubscriptionStatus.NONE -> connectionDetail(state.connectionState)
}

private fun connectionDetail(connectionState: BillingConnectionState): String = when (connectionState) {
    BillingConnectionState.CONNECTED ->
        "Connected to Google Play. Prices are localized for your Play Store region."
    BillingConnectionState.CONNECTING, BillingConnectionState.RECONNECTING ->
        "Connecting to Google Play Store..."
    BillingConnectionState.DISCONNECTED, BillingConnectionState.CLOSED ->
        "Google Play Store is not connected on this device."
}

@Composable
private fun SubscriptionProductCard(
    product: BillingProduct,
    isSubscribed: Boolean,
    canBuy: Boolean,
    onSelectOffer: (SubscriptionOffer) -> Unit,
) {
    FrostCard(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)) {
        Column {
            Text(product.title, style = MaterialTheme.typography.titleMedium)
            if (product.description.isNotBlank()) {
                Text(product.description, color = OsirisColors.Muted, style = MaterialTheme.typography.bodySmall)
            }
            Spacer(Modifier.height(8.dp))
            product.subscriptionOffers.forEach { offer ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = "${PlayBillingCatalog.planLabel(offer.billingPeriod)} • ${offer.formattedPrice}",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Button(
                        onClick = { onSelectOffer(offer) },
                        enabled = canBuy,
                    ) {
                        Text(if (isSubscribed) "ACTIVE" else "SUBSCRIBE")
                    }
                }
            }
        }
    }
}

@Composable
private fun OneTimeProductCard(
    product: BillingProduct,
    alreadyOwned: Boolean,
    enabled: Boolean,
    onBuy: () -> Unit,
) {
    FrostCard(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(product.title, style = MaterialTheme.typography.titleMedium)
                if (product.description.isNotBlank()) {
                    Text(product.description, color = OsirisColors.Muted, style = MaterialTheme.typography.bodySmall)
                }
            }
            Button(
                onClick = onBuy,
                enabled = enabled,
            ) {
                Text(if (alreadyOwned) "OWNED" else product.formattedPrice)
            }
        }
    }
}
