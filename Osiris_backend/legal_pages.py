"""Public legal pages Google Play links to, and the Android App Links file.

Mounted without a schema entry: these are web pages, not part of the API contract.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import settings
from growth_social import _page

router = APIRouter()

SUPPORT_EMAIL = "support@osiris.fit"
EFFECTIVE = "8 November 2026"
_MAILTO = f'<a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>'

_PRIVACY = f"""<h1>Privacy Policy</h1><p class="sub">Effective {EFFECTIVE}</p>
<p>Osiris is a fitness game built around verified runs, workouts and challenges. This policy explains what the
Osiris app and service collect, why, who receives it, and the choices you have.</p>
<div class="card"><h2>What we collect</h2><ul>
<li><b>Account:</b> email address, password (stored only as a hash), display name, goal, home city and invite code.</li>
<li><b>Location:</b> precise GPS points while you record a run, walk or challenge, including with the screen locked
during a run you started. Osiris does not collect location when you are not recording.</li>
<li><b>Activity and fitness:</b> runs, workouts, durations, distances, rep counts, streaks, XP and rank, and step and
activity signals used to check that a run is genuine.</li>
<li><b>Camera:</b> pose estimation runs on your phone. Camera frames never leave your device. Only rep counts,
timings and a form score are uploaded, and only with your consent.</li>
<li><b>Health Connect:</b> when you tap Import, Osiris reads your workouts from the last 30 days with their heart
rate, speed, power and distance. It reads nothing in the background and never writes to Health Connect.</li>
<li><b>Bluetooth sensors:</b> heart rate, power and speed from sensors you connect during a session.</li>
<li><b>Content you share:</b> posts, photos, captions, comments, reactions, direct messages, follows, blocks and
reports.</li>
<li><b>Purchases:</b> the product bought and the purchase token from Google Play. We never receive your card details.</li>
<li><b>Technical:</b> IP address, device and app information and usage events, used for security and to fix problems.</li>
</ul></div>
<div class="card"><h2>How we use it</h2><ul>
<li>To run the game: record and verify activity, award XP, and show progress, challenges and rankings.</li>
<li>To keep competition fair and players safe: detect cheating, review reports and enforce the rules.</li>
<li>To deliver purchases, provide support, and secure and improve the service.</li>
</ul><p>We do not sell personal data and do not use it for advertising. Data from Health Connect is used only to
show and verify your training. It is not used for advertising, is not sold, and is not used to determine credit or
insurance eligibility. Our use of Health Connect data follows the Health Connect permissions policy, including its
Limited Use requirements.</p></div>
<div class="card"><h2>What other players can see</h2><ul>
<li>Posts and comments are visible according to the audience you choose. Direct messages are visible to you, the
recipient, and our team when a message is reported or investigated.</li>
<li>Leaderboards show your name only if you turn that on. Otherwise you appear as "Private runner".</li>
<li>Public maps show challenges as approximate markers. The first and last 150 m of a run are removed before it
becomes a course.</li></ul></div>
<div class="card"><h2>Service providers</h2>
<p>We share data only as needed to operate Osiris: Render (hosting), Supabase (database), Cloudflare (network
security and encrypted backups), Upstash (rate limiting), Google Play (purchases), Stripe (payments, where offered),
and Mapbox and OpenStreetMap (map display, which receive your map area and IP address). We may disclose data when the
law requires it or to protect players' safety.</p></div>
<div class="card"><h2>Retention</h2><ul>
<li>Raw GPS route points are deleted after 45 days. Run totals and results stay until you erase your account.</li>
<li>Anti-cheat telemetry is deleted after 90 days.</li>
<li>Encrypted backups are deleted after 35 days, so erased data leaves backups within that time.</li></ul></div>
<div class="card"><h2>Your choices and rights</h2><ul>
<li>Change location, leaderboard, public page and camera settings at any time in Settings.</li>
<li>Download a copy of your data in Settings &gt; Download my data.</li>
<li>Erase your account in Settings &gt; Erase my account, or see <a href="/account-deletion">account deletion</a>.</li>
<li>Depending on where you live, you may have further rights, including access, correction, objection and complaint
to a data protection authority. Contact us to use them.</li></ul></div>
<div class="card"><h2>Age, security and changes</h2>
<p>Osiris is for people aged 18 and over, and we do not knowingly collect data from anyone younger. Data is encrypted
in transit and backups are encrypted at rest. No service is perfectly secure. We will update this page when the
policy changes, and tell you in the app about significant changes.</p></div>
<p>Questions: {_MAILTO}</p>"""

_TERMS = f"""<h1>Terms of Service</h1><p class="sub">Effective {EFFECTIVE}</p>
<div class="card"><h2>Using Osiris</h2><p>You must be at least 18 to use Osiris. Keep your password safe and give
accurate information. You are responsible for activity on your account.</p></div>
<div class="card"><h2>Exercise and safety</h2><p>Osiris is not medical advice. Check with a doctor before starting a
new exercise routine. Obey traffic laws, stay aware of your surroundings, and do not enter private or unsafe places
to complete a challenge. You exercise at your own risk.</p></div>
<div class="card"><h2>Community rules: zero tolerance</h2><p>Osiris has no tolerance for objectionable content or
abusive users. Do not post or send content that is hateful, harassing, threatening, sexual, violent, illegal or
misleading, that shares someone's private information, or that infringes others' rights. Do not cheat, including by
faking GPS or sensor data.</p>
<p>Use Report on any post, comment, player or conversation, and Block to stop contact with a player. We review reports
and remove violating content, and may suspend or close accounts that break these rules.</p></div>
<div class="card"><h2>Your content</h2><p>You keep ownership of what you post. You give Osiris a worldwide,
royalty-free licence to host and display it within the service, according to your settings, until you delete it or
erase your account.</p></div>
<div class="card"><h2>Mana Crystals, XP and purchases</h2><p>XP, rank, badges and Mana Crystals are game features. They
have no cash value and cannot be exchanged for money. Purchases through Google Play are subject to Google Play's terms
and refund policies. Subscriptions renew until cancelled in Google Play. XP or rewards obtained by breaking the rules
may be removed.</p></div>
<div class="card"><h2>The service</h2><p>Osiris is provided "as is" and may change or be interrupted. To the extent
the law allows, we are not liable for indirect or consequential losses. Nothing here limits rights that cannot be
limited by law. You can stop at any time by erasing your account. We will post changes to these terms on this
page.</p></div>
<p>Questions: {_MAILTO}. See also the <a href="/privacy">Privacy Policy</a>.</p>"""

_DELETION = f"""<h1>Delete your Osiris account</h1><p class="sub">How to erase your account and data</p>
<div class="card"><h2>In the app</h2><ol><li>Open Osiris and go to Profile, then Settings.</li>
<li>Scroll to Account and tap <b>Erase my account</b>.</li><li>Confirm and enter your password.</li></ol>
<p>Erasure happens immediately and cannot be undone.</p></div>
<div class="card"><h2>Without the app</h2><p>Email {_MAILTO} from the address on your account with the subject
"Delete my account". We will verify the request and erase the account within 30 days.</p></div>
<div class="card"><h2>What is deleted</h2><ul><li>Email, password, profile, display name and invite code</li>
<li>Routes, GPS points, runs, workouts, health imports and anti-cheat telemetry</li>
<li>Posts, photos, comments, reactions, messages, follows, blocks and badges</li></ul></div>
<div class="card"><h2>What is kept</h2><ul>
<li>An anonymous account placeholder, so other players' results and challenges stay correct</li>
<li>Crystal ledger and purchase records with no name or email attached, kept as long as accounting law requires</li>
<li>Reports you filed, with your identity removed, and security audit entries</li>
<li>Encrypted backups, which expire within 35 days</li></ul></div>"""


def _legal(path: str, title: str, description: str, body: str):
    base = settings.public_base_url() or ""
    return _page(title=f"{title} · Osiris", description=description, url=f"{base}{path}", body=body, index=True)


@router.get("/privacy", include_in_schema=False)
def privacy_policy():
    return _legal("/privacy", "Privacy Policy", "How Osiris collects, uses and protects your data.", _PRIVACY)


@router.get("/terms", include_in_schema=False)
def terms_of_service():
    return _legal("/terms", "Terms of Service", "The rules for using Osiris.", _TERMS)


@router.get("/account-deletion", include_in_schema=False)
def account_deletion():
    return _legal("/account-deletion", "Delete your account", "How to erase your Osiris account and data.", _DELETION)


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
def asset_links():
    """Lets Android open invite links in the app. Empty until the Play signing fingerprint is configured."""
    fingerprints = settings.android_cert_fingerprints()
    if not fingerprints:
        return JSONResponse([])
    return JSONResponse([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": settings.android_package_name(),
            "sha256_cert_fingerprints": fingerprints,
        },
    }])
