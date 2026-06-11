# Osiris — Privacy Build-List (Engineering Handoff to Backend Agent)

| Field | Value |
| :--- | :--- |
| **Document Type** | Engineering build-list — privacy/data-protection |
| **Consumed in** | Phase 2 (consent capture lands with money code) / Phase 5 (export + delete + anonymization implemented and tested) |
| **Date** | 2026-06-11 |
| **Prepared by** | Senior Compliance & Privacy Analyst (panel) |
| **Audience** | Principal Backend Engineer + Privacy/Compliance Officer (Agent Charter Roles 1 & 6) |
| **Status** | Specification — **no code in this document.** Implementation is Phase 2/5. |
| **Disclaimer** | This is a build specification informed by data-protection principles. It is **not legal advice** and does not conclude compliance. The lawful-basis determinations must be confirmed by privacy counsel against `Counsel_Question_List.md`. |

---

## (a) FLAG — the spec's "UK GDPR" framing is WRONG for this pilot

**The audit (`Deep_Audit_2026-06.md` §2.2, §3.4) and the surviving GDD repeatedly say "UK GDPR" / "GDPR" governs the pilot. For the actual Bedford, Nova Scotia pilot population, this is incorrect and must not drive the build.**

- **PIPEDA (federal Canadian private-sector privacy law) governs** the collection/use/disclosure of the pilot testers' personal data, layered with **Nova Scotia** considerations. The obligation attaches at **tester #1**, not at scale.
- **UK GDPR only attaches to UK data subjects.** Unless and until Osiris collects data from people **in the UK**, UK GDPR is not the operative regime for the ~50 Bedford testers. Building to "UK GDPR" while ignoring PIPEDA means building to the wrong consent, access, and retention standard for the people actually in the pilot.
- **Engineering consequence:** design the consent/export/delete machinery to satisfy **PIPEDA's** principles (meaningful consent, purpose limitation, access, accuracy, safeguards, individual access + correction, retention limits, accountability). PIPEDA-grade design is a strong baseline; if the product later expands to UK/EU subjects, the same endpoints extend — but **do not let "UK GDPR" be the named target while the real population is Canadian.**

> **Action for counsel (not engineering):** confirm the exact PIPEDA + NS obligations and whether any provincial law adds requirements. This build-list specifies the *machinery*; counsel confirms the *standard*.

---

## (b) Telemetry classification — this data is SENSITIVE

What Osiris captures per workout (from `User Story.md` Epic 8, `Imp_and_US.md` §6.2, `openapi.json` `ActivityProof` / `TelemetrySession` / `TelemetryData`):

| Data class | Fields | Sensitivity classification | Why |
| :--- | :--- | :--- | :--- |
| **Precise location (continuous)** | GPS traces, domain polygons, centroids, `/domains/nearby` | **SENSITIVE** | A polygon is *"a map of where a specific person repeatedly exercises"* (audit §2.2). Location → home/work/routine → identifiable individual. Continuous traces are among the most re-identifying data that exists. |
| **Biometric-adjacent motion** | accelerometer, gyroscope, magnetometer, barometer, pose summaries (MediaPipe landmarks) | **SENSITIVE (biometric-adjacent)** | Gait/cadence/pose signatures are behaviorally identifying and health-adjacent. Treat as sensitive even where not strictly "biometric" under a given statute. |
| **Health-adjacent profile** | height, weight, age, gender, BMI-derived class, exercise performance | **SENSITIVE (health-adjacent)** | Physical/health attributes. |
| **Account / contact** | email, password hash, name | Personal (standard) | Standard PII; password already bcrypt-hashed (good). |
| **Economic / behavioral** | crystal balance, vault, siege history, activity logs | Personal (standard) | Behavioral; becomes higher-stakes once crystals are convertible. |

**Build implication:** GPS + motion telemetry must be treated as **sensitive** throughout — stricter consent, minimization, retention limits, and access controls than ordinary account data. The audit's **unauthenticated `/domains/nearby` leak (§2.2)** is a sensitive-location exposure and is a **privacy blocker**, not only a security one (cross-listed below).

---

## (c) Endpoints engineering must build (consent, export, delete)

> None of these exist today (audit §3.4: "no account-delete, no data-export, no consent record"). Specified here; implemented Phase 2/5.

### C.1 Consent capture & ledger
- **`POST /api/v1/consent`** (and a read `GET /api/v1/consent`): records a **versioned, timestamped, granular** consent decision per purpose (see part (d) for the two distinct purposes). Store: `user_id`, `purpose_code`, `consent_version`, `granted` (bool), `device_timestamp` + **server timestamp**, `consent_text_hash` (so you can prove *which wording* they agreed to).
- Consent is captured at **onboarding** and **re-prompted on version change**. A withdrawn consent must propagate to the relevant data path (e.g., withdraw ML-training consent → stop retaining samples for training; see (d)).
- **Append-only** consent history (never overwrite a prior consent row — you must be able to show the state at any past date).

### C.2 Data export (PIPEDA access right)
- **`GET /api/v1/users/{id}/export`** (self or admin): returns the user's personal data in a portable format — profile, activities (`ActivityLog`), domains, siege/bounty history, **telemetry metadata** (`TelemetrySession`), and crystal/ledger history. Raw sample blobs included or referenced per counsel guidance on scope.
- Must be authenticated as the subject (or admin acting for the subject); rate-limited; logged as an access event.

### C.3 Deletion (with the ledger constraint in part below)
- **`DELETE /api/v1/users/{id}`** (self-initiated or admin-honored): honors a deletion/erasure request.
- Cascades hard-delete on data that **can** be erased: raw telemetry samples (`TelemetryData`), GPS traces, pose summaries, contact fields, domains.
- **Does NOT hard-delete ledger rows** — see the constraint below.
- Returns a confirmation the request was honored; deletion events themselves logged (who/when), with the **subject anonymized in that log too**.

### C.4 Cross-listed privacy blocker (fix belongs to Security/Backend, flagged here because it is a privacy exposure)
- **`GET /api/v1/domains/nearby` is unauthenticated and leaks `owner_id` + exact polygon + `vault_balance`** (audit §2.2). For sensitive continuous-location data this is a **privacy blocker for the pilot.** Must be authenticated; return an **opaque per-domain handle**, not raw `owner_id`; consider coarsening geometry (centroid + area) for non-owners.

---

## The ledger-deletion constraint (call it out explicitly to engineering)

**Crystal-ledger rows cannot be hard-deleted on a user-deletion request.** The append-only crystal ledger (Agent Charter Role 4; audit §3.2) is the **accounting system of record** — balance is *derived* from immutable entries, and conservation/reconciliation (Phase 2 invariant tests) depends on every entry surviving. Hard-deleting a departed user's ledger rows would **break crystal conservation** (sums no longer reconcile) and destroy the audit trail behind real-money movements.

**Required pattern — anonymize the subject, preserve the accounting:**
- On deletion, **sever the link between the person and the rows**: replace `user_id` (and any PII reachable from it) with a **non-reversible anonymized subject token** (e.g., a one-way pseudonym), and null/scrub any free-text PII on those rows.
- **Keep** the ledger `delta`, `balance_after`, `reason_code`, `related_*_id`, and timestamps intact under the anonymized token.
- Net effect: "user 42" becomes "anonymized-subject-X"; the books still balance; no one can re-identify the person from the retained accounting.
- The **Compliance agent reviews this anonymization design** (Playbook Phase 5 names this review explicitly). Confirm with counsel that PIPEDA's retention-for-legal/accounting-purpose basis covers retaining anonymized financial records after an erasure request.

---

## (d) Two purposes, two consent bases — keep them separate

The same telemetry serves two distinct purposes, and **each needs its own lawful basis / consent** (Agent Charter Role 6 standing brief):

| Purpose | What it is | Consent basis | Build consequence |
| :--- | :--- | :--- | :--- |
| **PRIMARY — verify the workout** | Use GPS + motion to confirm the player actually did the activity, award XP/crystals, resolve the action. | Necessary to deliver the service the user asked for — the **primary** processing purpose. | A separate `purpose_code = "workout_verification"` consent. Without it, the core loop can't run. Data needed *only* for verification should be **minimized and short-retained** once the action resolves. |
| **SECONDARY — train the ML referee** | Retain raw samples to build training datasets for the future scikit-learn anomaly detector (Epic 8.5). | **A distinct secondary-purpose consent.** "We verified your workout" does **not** authorize "we keep your gait data to train a model." | A separate `purpose_code = "ml_training"` consent, **independently grantable and withdrawable.** If not granted: telemetry may be used to verify the workout but **must not be retained for training** — drop/expire it on the verification path, do not route it into the training corpus. Withdrawal must purge the user's samples from the training-retention pool. |

**Engineering enforcement:** the telemetry write path must **branch on the `ml_training` consent flag** — samples retained for training only when that specific consent is present and current. The existing **TTL purge (`process_telemetry_ttl`, default 90 days)** is a retention *ceiling*, not a consent substitute: no-consent data should not reach the 90-day window at all. Coordinate with the Data Engineer (Role 9): "no consent, no retention."

---

## Build-list summary (the items that BLOCK Phase 2)

These are the privacy items the panel considers **blocking** for Phase 2 (real testers' sensitive data being retained, and the run-up to money):

1. **Re-target the framing from "UK GDPR" to PIPEDA/NS** in all design docs and consent copy. *(Blocking — you can't write correct consent text to the wrong law.)*
2. **Consent capture + versioned consent ledger** with the **primary vs. secondary (ML) split** — granular and independently withdrawable. *(Blocking — retaining sensitive telemetry for ML without its own consent is the named red line.)*
3. **Authenticate `/domains/nearby` + stop leaking `owner_id`/exact geometry.** *(Blocking — live sensitive-location leak.)*
4. **Export endpoint** (PIPEDA access). *(Blocking for go-live; implementable Phase 5.)*
5. **Delete endpoint with ledger-preserving anonymization** (anonymize subject, keep the books). *(Blocking — "any feature that can't honor a delete request" is a red line.)*
6. **Sensitive-data handling**: minimize, access-control, and retention-limit GPS + motion telemetry; TTL is a ceiling, consent is the gate.

Items 1–3 should land **before real testers' data is ML-retained** (i.e., before/at Phase 2). Items 4–5 are implemented and tested in Phase 5 per the Playbook, but the **deletion-anonymization design must be agreed now** so the ledger is built to support it from day one.
