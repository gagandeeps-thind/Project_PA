# kotlinx.serialization: keep generated serializers for @Serializable models in shared/.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class com.osiris.shared.** {
    *** Companion;
}
-keepclasseswithmembers class com.osiris.shared.** {
    kotlinx.serialization.KSerializer serializer(...);
}
# Ktor and OkHttp reference optional platform classes.
-dontwarn org.slf4j.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
