Here is the consolidated and updated **Master Design & Technical Document** for Osiris. It merges the initial MVP technical requirements with the advanced RPG mechanics, party systems, and territorial economy we discussed.

***

# 📜 OSIRIS: Master Game Design & Technical Document (GDD/TDD)

## I. Project Identity & Vision
* **The Hook:** *"Earn Your Awakening."* Osiris is a high-stakes, real-world Action-RPG where physical effort translates directly to digital rank, territorial control, and financial rewards.
* **The System:** An AI-driven "Referee" validates movement, preventing the cheating common in standard fitness apps and establishing a true economy of effort.

---

## II. The Progression & Hierarchy System

Users are categorized by a dual-tier identity system: **Physical Grade** (Raw Power) and **Territorial Title** (World Influence).

### 1. The Grade (Physical Rank)
Calculated by the AI Referee based on the user's completion of verified physical tasks.

| Rank (Grade) | Title (Prestige) | Requirements & Decay Logic |
| :--- | :--- | :--- |
| **SSS / SS / S** | God, Emperor, King | Elite performance. Top 0.1% of Global Leaderboard + Unique Feats. |
| **A / B** | Saint, Advanced | Dedicated athletes. Consistent high-level output. |
| **C / D** | Intermediate, Beginner | Baseline fitness; casual/starting users ("The Awakened"). |
| **F** | The Dishonored | Flagged for cheating or prolonged inactivity (>30 days). |

### 2. The Peerage (Territorial Control)
Titles are tied to **Cumulative Land Ownership** through "Domain Expansion". Players trace GPS polygons in the real world to claim land.

| Title Rank | Cumulative Area Required | Map Privilege | Real-World Feat Equivalent |
| :--- | :--- | :--- | :--- |
| **Warden** | 1.0 km² | Receives Base Tax from players inside. | ~4 km perimeter run. |
| **Lord** | 5.0 km² | Custom AR Flag on map center. | ~9 km perimeter run (or 5 Wardens). |
| **High Lord** | 20.0 km² | Controls weather/spawn conditions. | ~18 km perimeter run (or 4 Lords). |
| **Sovereign** | 100.0+ km² | Sovereign-only Guild Hall access. | Massive Guild Coordination. |

---

## III. The Gameplay Loop & Party Mechanics

### 1. Onboarding (The Awakening)
* **Input:** Height, Weight, Age, Gender.
* **Assessment Quest:** User performs a baseline physical test (push-ups, running) verified by the AI.
* **Avatar:** Based on the assessment, the user is assigned a **2D Sprite Class** (e.g., Tank, Assassin, Mage) matching their primary physical strength.

### 2. Daily Bounties & Dungeons
* **Bounties:** Low-stakes tasks ("Walk 5k steps," "Do 20 push-ups") to maintain XP and avoid Rank Decay.
* **Dungeons:** Premium GPS-gated zones. Users pay "Mana Crystals" to enter and must clear a timed sequence of exercises to earn high-tier loot.

### 3. Domain Expansion (Territory Wars)
*Strava Art meets Splatoon.* Players convert physical runs/walks into closed GPS polygons. The enclosed area becomes their "Virtual Property."
* **The Cast:** User pays Mana Crystals, traces a path via GPS (polling every 5s), and closes the loop (returning to start within 20m).
* **The Imprint:** Immediately upon closing the loop, the player performs a physical "Defense Feat" (e.g., max push-ups in 2 minutes) verified by the AI Referee to set the defending "Ghost" score.
* **The Siege:** To steal a domain, a Challenger must physically run a path that completely encapsulates (swallows) the Defender's polygon. The Challenger must then beat the Defender's Ghost score.
    * *Win:* Defender's polygon is erased; Challenger claims the new larger area.
    * *Loss:* Challenger's trace shatters; Mana Crystals lost.
* **Guild Empires:** If two players in the same Guild draw intersecting domains, the polygons merge into a unified "Guild Empire."

### 4. The Adventure Party (Role Assignment)
When players group up for a Dungeon or Raid Boss, the System assigns roles based on their **verified 30-day physical history**:
* **Vanguard (Tank):** Highest Strength (STR). Tasked with explosive, heavy-resistance movements to "block" boss attacks.
* **Striker (DPS):** Highest Agility (AGI). Tasked with high-speed movement (sprinting, burpees) to deal massive damage.
* **Scout (Support):** Highest Endurance (END). Tasked with maintaining steady volume (long-distance movement) to provide party buffs.
* **Strategist (Healer):** Highest Consistency (Streak). Tasked with precision holds (planks) to restore the party's time limit.

---

## IV. The Economy & Business Model

Osiris operates on a dual B2B/B2C revenue model, blending real-world local business with an RPG economy.

### 1. B2C: The Adventurer's Economy
* **The Defender's Vault & Challenge Tax:** To hold a Territorial Title, players must lock real money in a "Vault" (e.g., $10 for Warden). Challengers match this bet. The winner takes the title and 80% of the pot. Osiris takes a **20% War Tax**.
* **The Black Market:** A user-to-user trading hub for rare digital loot (Skins/Artifacts) with a **15% transaction fee**.
* **The Tower Pass:** A $9.99/month subscription offering XP boosters, "Decay Shields," and premium cosmetics.

### 2. B2B: Foot Traffic as a Service
* **The Merchant Portal:** A web dashboard where local businesses pay (e.g., $50) to host a "Legendary Chest."
* **The Conversion:** Chests unlock only when a player is within 10 meters of the shop. Inside, players find XP and a digital coupon (e.g., "20% off a protein smoothie").

---

## V. Technical Architecture & The AI Referee (The Moat)

To prevent cheating and minimize battery drain, Osiris uses a **Hybrid Sensor Fusion** approach.

### 1. The Verification Matrix
| Threat | Solution (The Anti-Cheat) |
| :--- | :--- |
| **Vehicle GPS Spoofing** | **Velocity Lock:** If Velocity > 25 km/h for >10s, Domain Trace shatters. |
| **Invalid Polygons** | **Closure Tolerance:** Must return to origin coordinates within 20m. |
| **Polygon Swallowing** | **Ray Casting Algorithm:** Checks if Target vertices fall entirely inside Challenger shape. |

### 2. Sensor Compute Cost
| Exercise Type | Primary Sensor | Tech / Logic | Compute Cost |
| :--- | :--- | :--- | :--- |
| **Sprinting / Running** | GPS + Accelerometer | Speed/Cadence validation; Velocity filtering (<25 km/h). | Low |
| **Skipping / Jumping** | Accelerometer / IMU | Frequency (Hz) pattern matching; Anti-spoof detection. | Low |
| **Push-ups / Squats** | Camera (MediaPipe) | On-device Pose Estimation (Skeleton tracking) at 15 FPS. | Medium/High |
| **Dungeon Clearing** | Geofencing | Radius-based entry/exit triggers (Google Maps API). | Low |

### 3. Tech Stack Recommendation
* **Frontend/Mobile:** Flutter (Handles ARCore/ARKit and maps efficiently).
* **Backend:** Python (FastAPI) for high-performance ML integration.
* **Database:** PostgreSQL with **PostGIS extension** (Crucial for `ST_Area` and spatial intersect queries).
* **ML Framework:** MediaPipe (On-device Pose Estimation), Scikit-learn (Accelerometer anomaly detection).

---

## VI. SDLC – MVP Implementation Plan (Phase 1 & 2)

### 1. Scope (The Bedford Pilot)
* **Zone:** DeWolf Park to Sunnyside Mall.
* **Users:** ~50 testers per bounty.
* **Constraint:** Avoid direct live-road speed quests for safety. Rely on "Stay in the Zone" park quests.

### 2. Core User Stories (MVP)
* **Epic 1: Participation:**
    * *Story 1.1:* As a user, I want to see nearby bounties on a map so I can choose a challenge.
    * *Story 1.2:* As a user, I want to open my camera after a quest to claim an AR Treasure Chest on the ground.
* **Epic 2: Verification (Anti-Cheat):**
    * *Story 2.1:* As the system, I will verify GPS coordinates within a 30m polygon to ensure physical presence.
    * *Story 2.2:* As the system, I will analyze accelerometer arrays to classify human stride vs. phone shaking (85% confidence required).
* **Epic 3: Business Flow:**
    * *Story 3.1:* As a merchant, I want to define a reward amount, max users, and pay a pilot fee to place a chest at my storefront.
* **Epic 4: Domain Expansion (Territory Wars):**
    * *Story 4.1:* As a user, I want to press "Start Domain" and see a breadcrumb trail of my path on the map.
    * *Story 4.2:* As the system, I will calculate the distance between the user's current location and start point, enabling "Close Domain" if < 20m.
    * *Story 4.3:* As the backend, I will reject any domain submission where the user's average speed exceeded 25 km/h.
    * *Story 4.4:* As the backend, I will use Point-in-Polygon logic to check if a new domain swallows an existing one, triggering a Siege.
    * *Story 4.5:* As the system, I will aggregate total `area_sqkm` for a user and automatically update their Map Title (Warden, Lord, etc.).

### 3. Risk Mitigation
| Risk | Mitigation Strategy |
| :--- | :--- |
| **GPS Spoofing** | Cross-check sudden coordinate jumps with realistic acceleration constraints. |
| **Cheating (Shaking)** | Train ML model on accelerometer frequency patterns to reject non-human rhythms. |
| **Live Betting Latency** | Force MVP betting/challenges to be **Asynchronous** (beat a ghost score) rather than live 1v1 video syncs. |
| **Avatar Body-Shaming** | Avoid strict BMI visual morphing; let users choose their Class "Path" (Strength/Cardio). |