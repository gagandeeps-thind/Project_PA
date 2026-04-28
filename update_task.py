import re

def update_task_md():
    with open("c:/Folder D/Project_PA/Task.md", "r", encoding="utf-8") as f:
        content = f.read()

    # The goal is to insert `# Backend` before `## 2. Completed Milestones`
    # And then replace the entire `## 7. Frontend Track` section with `# Frontend` and the new epics.

    # 1. Insert # Backend
    backend_start = "## 2. Completed Milestones"
    if "# Backend\n\n## 2. Completed Milestones" not in content:
        content = content.replace(backend_start, "# Backend\n\n" + backend_start)

    # 2. Extract up to ## 7. Frontend Track (Google Antigravity — Parallel Workstream)
    frontend_track_str = "## 7. Frontend Track (Google Antigravity — Parallel Workstream)"
    if frontend_track_str in content:
        before_frontend = content.split(frontend_track_str)[0]
        
        # Everything after frontend track up to ## 8. How to Resume
        after_frontend_track = "## 8. How to Resume This Project (Cold-Start Guide)"
        if after_frontend_track in content:
            after_frontend_parts = content.split(after_frontend_track)
            tail = after_frontend_track + after_frontend_parts[1]
        else:
            tail = ""

        # Remove frontend mentions in the backend Sprint Backlog
        before_frontend = re.sub(
            r"\*\*Frontend Track — Flutter \(in Google Antigravity\)\*\*\n- 📋 Bootstrap project; pull OpenAPI spec from FastAPI \/docs\.\n- 📋 Screens: Awakening \(register\), Login, Dashboard, Map, Bounty list\.\n- 📋 Wire `device_timestamp` \(use `DateTime\.now\(\)\.toUtc\(\)\.toIso8601String\(\)` on every activity call\)\.",
            "", before_frontend
        )
        # Clean up empty lines
        before_frontend = before_frontend.replace("\n\n\n\n", "\n\n")

        new_frontend_section = """# Frontend

## 1. Active Sprint — Next Up (Frontend)

**Epic 1 — Frontend Scaffold & Core Systems**
- [ ] Create `Osiris_frontend` directory and initialize Flutter project.
- [ ] Generate and configure OpenAPI Dart client from FastAPI backend.
- [ ] Set up routing system and core theme (Dark RPG Aesthetic).
- [ ] Implement secure local storage for session management.

**Epic 2 — Onboarding & Auth ("The Awakening")**
- [ ] Build Login Screen.
- [ ] Build Registration/Onboarding Flow (Height, Weight, Age, Gender).
- [ ] Implement Avatar Class selection (Strength / Cardio / Balance).
- [ ] Wire up to `POST /api/v1/onboard` and `POST /api/v1/login`.

## 2. Backlog — Phase 1 (Frontend)

**Epic 3 — Map & Domain Expansion**
- [ ] Build the Main Map View (centered on user's location).
- [ ] Implement "Start Domain" GPS polling and breadcrumb drawing on the map.
- [ ] Implement "Close Domain" logic (checking within 20m of start) and Defense Feat prompt.
- [ ] Wire up `POST /api/v1/domains` for land claiming.

**Epic 4 — Bounty Board & Economy**
- [ ] Build Bounty List/Map View (fetching from `GET /api/v1/bounties/nearby`).
- [ ] Implement AR / Chest unlocking sequence when within range.
- [ ] Wire up `POST /api/v1/bounties/{id}/complete` and display coupon codes.
- [ ] Implement Vault UI to manage Mana Crystals and Ownership Fees.

**Epic 5 — Profile & Adventure Party**
- [ ] Build Profile Screen showing STR / AGI / END / CON.
- [ ] Fetch and display Party Role via `GET /api/v1/users/{id}/party-role`.
- [ ] Display current Rank and progression.

"""
        
        # update version
        before_frontend = re.sub(r"\| \*\*Version\*\* \| 2.3 \|", "| **Version** | 2.4 |", before_frontend)
        
        content = before_frontend + new_frontend_section + tail
        
        # update revision history
        rev_history = "| 2.4 | 2026-04-27 | AI | Restructured Task.md into # Backend and # Frontend sections; mapped Frontend Epics 1-5 |\n"
        content += rev_history

        with open("c:/Folder D/Project_PA/Task.md", "w", encoding="utf-8") as f:
            f.write(content)

if __name__ == "__main__":
    update_task_md()
