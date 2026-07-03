# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview
JARVIS (Just A Rather Very Intelligent System) is a voice-first AI assistant for macOS. It runs locally, connecting to Apple Calendar, Mail, and Notes via AppleScript, and can spawn Claude Code sessions for development tasks. Note: the AppleScript integrations only work on macOS — on Linux/CI, verify changes with the test suite instead of running the app.

## First-Time Setup (walk users through this)
When a user clones this repo and starts Claude Code, help them:
1. Copy .env.example to .env
2. Get an Anthropic API key from console.anthropic.com
3. Get a Fish Audio API key from fish.audio
4. Install Python dependencies: `pip install -r requirements.txt`
5. Install frontend dependencies: `cd frontend && npm install`
6. Generate SSL certs: `openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'`
7. Run the backend: `python server.py`
8. Run the frontend: `cd frontend && npm run dev`
9. Open Chrome to http://localhost:5173 (Chrome required — the app uses the Web Speech API)
10. Click to enable audio, speak to JARVIS

## Commands
```bash
# Backend (port 8340; SSL auto-enables when cert.pem/key.pem exist)
python server.py [--port 8340] [--reload] [--ssl]

# Frontend dev server (port 5173, proxies /ws and /api to https://localhost:8340)
cd frontend && npm run dev

# Frontend typecheck + production build
cd frontend && npm run build

# Tests (pytest + pytest-asyncio)
pip install -r requirements-dev.txt
pytest tests/
pytest tests/test_feedback_loop.py -k test_name   # single test
python3 tests/test_classifier.py                  # standalone script; needs ANTHROPIC_API_KEY

# Log monitor (runs alongside the server, flags conversation-quality issues)
python monitor.py
```
There is no linter configured. Browser tests (`test_browser_integration.py`) need network + Playwright browsers and skip themselves otherwise; `test_e2e_pipeline.py` and `test_feedback_loop.py` mock Claude Code execution and run anywhere. CI (`.github/workflows/ci.yml`) runs `pytest tests/` and the frontend build on every PR.

## Architecture

### Voice loop (the core path)
Chrome Web Speech API transcribes speech → transcript sent over WebSocket `/ws/voice` → `server.py` classifies intent (fast keyword pass in `detect_action_fast()`, then LLM classifier `classify_intent()` on Haiku) → response generated on Haiku with `[ACTION:X]` tags extracted by `extract_action()` → action handlers execute (AppleScript, Claude Code subprocess, browser) → Fish Audio TTS → audio streamed back over the WebSocket → Three.js orb reacts. Slow lookups (calendar, mail, screen) run as background tasks that report back via voice when done, so responses never block.

`server.py` (~2,700 lines) is a deliberate monolith and the hub of everything: config, `ClaudeTaskManager`, action handlers, the WebSocket voice handler, REST/settings endpoints, and usage tracking. Refactoring pieces into modules is welcome per CONTRIBUTING.md, but don't break the voice loop.

### Build-task intelligence layer (spans several modules)
When the user asks JARVIS to build something, the request flows through a pipeline rather than going straight to Claude Code:

1. `planner.py` — detects planning mode vs. quick chat, asks 1-3 voice-friendly clarifying questions, confirms a plan, then assembles a structured prompt from templates + project context. `conversation.py` holds the multi-turn planning session state (5-min timeout).
2. `templates.py` + `templates/prompts/*.yaml` — prompt templates keyed by task type; the YAML files hold evolved versions.
3. `ab_testing.py` — picks which template version to use for a task type and records the assignment.
4. Execution — `actions.py` / `work_mode.py` spawn `claude -p` subprocesses (`work_mode.py` keeps persistent sessions). `dispatch_registry.py` records every dispatch so JARVIS knows what "it" refers to later.
5. `qa.py` — a QA agent (another `claude -p` subprocess) verifies the output and auto-retries up to 3 times.
6. `tracking.py` → `evolution.py` — success/failure metrics feed template evolution, which writes improved template versions back to `templates/prompts/`; `learning.py` tracks usage patterns to pre-load context. `suggestions.py` offers one heuristic follow-up per completed task (file checks, no LLM calls).

### Storage — two SQLite databases, both in `data/`
- `data/jarvis.db` — user-facing memory (`memory.py`, FTS5 full-text search) and the dispatch registry.
- `data/jarvis_data.db` — intelligence-layer metrics (`tracking.py`, `learning.py`, `ab_testing.py`, `evolution.py`). The path comes from `db_paths.intelligence_db_path()`, which auto-migrates a legacy root-level `jarvis_data.db` if one exists.

### macOS integration
All system access goes through AppleScript (`calendar_access.py`, `mail_access.py`, `notes_access.py`, `actions.py`, `screen.py`) — no OAuth. Any string interpolated into AppleScript must go through `applescript_escape()` (`actions.py`); `tests/test_applescript_escape.py` guards this. `JARVIS_SKIP_PERMISSIONS` defaults to true because voice-driven `claude` subprocesses can't answer interactive permission prompts (they'd hang silently).

### Frontend (`frontend/src/`)
`main.ts` is the state machine, `voice.ts` handles Web Speech API + audio playback, `ws.ts` is a reconnecting WebSocket client, `orb.ts` is the Three.js particle orb, `settings.ts` drives the settings panel backed by the `/api/settings/*` endpoints.

## Environment Variables
- `ANTHROPIC_API_KEY` (required), `FISH_API_KEY` (required)
- `FISH_VOICE_ID`, `USER_NAME`, `CALENDAR_ACCOUNTS` (optional)
- `JARVIS_SKIP_PERMISSIONS` (default true — see above)
- `WEATHER_LOCATION_LABEL` / `WEATHER_LATITUDE` / `WEATHER_LONGITUDE` / `WEATHER_UNIT` (optional; defaults to IP-based location, Fahrenheit)

## Conventions
- JARVIS personality: British butler, dry wit, economy of language. Max 1-2 sentences per voice response — responses are spoken aloud.
- Mail is READ-ONLY by design. Don't add features that modify or delete user data in Mail, Calendar, or Notes.
- No telemetry/analytics; no external services beyond Anthropic and Fish Audio. Don't add dependencies unless necessary.
- SQLite for all local data storage.
- Claude Haiku for fast voice responses, Claude Opus for research/deep tasks.
