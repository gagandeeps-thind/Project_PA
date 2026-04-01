# System Development Life Cycle (SDLC)

## Phase 1: Planning & Requirement Analysis
*   **Objective:** Define the "Unit Economics" and the core tech requirements.
*   **Business Logic:** Define the "Bounty" (e.g., a local coffee shop in Bedford pays `$50` for `50` "check-ins").
*   **Fraud Prevention (Your Edge):** Since users will try to "spoof" GPS or shake their phones to mimic running, you need to define the ML requirements for Anomaly Detection (e.g., identifying if a user's velocity matches a car vs. a runner).
*   **Stakeholder Mapping:** Identify 5–10 local businesses in Halifax/Bedford for a pilot program.

## Phase 2: Design & Architecture
*   **Objective:** Create a scalable, real-time system.

*   **System Architecture:**
    *   **Frontend:** React Native or Flutter (for cross-platform iOS/Android).
    *   **Backend:** Node.js or Python (FastAPI) for high-concurrency GPS pings.
    *   **Database:** PostgreSQL with PostGIS extension (essential for geo-spatial queries like *"Is the user within 20 meters of the Bounty?"*).

*   **User Flow:** Wallet Integration (Stripe or Connect) → Map Interface → Activity Verification → Payout.

## Phase 3: Implementation (Development)
*   **Objective:** Build the "Happy Path" (The core loop that works).

*   **Sprint 1 (Geo-fencing):** Develop the map view and the logic that triggers a *"Mission Start"* when a user enters a specific zone.
*   **Sprint 2 (Activity Tracking):** Integrate CoreMotion (iOS) or Google Fit API to verify the user actually ran/walked to the location.
*   **Sprint 3 (The Vault):** Build the "Staking" mechanism where users commit funds via a secure payment gateway.

## Phase 4: Testing & ML Refinement
*   **Objective:** Ensure the "Bounty" can't be gamed.

*   **UAT (User Acceptance Testing):** Conduct an "Alpha" test with friends running between DeWolf Park and a nearby cafe.
*   **ML Model Training:** Use the data from the Alpha test to train a simple Random Forest or XGBoost classifier to differentiate between walking, running, biking, and driving based on accelerometer and GPS data.

## Phase 5: Deployment & Pilot Launch
*   **Objective:** Go live in a small, controlled area.

*   **Cloud Hosting:** Deploy the backend on AWS (using Lambda for cost-efficiency) or Google Cloud.
*   **The "Bedford Pilot":** Launch exclusively in the Bedford/Halifax area. This allows you to physically visit the partner businesses and gather feedback.

## Phase 6: Operations & Maintenance
*   **Objective:** Scale and automate.

*   **Dashboard for Businesses:** Build a simple web portal where shop owners can see how many people visited their store via your app and what their "Cost Per Acquisition" (CPA) was.
*   **Feedback Loop:** Use the analytics to see where users "drop off"—do they quit if the run is longer than 5km? Adjust the Bounty algorithm accordingly.