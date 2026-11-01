# kotlinx.serialization: keep generated serializers for @Serializable models in shared/.
-keepattributes *Annotation*, InnerClasses, Signature, Exceptions
-dontnote kotlinx.serialization.**
-keepclassmembers class com.osiris.shared.** {
    *** Companion;
}
-keepclasseswithmembers class com.osiris.shared.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Google Play Billing Library: preserve AIDL IPC stubs, listener callbacks, and billing models
# so R8 shrinking/obfuscation never strips purchase updates or product details callbacks.
-keep class com.android.vending.billing.** { *; }
-keep class com.android.billingclient.api.** { *; }
-keepclassmembers class * implements com.android.billingclient.api.PurchasesUpdatedListener {
    public void onPurchasesUpdated(com.android.billingclient.api.BillingResult, java.util.List);
}
-keepclassmembers class * implements com.android.billingclient.api.BillingClientStateListener {
    public void onBillingSetupFinished(com.android.billingclient.api.BillingResult);
    public void onBillingServiceDisconnected();
}
-keepclassmembers class * implements com.android.billingclient.api.ProductDetailsResponseListener {
    public void onProductDetailsResponse(com.android.billingclient.api.BillingResult, java.util.List);
}
-keepclassmembers class * implements com.android.billingclient.api.PurchasesResponseListener {
    public void onQueryPurchasesResponse(com.android.billingclient.api.BillingResult, java.util.List);
}
-keepclassmembers class * implements com.android.billingclient.api.ConsumeResponseListener {
    public void onConsumeResponse(com.android.billingclient.api.BillingResult, java.lang.String);
}
-keepclassmembers class * implements com.android.billingclient.api.AcknowledgePurchaseResponseListener {
    public void onAcknowledgePurchaseResponse(com.android.billingclient.api.BillingResult);
}

# Keep Osiris Billing domain models, callbacks, and verification contracts.
-keep class com.osiris.player.platform.billing.** { *; }

# Ktor and OkHttp reference optional platform classes.
-dontwarn org.slf4j.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
