# 🏆 The MVP Implementation Plan

## 🔹 Phase 1: Onboarding & The "Stat" Engine

### 👤 User Profile
*   **Authentication:** Standard Email/Password auth.

### 🎭 The Avatar Logic
Instead of complex 3D models initially, use **Dynamic 2D Sprite Sheets**.
*   **Logic:** Calculate BMI (`Weight / Height²`). Map BMI ranges to **Physical Classes** (e.g., *Tank, Assassin, Mage*).
*   **Ranking:** Hardcode the Rank/Title strings in a lookup table so the UI updates instantly as XP crosses thresholds.

### 📉 The Decay System
Implement a *"Streak"* counter.
*   **Mechanism:** If the `last_activity_date` is `> 24 hours`, a background `cron` job deducts a percentage of XP daily.

---

## 🔹 Phase 2: The Quest Board (GPS & AR)

### 📍 Geofencing
*   **API Integration:** Use the **Google Maps API** to define "Quest Zones" in Bedford/Halifax.

### 🎁 The Loot Drop
*   **Trigger:** When the user enters the geofence and completes the task (e.g., *"Reach the park in 10 mins"*), trigger the AR view.

### 🕶️ AR Implementation
*   **Tech Stack:** Use **ARCore** (Android) / **ARKit** (iOS).
*   **Logic:** Instead of complex physics, simply "anchor" a 3D chest model to the horizontal plane (the ground) once the GPS coordinates match.

---

## 🔹 Phase 3: The ML Referee (The Betting System)

### 🧘‍♂️ Pose Estimation
*   **Tech Stack:** Use **MediaPipe** (lightweight and runs on-device).
*   **Logic:** Track "Landmarks" (*elbow, shoulder, hip*) to count reps accurately.

### 🔄 Synchronization
*   **Live Bet Requirements:** For the "Live" bet, you will need **WebRTC** for the video stream and **WebSockets** to sync the rep counts in real-time.

---

# ⚠️ Flaw Logic & Reality Checks

### A. The "BMI = Avatar" Flaw
*   **The Issue:** BMI is a notoriously poor indicator of fitness for bodybuilders (it doesn't distinguish between muscle and fat). BMI might label you as *"Obese"*.
*   **The Correction:** Use *Body Fat Percentage* estimates or let users pick a "Path" (**Strength, Cardio, or Balance**) during onboarding. *Do not punish a muscular user with a "Heavy/Slow" avatar.*

### B. The Live Betting Latency
*   **The Issue:** Syncing two live video feeds and running ML pose estimation simultaneously is extremely taxing on battery and data. Latency (lag) will make it impossible to judge who finished a push-up *"0.1 seconds faster"*.
*   **The Correction:** For the MVP, make betting **Asynchronous**. Player A sets a record (video recorded/verified by ML). Player B tries to beat it later. This removes the need for expensive real-time servers.

### C. Safety & Traffic Logic
*   **The Issue:** You cannot realistically know if a user is at a "Don't Walk" sign using standard GPS (which has a `5-10 meter` margin of error).
*   **The Correction:** Avoid "Point A to Point B" speed quests in urban areas. Instead, use *"Stay in the Zone"* quests (e.g., *"Maintain a 5:00 min/km pace for 10 minutes inside this park boundary"*). Parks are safer and GPS signals are clearer.

---

# 💼 The Business Model: Local Bounty

> *To get money from local businesses, we shouldn't just "put a chest" there. We provide **Foot Traffic as a Service**.*

### 🏪 The Merchant Portal
*   A simple web dashboard where a local cafe in Bedford can pay **$50** to host a *"Legendary Chest"* for a weekend.

### 🎯 The Incentive
*   The chest only unlocks if the player is within **10 meters** of the shop.

### 💰 The Conversion
*   Inside the AR chest, the player gets XP plus a digital coupon (e.g., *"20% off a protein smoothie"*).

---

# 🛠️ Technical Stack Recommendation

| Component | Technology | Rationale |
| :--- | :--- | :--- |
| **Language / Backend** | **Python (FastAPI)** | Great for ML integration and rapid API development. |
| **Mobile** | **Flutter** | Handles AR/Camera and GPS much more smoothly for a solo dev than native coding two separate apps. |
| **Machine Learning** | **MediaPipe** | Highly efficient for on-device pose estimation (e.g., push-up counter). |

---

# 🧩 User Stories (Structured & Production-Ready)

## 🔹 Epic 1: User Participation (Core Product)
> **Goal:** Users complete fitness “Bounties” and earn rewards.

### User Story 1.1 – Discover Bounties
*As a fitness user, I want to see nearby bounties on a map so that I can choose a challenge near me.*

**Acceptance Criteria:**
*   [ ] Map shows Bedford zone (*DeWolf Park → Sunnyside Mall*).
*   [ ] Each bounty displays: **Reward**, **Distance**, and **Time validity**.
*   [ ] Only active bounties are visible.

### User Story 1.2 – Start a Bounty
*As a user, I want to start a bounty session so that my activity is tracked.*

**Acceptance Criteria:**
*   [ ] User taps *"Start Run"*.
*   [ ] GPS tracking begins immediately.
*   [ ] Session state is set to `ACTIVE`.
*   [ ] Timer and current distance are visible.

### User Story 1.3 – Complete & Claim Reward
*As a user, I want to claim a reward after completing the route so that I get incentives.*

**Acceptance Criteria:**
*   [ ] User reaches the geo-fenced zone.
*   [ ] Verification engine validates movement.
*   [ ] Reward credited (*wallet / discount*).

## 🔹 Epic 2: Verification Engine (Your MOAT 🔥)
> **Goal:** Prevent cheating → core competitive advantage.

### User Story 2.1 – GPS Geo-Fencing Validation
*As a system, I want to verify user location within a 30–50m radius so that users must physically be at the bounty location.*

**Acceptance Criteria:**
*   [ ] GPS coordinates fall within defined polygon/radius.
*   [ ] Reject if outside radius.
*   [ ] Log entry created for validation.

### User Story 2.2 – Velocity Filtering
*As a system, I want to ensure speed is `< 25 km/h` so that vehicles are filtered out.*

**Acceptance Criteria:**
*   [ ] Speed calculated from GPS timestamps.
*   [ ] If speed > threshold → session invalidated.
*   [ ] Flag suspicious sessions.

### User Story 2.3 – Cadence-Based Movement Detection (ML Core)
*As a system, I want to analyze accelerometer patterns so that I distinguish walking/running from fake motion.*

**Acceptance Criteria:**
*   [ ] Collect accelerometer data (*x, y, z*).
*   [ ] Apply ML classifier:
    *   Human stride → `VALID`
    *   Noise/vibration → `INVALID`
*   [ ] Confidence score `> 85%`.

### User Story 2.4 – Anti-Spoof Detection
*As a system, I want to detect GPS spoofing so that fake locations are rejected.*

**Acceptance Criteria:**
*   [ ] Detect sudden coordinate jumps.
*   [ ] Check unrealistic acceleration.
*   [ ] Cross-check with device sensor consistency.

## 🔹 Epic 3: Business / Partner Flow

### User Story 3.1 – Merchant Creates Bounty
*As a local business, I want to create a weekend sprint offer so that I drive foot traffic.*

**Acceptance Criteria:**
*   [ ] Merchant defines: **Reward amount**, **Max users**, and **Time window**.
*   [ ] Payment processed (`$50` pilot fee).

### User Story 3.2 – Reward Redemption
*As a user, I want to redeem rewards at partner shops so that I can use my earned value.*

**Acceptance Criteria:**
*   [ ] QR / code-based redemption.
*   [ ] One-time usage validation.
*   [ ] Linked to session ID.

---

# ⚙️ SDLC – Phase 1 & 2

## 🚀 Phase 1: Planning & Requirements

### 1. Problem Statement
*Fitness apps are easily manipulated → no trust → low business value.*

### 2. Solution
A **Verified Fitness Reward System** using:
1.  GPS validation.
2.  Velocity filtering.
3.  ML-based cadence detection.

### 3. Scope (Bedford Pilot)
*   **Zone:** DeWolf Park → Sunnyside Mall.
*   **Users:** ~50 per bounty.
*   **Partners:** Local cafes / supplement stores.

### 4. Functional Requirements
*   Map-based bounty discovery.
*   Real-time tracking.
*   Reward distribution.
*   Fraud detection (core).

### 5. Non-Functional Requirements
*   **Latency:** `< 1s` for validation.
*   **Accuracy:**
    *   GPS: `±30m`
    *   ML model: `>85%` precision
*   **Scalability:** Support `1000` concurrent users (future).
*   **Security:** Anti-spoofing and secure reward system.

### 6. Business Constraints
*   **Initial budget:** Low (MVP).
*   **Legal:** Avoid direct cash → prefer credits/discounts.
*   **Region-limited:** Pilot in Bedford.

### 7. Success Metrics (KPIs)
*   Completion rate (%).
*   Fraud detection accuracy.
*   Partner ROI (foot traffic increase).
*   Weekly revenue (target: `$250+`).

## 🏗️ Phase 2: Design & Architecture

### 1. High-Level Architecture

```text
📱 Mobile App (Flutter / React Native)  
⬇️  
🌐 API Gateway (FastAPI / Node)  
⬇️  
⚙️ Backend Services  
├── 📍 Tracking Service  
├── 🛡️ Verification Engine (ML + Rules)  
├── 🎁 Reward Engine  
└── 🏪 Merchant Service  
⬇️  
🗄️ Database (PostgreSQL / DynamoDB)  
⬇️  
🧠 ML Pipeline (Python - PyTorch / Sklearn)  
```

### 2. Verification Engine (Core Design)

*   **Rule-Based Layer (Fast):**
    *   Geo-fencing
    *   Speed threshold
    *   Time consistency
*   **ML Layer (Advanced):**
    *   **Input:** Accelerometer time series
    *   **Features:** Frequency patterns, Step periodicity
    *   **Model:** Random Forest / LSTM (future)
    *   **Output:** `VALID` / `INVALID`

### 3. Data Flow
`User runs` ➔ `GPS + Sensor data collected` ➔ `Sent to backend` ➔ `Verification engine processes` ➔ `Decision returned` ➔ `Reward issued or rejected`.

### 4. Database Design (Simplified Tables)
*   `Users` | `Bounties` | `Sessions` | `SensorData` | `Rewards` | `Merchants`

### 5. Tech Stack Recommendation
*   **Backend:** Python (**FastAPI**)
*   **ML:** PyTorch / Scikit-learn
*   **Mobile:** Flutter *(best for speed + UI)*
*   **Infrastructure:** **AWS:** EC2 / Lambda, DynamoDB / RDS, S3 for logs.
