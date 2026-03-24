# 🧩 1. USER STORIES (Structured & Production-Ready)

## 🔹 Epic 1: User Participation (Core Product)

***Goal: Users complete fitness “Bounties” and earn rewards.***

**User Story 1.1 – Discover Bounties**
As a fitness user
I want to see nearby bounties on a map
So that I can choose a challenge near me

**Acceptance Criteria**

*   Map shows Bedford zone (DeWolf Park → Sunnyside Mall)
*   Each bounty displays:
    *   Reward
    *   Distance
    *   Time validity
*   Only active bounties are visible

**User Story 1.2 – Start a Bounty**
As a user
I want to start a bounty session
So that my activity is tracked

**Acceptance Criteria**

*   User taps “Start Run”
*   GPS tracking begins
*   Session state = ACTIVE
*   Timer + distance visible

**User Story 1.3 – Complete & Claim Reward**
As a user
I want to claim reward after completing the route
So that I get incentives

**Acceptance Criteria**

*   User reaches geo-fenced zone
*   Verification engine validates movement
*   Reward credited (wallet / discount)

## 🔹 Epic 2: Verification Engine (Your MOAT 🔥)

***Goal: Prevent cheating → core competitive advantage***

**User Story 2.1 – GPS Geo-Fencing Validation**
As a system
I want to verify user location within 30–50m radius
So that users must physically be at the bounty location

**Acceptance Criteria**

*   GPS coordinates fall within defined polygon/radius
*   Reject if outside radius
*   Log entry created for validation

**User Story 2.2 – Velocity Filtering**
As a system
I want to ensure speed < 25 km/h
So that vehicles are filtered out

**Acceptance Criteria**

*   Speed calculated from GPS timestamps
*   If speed > threshold → session invalidated
*   Flag suspicious sessions

**User Story 2.3 – Cadence-Based Movement Detection (ML Core)**
As a system
I want to analyze accelerometer patterns
So that I distinguish walking/running from fake motion

**Acceptance Criteria**

*   Collect accelerometer data (x, y, z)
*   Apply ML classifier:
    *   Human stride → VALID
    *   Noise/vibration → INVALID
*   Confidence score > threshold (e.g., 85%)

**User Story 2.4 – Anti-Spoof Detection**
As a system
I want to detect GPS spoofing
So that fake locations are rejected

**Acceptance Criteria**

*   Detect sudden coordinate jumps
*   Check unrealistic acceleration
*   Cross-check with device sensor consistency

## 🔹 Epic 3: Business / Partner Flow

**User Story 3.1 – Merchant Creates Bounty**
As a local business
I want to create a weekend sprint offer
So that I drive foot traffic

**Acceptance Criteria**

*   Merchant defines:
    *   Reward amount
    *   Max users
    *   Time window
*   Payment processed ($50 pilot fee)

**User Story 3.2 – Reward Redemption**
As a user
I want to redeem rewards at partner shops
So that I can use my earned value

**Acceptance Criteria**

*   QR / code-based redemption
*   One-time usage validation
*   Linked to session ID

# ⚙️ 2. SDLC – PHASE 1 & 2

## 🚀 PHASE 1: PLANNING & REQUIREMENTS

**1. Problem Statement**

Fitness apps are easily manipulated → no trust → low business value.

**2. Solution**

A Verified Fitness Reward System using:

*   GPS validation
*   Velocity filtering
*   ML-based cadence detection

**3. Scope (Bedford Pilot)**
*   **Zone**: DeWolf Park → Sunnyside Mall
*   **Users**: ~50 per bounty
*   **Partners**: Local cafes / supplement stores

**4. Functional Requirements**
*   Map-based bounty discovery
*   Real-time tracking
*   Reward distribution
*   Fraud detection (core)

**5. Non-Functional Requirements**
*   **Latency**: < 1s for validation
*   **Accuracy**:
    *   GPS: ±30m
    *   ML model: >85% precision
*   **Scalability**:
    *   Support 1000 concurrent users (future)
*   **Security**:
    *   Anti-spoofing
    *   Secure reward system

**6. Business Constraints**
*   Initial budget: low (MVP)
*   Legal: avoid direct cash → prefer credits/discounts
*   Region-limited pilot

**7. Success Metrics (KPIs)**
*   Completion rate %
*   Fraud detection accuracy
*   Partner ROI (foot traffic increase)
*   Weekly revenue (target: $250+)

## 🏗️ PHASE 2: DESIGN & ARCHITECTURE

**1. High-Level Architecture**

Mobile App (Flutter / React Native)
↓
API Gateway (FastAPI / Node)
↓
Backend Services
├── Tracking Service
├── Verification Engine (ML + Rules)
├── Reward Engine
└── Merchant Service
↓
Database (PostgreSQL / DynamoDB)
↓
ML Pipeline (Python - PyTorch / Sklearn)

**2. Verification Engine (Core Design)**

*   **Rule-Based Layer (Fast)**
    *   Geo-fencing
    *   Speed threshold
    *   Time consistency
*   **ML Layer (Advanced)**
    *   **Input**:
        *   Accelerometer time series
    *   **Features**:
        *   Frequency patterns
        *   Step periodicity
    *   **Model**:
        *   Random Forest / LSTM (future)
    *   **Output**:
        *   VALID / INVALID

**3. Data Flow**

User runs →
GPS + Sensor data collected →
Sent to backend →
Verification engine processes →
Decision returned →
Reward issued or rejected

**4. Database Design (Simplified)**

*   **Tables**:
    *   Users
    *   Bounties
    *   Sessions
    *   SensorData
    *   Rewards
    *   Merchants

**5. Tech Stack Recommendation (for YOU)**

Given your background:

*   **Backend**
    *   Python (FastAPI)
*   **ML**: PyTorch / Scikit-learn
*   **Mobile**
    *   Flutter (best for speed + UI)
*   **Infra**
    *   **AWS**:
        *   EC2 / Lambda
        *   DynamoDB / RDS
        *   S3 for logs

**6. Risk Analysis**

| Risk             | Mitigation                  |
| ---------------- | --------------------------- |
| GPS spoofing     | Sensor fusion               |
| Fake motion      | ML cadence detection        |
| Low adoption     | Gamification                |
| Merchant churn   | ROI tracking dashboard      |
