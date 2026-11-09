# Osiris on Google Play: internal test

How to get Osiris onto your own phone through Google Play. Do the parts in order. Written 2026-11-08.

Play Console menus move around. If a label differs, use the Console's search box with the words given here.

## Before you start

| Item | Status |
|---|---|
| Upload keystore | `android_version/release-upload-keystore.jks` and `keystore.properties` exist and are git-ignored |
| Back up the keystore | **Do this now.** Copy both files and the passwords to your password manager |
| App id | `com.osiris.player` cannot be changed after the first upload |
| Production API | `https://api.osiris.fit` (healthy, migrations current) |
| Supabase | Nothing to do. This release adds no database migration |

## Part 1. Setup outside Google Play

### 1.1 Publish the backend changes

`/privacy`, `/terms` and `/account-deletion` only exist after the backend is deployed, and Play needs those links.
Merging the branch to `master` deploys it through Render.

Check after the deploy:

- https://api.osiris.fit/privacy
- https://api.osiris.fit/terms
- https://api.osiris.fit/account-deletion

### 1.2 Create support@osiris.fit

The policies and support chat give this address, and it does not exist yet. Cloudflare can forward it to your Gmail for free.

1. Cloudflare dashboard > `osiris.fit` > **Email** > **Email Routing** > **Get started**.
2. Custom address `support`, destination your Gmail, then **Create and continue**.
3. Open the verification email and confirm.
4. Back in Cloudflare, choose **Add records and enable**.
5. Send a test message to support@osiris.fit from another account.

### 1.3 Review the legal pages

The Privacy Policy, Terms and account-deletion page were drafted from what the code does. They are not legal advice.
Read them, and have a lawyer check them before a public launch. They set the minimum age at 18, so answer the Play
target-audience question the same way.

### 1.4 Optional cost cleanup

The Render disk `osiris-data` only holds the retired SQLite file. See step 10 in `docs/deployment/production.md`.

## Part 2. Build the release bundle

From the repo root, in Git Bash:

```
export JAVA_HOME="$HOME/.jdks/jbr-21.0.11"
export ANDROID_HOME="$LOCALAPPDATA/Android/Sdk"
./gradlew -Posiris.env=prod -Posiris.versionCode=1 -Posiris.versionName=1.0.0 :android_version:app:bundleRelease
```

The file is `android_version/app/build/outputs/bundle/release/app-release.aab`.

`-Posiris.env=prod` is required. Without it the app points at a local server. Raise `osiris.versionCode` by 1 for every
upload, because Play refuses a repeated number.

## Part 3. Create the app and upload

1. https://play.google.com/console > **Create app**.
2. App name `Osiris`, your default language, **App**, **Free**. Accept the declarations and **Create app**.
3. **Test and release** > **Testing** > **Internal testing** > **Create new release**.
4. Accept **Play App Signing** when asked.
5. Upload `app-release.aab`. Release name `1.0.0 (1)`. Notes: `First internal test`.
6. **Next**. Fix anything listed as an error using Part 4, then **Save and publish**.

## Part 4. App content forms

Find these under **Policy and programs** > **App content**. Internal tests are not all held to the same form list, so fill
them once now and they will be ready for closed testing too.

| Form | Answer |
|---|---|
| Privacy policy | `https://api.osiris.fit/privacy` |
| Ads | No ads |
| App access | Restricted. Create a test account in the app and give its email and password |
| Content rating | Fitness/utility questionnaire. Yes to user interaction and shared location, if asked |
| Target audience | 18 and over |
| News, government, financial features | No |
| Health apps | Fitness. Declare Health Connect read access for exercise, heart rate, speed, power and distance. Reason: "Imports the player's recent workouts when they tap Import, to show their training history." No write or background access |
| Foreground service | Location, for "the player starts a run and it records with the screen locked, with a visible notification". The Console may ask for a short screen recording of this |
| Data safety | See below |

### Data safety answers

Data is collected, encrypted in transit, and players can request deletion. Deletion URL: `https://api.osiris.fit/account-deletion`.
Service providers do not count as sharing, so answer **not shared** for all of these.

| Data type | Collected | Purpose |
|---|---|---|
| Name, email, user IDs | Yes, required | Account management, app functionality |
| Precise and approximate location | Yes, required for runs | App functionality, fraud prevention |
| Health info (heart rate) and fitness info | Yes, optional | App functionality |
| Photos | Yes, optional | App functionality |
| In-app messages, other user content | Yes, optional | App functionality |
| Purchase history | Yes, optional | App functionality |
| App interactions | Yes | Analytics, app functionality |
| Device or other IDs (install ID) | Yes | Fraud prevention, app functionality |

## Part 5. Add yourself as a tester and install

1. **Internal testing** > **Testers** > **Create email list**, add the Gmail used on your phone, **Save**.
2. Tick that list, **Save**, and copy the **join link**.
3. On the phone, signed in to that Gmail, open the link and tap **Become a tester**.
4. Follow the Play Store link and tap **Install**. The first time it can take several hours to appear.

For a quick look before all that, install the signed APK over USB. Billing will not work this way:
`adb install -r android_version/app/build/outputs/apk/release/app-release.apk`

## Part 6. Turn on purchases

Products can only be created after a bundle with billing has been uploaded (Part 3).

### 6.1 Create the products

**Monetize with Play** > **Products**. The ids must match exactly, and each product must be **active**.

| Type | Product id | Grants |
|---|---|---|
| One-time | `osiris_crystals_starter` | 500 crystals |
| One-time | `osiris_crystals_adventurer` | 1200 crystals |
| One-time | `osiris_crystals_champion` | 2600 crystals |
| One-time | `osiris_founder_pack` | Founder pack |
| Subscription, with one base plan | `osiris_pass_monthly` | Osiris Pass |
| Subscription, with one base plan | `osiris_pass_annual` | Osiris Pass |

### 6.2 Let the server check purchases

Without this, every purchase fails verification and the player gets nothing.

1. https://console.cloud.google.com > create or pick a project.
2. **APIs & Services** > **Library** > enable **Google Play Android Developer API**.
3. **IAM & Admin** > **Service Accounts** > **Create**. Name it `osiris-play`, with no roles.
4. Open it > **Keys** > **Add key** > **JSON**. Keep the downloaded file private.
5. Play Console > **Users and permissions** > **Invite new users** > the service account's email.
6. Grant **View app information**, **View financial data** and **Manage orders and subscriptions**, then invite.
7. Render > `osiris-api` > **Environment** > set `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` to the whole JSON file's content. Save.

New permissions can take up to a day to take effect.

### 6.3 Test without being charged

1. Play Console > **Settings** > **License testing**, add your Gmail, **Save**.
2. In the app, open Wallet and buy a pack using **Test card, always approves**.
3. Crystals should arrive within seconds.

## Part 7. Make invite links open the app

1. Play Console > **Test and release** > **Setup** > **App signing**.
2. Copy the **App signing key** SHA-256 fingerprint. Use that one, not the upload key.
3. Render > `osiris-api` > **Environment** > set `OSIRIS_ANDROID_CERT_SHA256` to it. Save.
4. Check that https://api.osiris.fit/.well-known/assetlinks.json shows the fingerprint.

## Part 8. What to test on the phone

- [ ] Create an account, sign out, sign back in. Terms and Privacy links open.
- [ ] Allow location, record a short outdoor run, and see the result.
- [ ] Lock the screen for a long run. A 60-minute run is the real check.
- [ ] Camera exercises in real light, at floor and standing angles.
- [ ] Bluetooth heart-rate sensor, if you have one.
- [ ] Health Connect import from the Progress page.
- [ ] Map screens show the map.
- [ ] Post with a photo, comment, send a direct message (needs a second account).
- [ ] Report a post, a comment and a player. Check the reports in admin, Community > Reports.
- [ ] Remove a reported post from admin, and block a player.
- [ ] Buy a test crystal pack and a test subscription.
- [ ] Open an invite link from another app.
- [ ] Download my data, then Erase my account on a throwaway account.

Crashes appear in Play Console under **Android vitals**.

## Before a public launch

- Personal developer accounts created after 13 November 2023 must run a closed test with at least 12 testers opted in
  for 14 days in a row, then apply for production access. Organization accounts are generally exempt.
- Complete the store listing: 512x512 icon, 1024x500 feature graphic, at least 2 phone screenshots, descriptions.
- Build the missing pieces listed in the release notes for this branch: password reset, push notifications, a staffed
  support desk, and Play refund handling.
