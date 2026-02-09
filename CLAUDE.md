# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GPS location simulator for iOS devices. Cross-platform Electron desktop app with React frontend and Python backend.

## Development Commands

```bash
# Install dependencies
npm install
pip install -r backend/requirements.txt

# Development (runs Vite + Electron concurrently)
npm run dev

# Frontend only (Vite dev server on port 5173)
npm run dev:vite

# Electron only
npm run dev:electron

# Build frontend
npm run build

# Build packaged app for distribution
npm run build:electron

# Browser mode (HTTP backend instead of Electron IPC)
npm run dev:browser

# Testing
npm run test:run          # Frontend (vitest)
npm run test:backend      # Backend (pytest)
npm run test:all          # Both

# Run single test file
npx vitest run src/hooks/useMovement.test.js
cd backend && .venv/bin/pytest test_tunnel.py -v
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Electron (electron/main.js)                                │
│  └─ Creates window, spawns Python subprocess                │
└─────────────────────────────────────────────────────────────┘
                        ↕ IPC (preload.js)
┌─────────────────────────────────────────────────────────────┐
│  React Frontend (src/)                                      │
│  ├─ App.jsx - Main component, state management              │
│  ├─ hooks/useBackend.js - Backend communication (IPC/HTTP)  │
│  ├─ hooks/useMovement.js - Cruise/joystick calculations     │
│  ├─ hooks/useFavorites.js - Saved locations management      │
│  ├─ hooks/useRouteCruise.js - Route cruise state management │
│  └─ components/                                             │
│     ├─ MapWidget - Leaflet map with click-to-set location   │
│     ├─ DevicePanel - Device selection and tunnel controls   │
│     ├─ ControlPanel - Location input, cruise, joystick      │
│     ├─ RoutePanel - Route mode waypoints and cruise control │
│     ├─ FavoritesManager - Save/load favorite locations      │
│     └─ DebugPage - Port forwarding and debug tools          │
└─────────────────────────────────────────────────────────────┘
                ↕ JSON-RPC (stdin/stdout via python-bridge.js)
┌─────────────────────────────────────────────────────────────┐
│  Python Backend (backend/)                                  │
│  ├─ main.py - Server entry point (stdin/stdout or HTTP)     │
│  ├─ models.py - Device and tunnel dataclasses               │
│  └─ services/                                               │
│     ├─ device_manager.py - Discover simulators & devices    │
│     ├─ location_service.py - Inject GPS coordinates         │
│     ├─ tunnel_manager.py - RSD tunnels for iOS 17+          │
│     ├─ cruise_service.py - Backend cruise mode logic        │
│     ├─ route_service.py - Multi-waypoint route cruise       │
│     ├─ brouter_service.py - Brouter pathfinding integration │
│     ├─ favorites_service.py - Saved locations persistence   │
│     ├─ last_location_service.py - Per-device location cache │
│     ├─ port_forward_service.py - TCP port forwarding        │
│     ├─ event_bus.py - Backend event system                  │
│     └─ coordinate_utils.py - Geographic calculations        │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  iOS Devices                                                │
│  ├─ Simulators → xcrun simctl                               │
│  └─ Physical → pymobiledevice3 (USB/WiFi or RSD tunnel)     │
└─────────────────────────────────────────────────────────────┘
```

## Key Technical Details

**Communication Protocol:**
- **Electron mode:** JSON-RPC over stdin/stdout between Electron and Python subprocess. Requests/responses are JSON lines. Backend logs go to stderr.
- **Browser mode:** HTTP REST API + SSE (Server-Sent Events) for real-time updates. Backend runs standalone HTTP server on port 8765.

**Device Support:**
- Simulators: Uses `xcrun simctl` for device discovery and location injection
- Physical iOS ≤16: Direct USB/WiFi via pymobiledevice3 lockdown
- Physical iOS 17+: Requires RSD tunnel (TunnelManager) before location injection

**Geographic Calculations:** All coordinate math (Haversine distance, bearing, cruise interpolation) happens in frontend (`src/utils/coordinateCalculator.js`). Backend receives final lat/lng only.

**Python Discovery:** `electron/python-bridge.js` searches asdf, pyenv, homebrew, then system Python. Requires Python 3.13+ with pymobiledevice3.

**Data Persistence:**
- Favorites: `~/.location-simulator/favorites.txt` as CSV (latitude,longitude,name). Auto reverse-geocoding via Nominatim API.
- Last locations: `~/.location-simulator/last_locations.json` stores most recent GPS position per device for restoration on selection.

**Cruise Mode:** Can run in frontend (useMovement.js) or backend (cruise_service.py). Backend mode provides smoother updates and continues running even if frontend is closed.

**Route Cruise Mode:** Multi-waypoint pathfinding-based routing. Users click map in "Route" mode to add waypoints; Brouter calculates hiking paths between them. RouteService is a sequencer that delegates point-pair movement to CruiseService. Supports loop mode (auto-closure segment), pause/resume, dynamic speed, undo waypoint. Falls back to straight line if Brouter is unavailable. Configuration: `BROUTER_API_URL` env var (default: `https://brouter.de/brouter`).

**Debug Features:** TCP port forwarding service allows remote debugging of iOS devices over RSD tunnels. DebugPage component provides UI for managing forwarding rules.
