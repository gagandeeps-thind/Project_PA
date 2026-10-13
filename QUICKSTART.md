# Osiris Quick Start Guide

This project consists of a customer mobile app, an admin console, an optional partner app, and a central backend:

## Project Structure
- `Osiris_backend/`: FastAPI backend server. Handles core logic, payments, and connects to the SQLite db (`fitness_mvp.db`).
- `Osiris_admin_web/`: Vite/React admin panel for managing the ecosystem.
- `Osiris_customer/`: Flutter mobile app for players to complete verified runs, quests, courses, challenges, communities, and progression.
- `Osiris_merchant/`: Future partner app retained for sponsor/merchant functionality; it is not required for the first player release.

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

### 3. Customer Mobile App
First, ensure an Android emulator is running:
```sh
flutter emulators --launch test_device
```
*(If the flutter command doesn't start the emulator properly, use the android CLI wrapper if available, or start from Android Studio).*

Then, to run the apps:
```sh
# Customer app:
cd Osiris_customer
flutter run -d emulator-5554
```

## Troubleshooting
- For API issues on the Android emulator, check `Osiris_customer/lib/api/api_client.dart` and confirm the base URL is `http://10.0.2.2:8000`.
