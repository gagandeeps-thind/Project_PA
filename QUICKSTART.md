# Osiris Quick Start Guide

This project consists of a player mobile app (Android + iOS), an admin console, an optional partner app, and a central backend:

## Project Structure
- `Osiris_backend/`: FastAPI backend server. Handles core logic, payments, and connects to the SQLite db (`fitness_mvp.db`).
- `Osiris_admin_web/`: Vite/React admin panel for managing the ecosystem.
- `shared/`, `android_version/`, `ios_version/`: Kotlin Multiplatform player app (verified runs, quests, courses, challenges, communities, exercises, progression). See `docs/architecture/README.md`.

## Prerequisites
- Node.js & npm (for Admin Web)
- Python 3 (for Backend)
- Android Studio (its bundled JDK and the Android SDK) for the Android app; Xcode for the iOS app
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

### 3. Player App (Android)
Start an emulator (from Android Studio, or `%LOCALAPPDATA%\Android\Sdk\emulator\emulator -avd test_device`), then from the repo root:
```sh
export ANDROID_HOME="$LOCALAPPDATA/Android/Sdk" JAVA_HOME="/c/Program Files/Android/Android Studio/jbr"
./gradlew :android_version:app:installDebug
```
The iOS app: see `ios_version/README.md`.

## Troubleshooting
- For API issues on the Android emulator, check `config/environments/dev.properties` and confirm the API base URL is `http://10.0.2.2:8000`.
