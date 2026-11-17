#!/usr/bin/env bash
# Builds the signed production Play bundle on this machine (no CI needed) and prints what is
# actually inside it: package name, version code and signing certificate.
#
#   scripts/build_android_release.sh <versionCode> [versionName]
#
# Needs JAVA_HOME (JDK 17+), ANDROID_HOME, and signing credentials in keystore.properties or
# OSIRIS_KEYSTORE_* (see keystore.properties.template). The build itself refuses a non-prod
# environment, missing signing or a missing version code (android_version/app/build.gradle.kts).
set -euo pipefail

code="${1:-}"
name="${2:-1.0.0}"
if ! [[ "$code" =~ ^[1-9][0-9]*$ ]]; then
    echo "usage: $0 <versionCode> [versionName]   (versionCode: a whole number, higher than the last upload)" >&2
    exit 2
fi
: "${JAVA_HOME:?set JAVA_HOME to a JDK 17+}"
: "${ANDROID_HOME:?set ANDROID_HOME to the Android SDK}"

cd "$(dirname "$0")/.."
./gradlew -Posiris.env=prod "-Posiris.versionCode=$code" "-Posiris.versionName=$name" :android_version:app:bundleRelease

aab="android_version/app/build/outputs/bundle/release/app-release.aab"
[[ -f "$aab" ]] || { echo "No bundle at $aab" >&2; exit 1; }

# A bundle stores its manifest as protobuf. aapt2 reads that format from an APK-shaped zip, so the
# base module's manifest and resource table are repacked into one.
aapt2="$(ls "$ANDROID_HOME"/build-tools/*/aapt2* | sort -V | tail -1)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
unzip -q -j "$aab" base/manifest/AndroidManifest.xml base/resources.pb -d "$tmp/base"
"$JAVA_HOME/bin/jar" --create --no-manifest --file "$tmp/base.apk" -C "$tmp/base" .
manifest="$("$aapt2" dump xmltree --file AndroidManifest.xml "$tmp/base.apk")"
attr() { sed -n "s|^ *A: [^=]*$1[^=]*=.*(Raw: \"\(.*\)\").*|\1|p" <<<"$manifest" | head -1; }
package="$(attr package)"
built_code="$(attr versionCode)"
built_name="$(attr versionName)"

# The signer comes from the bundle too; a bundle without one is unsigned and Play rejects it.
signer="$("$JAVA_HOME/bin/keytool" -printcert -jarfile "$aab" 2>&1 || true)"
sha256="$(sed -n 's/.*SHA256: *//p' <<<"$signer" | head -1)"

echo
echo "Bundle:       $aab"
echo "Package:      $package"
echo "Version:      $built_name ($built_code)"
echo "Signed:       ${sha256:+yes, certificate SHA-256 $sha256}${sha256:-NO}"

[[ "$package" == "osiris.fit" ]] || { echo "Unexpected package '$package'" >&2; exit 1; }
[[ "$built_code" == "$code" ]] || { echo "Bundle has version code '$built_code', expected $code" >&2; exit 1; }
[[ -n "$sha256" ]] || { echo "The bundle is not signed" >&2; exit 1; }
