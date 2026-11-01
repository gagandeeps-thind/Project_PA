# Google Play Store Release & Billing Guide

Step-by-step runbook for building the signed release Android App Bundle (`.aab`), configuring Google Play Billing products and subscriptions, and publishing to Google Play Console's **Internal Testing** and **Closed Testing** tracks.

---

## 1. Package & SDK Configuration Summary

| Setting | Value | Source |
|---|---|---|
| `applicationId` | `com.osiris.player` | `android_version/app/build.gradle.kts` |
| `minSdk` | `26` (Android 8.0) | `gradle/libs.versions.toml` |
| `targetSdk` / `compileSdk` | `36` (exceeds Google Play Target API 34+ requirement) | `gradle/libs.versions.toml` |
| `versionCode` | Default `1` (`-Posiris.versionCode=<N>` or `OSIRIS_VERSION_CODE`) | `android_version/app/build.gradle.kts` |
| `versionName` | Default `1.0.0` (`-Posiris.versionName=<X.Y.Z>` or `OSIRIS_VERSION_NAME`) | `android_version/app/build.gradle.kts` |
| Billing Library | `com.android.billingclient:billing-ktx:7.1.1` | `gradle/libs.versions.toml` |

---

## 2. How to Generate an Upload Keystore & Build the Signed `.aab` via CLI

### Step 2.1 — Generate the Upload Keystore (Once)

Run `keytool` (bundled in the JDK / Android Studio JBR) from the repository root to generate a 2048-bit RSA PKCS12 upload keystore:

```bash
keytool -genkeypair -v \
  -storetype PKCS12 \
  -keystore android_version/release-upload-keystore.jks \
  -alias osiris-upload \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -dname "CN=Osiris Mobile, OU=Engineering, O=Osiris, L=Toronto, ST=ON, C=CA"
```

> **Security Note:** All `*.jks`, `*.keystore`, `*.p12`, `key.properties`, and `keystore.properties` files are listed in `.gitignore` and guarded by `.claude/hooks/gate.sh`. Store the `.jks` file and its passwords in your team password manager / CI secret store.

### Step 2.2 — Configure Signing Credentials

**Option A — Local properties file (git-ignored):**

Copy `keystore.properties.template` to `keystore.properties` in the repository root and populate your credentials:

```bash
cp keystore.properties.template keystore.properties
```

```properties
storeFile=android_version/release-upload-keystore.jks
storePassword=<YOUR_KEYSTORE_PASSWORD>
keyAlias=osiris-upload
keyPassword=<YOUR_KEY_PASSWORD>
```

**Option B — Environment variables (CI/CD):**

```bash
export OSIRIS_KEYSTORE_FILE="android_version/release-upload-keystore.jks"
export OSIRIS_KEYSTORE_PASSWORD="<YOUR_KEYSTORE_PASSWORD>"
export OSIRIS_KEY_ALIAS="osiris-upload"
export OSIRIS_KEY_PASSWORD="<YOUR_KEY_PASSWORD>"
export OSIRIS_PLAY_BILLING_PUBLIC_KEY="<BASE64_RSA_KEY_FROM_PLAY_CONSOLE>"
```

### Step 2.3 — Build the Signed Release `.aab`

From the repository root, run:

```bash
# macOS / Linux / Git Bash
./gradlew :android_version:app:bundleRelease \
  -Posiris.env=prod \
  -Posiris.versionCode=1 \
  -Posiris.versionName=1.0.0

# Windows PowerShell (quote -P flags with dots or use --project-prop)
.\gradlew.bat :android_version:app:bundleRelease --project-prop osiris.env=prod --project-prop osiris.versionCode=1 --project-prop osiris.versionName=1.0.0
```

**Output Artifacts:**
- Signed Android App Bundle:
  `android_version/app/build/outputs/bundle/release/app-release.aab`
- R8 deobfuscation mapping file (upload to Play Console for readable crash stack traces):
  `android_version/app/build/outputs/mapping/release/mapping.txt`

### Step 2.4 — Verify the `.aab` Signature

```bash
jarsigner -verify -verbose -certs android_version/app/build/outputs/bundle/release/app-release.aab
```

---

## 3. Google Play Console Setup: Products & Subscriptions

> **Prerequisite:** Google Play Console requires at least one `.aab` that declares `<uses-permission android:name="com.android.vending.BILLING" />` and the Play Billing Library to be uploaded to a track (e.g. Internal Testing) before unlocking the **Monetize with Play** product creation screens.

### Step 3.1 — Copy the Play Licensing Public Key

1. In Google Play Console, select your app (`com.osiris.player`).
2. Navigate to **Monetize with Play** -> **Monetization setup**.
3. Copy the Base64-encoded RSA public key under **Licensing**.
4. Set it in `config/environments/local.properties` (`billing.playPublicKey=<KEY>`) or export `OSIRIS_PLAY_BILLING_PUBLIC_KEY=<KEY>` in CI so `PlaySignaturePurchaseVerifier` verifies purchase receipts cryptographically on-device.

### Step 3.2 — Create One-Time In-App Products (`Monetize with Play` -> `Products` -> `In-app products`)

Create and **Activate** each of the following product IDs (matching `PlayBillingCatalog` in `BillingContract.kt`):

| Product ID | Type in App | Name | Suggested Base Price (USD) | Notes |
|---|---|---|---|---|
| `osiris_crystals_starter` | Consumable (`consumeAsync`) | Starter Pouch (500 Mana Crystals) | $4.99 | Multi-quantity optional; Play auto-converts global prices |
| `osiris_crystals_adventurer` | Consumable (`consumeAsync`) | Adventurer's Cache (1,200 Mana Crystals) | $9.99 | Multi-quantity optional; Play auto-converts global prices |
| `osiris_crystals_champion` | Consumable (`consumeAsync`) | Champion's Hoard (2,600 Mana Crystals) | $19.99 | Multi-quantity optional; Play auto-converts global prices |
| `osiris_founder_pack` | Non-consumable (`acknowledgePurchase`) | Founder's Emblem & Permanent Course Slot | $14.99 | Permanent account unlock |

For each product:
1. Click **Create product**, enter the exact **Product ID**, **Name**, and **Description**.
2. Under **Price**, click **Set price**, enter the default price, select **All countries / regions** to automatically calculate localized pricing + taxes globally, and click **Apply prices**.
3. Click **Save** and then **Activate**.

### Step 3.3 — Create Subscriptions & Base Plans (`Monetize with Play` -> `Products` -> `Subscriptions`)

Create and **Activate** the following subscriptions and base plans:

| Subscription Product ID | Base Plan ID | Billing Period | Renewal Type | Grace Period | Account Hold |
|---|---|---|---|---|---|
| `osiris_pass_monthly` | `monthly-base` | Monthly (`P1M`) | Auto-renewing | 7 days | 30 days |
| `osiris_pass_annual` | `annual-base` | Yearly (`P1Y`) | Auto-renewing | 7 days | 30 days |

For each subscription:
1. Click **Create subscription**, enter the exact **Product ID** (`osiris_pass_monthly` or `osiris_pass_annual`) and user-facing name.
2. Click **Add base plan**:
   - Enter the exact **Base plan ID** (`monthly-base` or `annual-base`).
   - Select **Auto-renewing**.
   - Configure **Billing period** (Monthly or Yearly), **Grace period** (`7 days`), and **Account hold** (`30 days`).
   - Under **Price and availability**, select all target countries/regions, enter your base price (e.g. $4.99/mo or $39.99/yr), and click **Update** -> **Save** -> **Activate**.
3. *(Optional)* Click **Add offer** on the active base plan to attach a 7-day free trial or introductory price; `BillingManager` automatically discovers all offers and passes the corresponding `offerToken` to `launchBillingFlow`.

---

## 4. Configuring Internal Testing & Closed Testing Tracks

### Option A — Internal Testing Track (Fastest: Available in Minutes, Up to 100 Testers)

1. In Google Play Console, go to **Testing** -> **Internal testing**.
2. Open the **Testers** tab:
   - Click **Create email list**, name it (e.g., `Internal QA`), and enter the Google account email addresses of your testers (must be `@gmail.com` or Google Workspace accounts).
   - Click **Save changes**.
3. Open the **Releases** tab and click **Create new release**:
   - Under **App integrity / Play App Signing**, let Google Play manage your app signing key (recommended).
   - Upload `android_version/app/build/outputs/bundle/release/app-release.aab`.
   - Upload `android_version/app/build/outputs/mapping/release/mapping.txt` (if not already bundled).
   - Enter release notes and click **Next** -> **Save and publish**.

### Option B — Closed Testing Track (For Larger Alpha/Beta Groups & Pre-Production Requirement)

1. Go to **Testing** -> **Closed testing** and select **Manage track** on the **Alpha** track (or click **Create track**).
2. Open the **Countries / regions** tab, click **Add countries / regions**, select your target global markets, and save.
3. Open the **Testers** tab, select your email list(s) or Google Groups, and click **Save changes**.
4. Open the **Releases** tab, click **Create new release**, upload `app-release.aab` (or choose **Add from library** to promote the exact `.aab` already tested in Internal Testing), and submit for Play review.

---

## 5. Adding Tester Google Accounts to License Testing (Zero-Charge Sandbox Purchases)

License testers can purchase one-time products and subscriptions using Google Play's test payment instrument **without real credit card charges**.

1. In the **Google Play Console** root left sidebar (Account level, outside the individual app view), go to **Settings** -> **License testing**.
2. Select your tester email list (the same list created in Step 4) or create a dedicated license testers list.
3. Set **License response** to `RESPOND_NORMALLY`.
4. Click **Save changes**.

**Test Subscription Renewal Speeds (Google Play License Testing):**
- A `1 month` (`P1M`) subscription renews every **5 minutes** in license testing.
- A `1 year` (`P1Y`) subscription renews every **30 minutes** in license testing.
- Test subscriptions renew up to 6 times and then expire automatically, allowing QA to test `ACTIVE` -> `IN_GRACE_PERIOD` (using the "Test card, always declines" option after initial purchase) -> `EXPIRED` transitions in under an hour.

---

## 6. Instructions for Testers to Opt In and Download the App

Share the following steps with your testers along with the **Copy link** URL from **Testing** -> **Internal testing** (or **Closed testing**) -> **Testers** -> **How testers join your test**:

1. **Verify Google Account on Device:**
   - Open the **Google Play Store** app on your Android phone (Android 8.0+).
   - Tap your profile avatar in the top-right corner and confirm the signed-in Google account matches the exact email address added to the tester list.
2. **Opt In to the Testing Program:**
   - Open the **Web Opt-In Link** (`https://play.google.com/apps/internaltest/...` or `https://play.google.com/apps/testing/com.osiris.player`) in Chrome on your phone or computer.
   - Sign in with your tester Google account and tap **Accept Invite** / **Become a Tester**.
3. **Install Osiris from Google Play:**
   - Tap **Download it on Google Play** on the confirmation page (this opens the Play Store listing for **Osiris (Internal Beta)**).
   - Tap **Install**. (If a local debug build of `com.osiris.player` is already installed on the device, uninstall it first so the Play Store-signed build can install cleanly.)
4. **Verify Test Payment Instrument During Checkout:**
   - Open Osiris, sign in, and open the **Wallet** screen.
   - Tap a Mana Crystal pack or **SUBSCRIBE** on Osiris Pass.
   - Confirm the Google Play purchase sheet displays **"Test card, always approves"** (or **"Test card, always declines"** for testing error/grace-period flows) and a notice stating *"This is a test order, you will not be charged."*

