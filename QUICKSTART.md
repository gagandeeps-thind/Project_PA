# Osiris Quick Start Guide

This project consists of three main applications and a central backend:

## Project Structure
- `Osiris_backend/`: FastAPI backend server. Handles core logic, payments, and connects to the SQLite db (`fitness_mvp.db`).
- `Osiris_admin_web/`: Vite/React admin panel for managing the ecosystem.
- `Osiris_customer/`: Flutter mobile app for players (customers) to claim territories and engage in fitness activities.
- `Osiris_merchant/`: Flutter mobile app for merchants to issue bounties, check analytics, and manage their store presence in the game.

## Prerequisites
- Node.js & npm (for Admin Web)
- Python 3 (for Backend)
- Flutter & Android Studio/Command-line tools (for Mobile Apps)
- The local Python virtual environment `.venv` is located at the root of the project.

## Running the Project

### 1. Backend
To run the backend locally on port 8000:
```sh
cd Osiris_backend
..\.venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0
```

### 2. Admin Web Panel
To run the React admin portal:
```sh
cd Osiris_admin_web
npm install
npm run dev
```

### 3. Mobile Apps (Customer & Merchant)
First, ensure an Android emulator is running:
```sh
flutter emulators --launch test_device
```
*(If the flutter command doesn't start the emulator properly, use the android CLI wrapper if available, or start from Android Studio).*

Then, to run the apps:
```sh
# For Customer App:
cd Osiris_customer
flutter run -d emulator-5554

# For Merchant App:
cd Osiris_merchant
flutter run -d emulator-5554
```

## Troubleshooting
- If `Osiris_merchant` fails to run complaining about a missing `lib/main.dart`, ensure that it is restored (as it may have been deleted during previous architecture audits).
- For API issues on the Android emulator, check `Osiris_frontend/lib/api/api_client.dart` to make sure the base URL points to `http://10.0.2.2:8000` (which loops back to localhost on the host machine).
