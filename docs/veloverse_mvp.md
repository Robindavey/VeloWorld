# VeloVerse — MVP Plan

## Objective

Build a minimal but fully functional version of VeloVerse capable of turning a GPX route into a rideable indoor cycling experience. The MVP proves the core value proposition — that any GPS route can become a physics-accurate indoor ride — and establishes the technical foundations on which all subsequent features will be built.

The MVP is not a prototype. It must be stable, deployable, and usable by real cyclists. It will be used for early access user testing, investor demonstrations, and as the base for rapid iteration.

---

## MVP Definition Principles

**Include only what proves the core value proposition.** Features that are compelling but not essential to the core loop (upload route → ride route) are deferred.

**Physics accuracy is not optional.** The gradient-resistance physics simulation is the entire point. The MVP must deliver accurate trainer resistance. A simplified physics model that "feels about right" is not acceptable.

**Visual fidelity is optional at MVP.** The environment can be basic — flat-shaded terrain, simple trees, minimal buildings — as long as it is functional and not actively unpleasant to ride in.

**Smart trainer integration is required.** Without smart trainer support, the platform is a video game. Trainer integration is what makes it a training tool.

---

## Core MVP Feature Set

### 1. GPX Route Upload

**What it does:**
The user uploads a GPX file through a web interface or desktop app. The system validates the file, extracts coordinates and metadata, and queues it for processing.

**Acceptance criteria:**
- GPX files from Garmin, Wahoo, and Strava exports parse correctly
- Files with fewer than 100 points or less than 500m distance are rejected with a clear error
- Upload progress is shown to the user
- User receives a notification (in-app or email) when the route is ready

**Out of scope for MVP:**
- FIT and TCX format support (can be added as format converters in Phase 2)
- Route editing tools
- Bulk upload

---

### 2. Route Processing Pipeline (MVP Subset)

The full pipeline has six stages. The MVP implements all stages but with reduced fidelity at the environment generation stage.

**Stage 1 — GPX Parsing**: Full implementation. GPSBabel or custom parser.

**Stage 2 — Map Matching**: Full implementation using Valhalla (self-hosted) or Mapbox API. Must return road type and surface classification.

**Stage 3 — Terrain Reconstruction**: Full implementation. LiDAR data for USA and Europe (USGS + Copernicus DEM). SRTM 30m fallback for all other regions.

**Stage 4 — Road Mesh Generation**: Full implementation. Accurate gradients, corner geometry, surface type. This directly feeds the physics engine.

**Stage 5 — Environment Generation (MVP simplified)**: Basic terrain mesh, procedural vegetation placement (one biome type per run for MVP — expand in Phase 2), simple sky and lighting. Buildings deferred to Phase 2.

**Stage 6 — Asset Pipeline**: Core asset library only. Approximately 50–100 vegetation assets covering alpine, forest, and lowland biomes. Road furniture basics.

**Processing time target**: Under 5 minutes for routes up to 100km. This is acceptable for MVP (target will tighten to <3 minutes in Phase 2).

---

### 3. 3D Terrain and Road Rendering

**What it does:**
Renders the generated route environment in real time as the rider progresses. The camera follows the rider from a configurable viewpoint (first-person, third-person, side-on).

**Rendering engine**: Unreal Engine 5 (MVP uses standard Lumen/Nanite pipeline). No custom shaders required at MVP.

**Acceptance criteria:**
- Route renders without visible artefacts at the road surface
- Frame rate: 60 FPS on recommended hardware (RTX 3070 or better)
- Gradient-consistent terrain (visual terrain matches physics gradient)
- Day/night cycle: not required for MVP (fixed mid-day lighting is acceptable)
- Weather: not required for MVP

---

### 4. Smart Trainer Integration

**What it does:**
Pairs with a smart trainer over Bluetooth or ANT+. Reads rider power and cadence. Sends resistance commands based on the physics engine output.

**Protocols:**
- Bluetooth FTMS (mandatory — covers all modern trainers)
- ANT+ FE-C (required to support Garmin ecosystem trainers)

**Supported trainers at MVP:**
- Wahoo KICKR (BLE + ANT+)
- Tacx NEO 2T (BLE + ANT+)
- Elite Direto XR (BLE + ANT+)
- Any FTMS-compliant trainer (broad compatibility)

**Acceptance criteria:**
- Trainer pairs within 30 seconds of opening connection screen
- Resistance updates within one simulation frame (16.7ms) of physics calculation
- Gradient simulation mode works across the full route
- ERG mode is functional for power-target intervals
- Cadence and power data are read and displayed correctly

**Trainer abstraction layer:**
Implement a hardware abstraction interface from the start. All trainer-specific code sits behind this interface. Adding support for a new trainer requires only implementing the interface, not modifying the physics engine.

---

### 5. Solo Riding Mode

**What it does:**
The rider selects a route from their library and starts a ride. The simulation runs: route renders, trainer receives resistance commands, rider progresses along the route, HUD displays ride data.

**HUD elements (MVP):**
- Current power (W)
- Current speed (km/h)
- Current gradient (%)
- Distance covered (km)
- Distance remaining (km)
- Elapsed time
- Estimated completion time
- Mini-map / route profile with current position

**Session completion:**
When the rider reaches the end of the route, the session ends. A summary screen shows: total distance, total time, average power, average speed, elevation gained, elevation lost.

**Ride data is saved** to the user's ride history. No external export at MVP.

**Acceptance criteria:**
- Rider can complete a full route from start to finish without crashes or freezes
- HUD data is accurate and updates in real time
- Session summary is displayed and saved
- Rider can pause and resume a session

---

### 6. User Accounts and Route Library

**What it does:**
User registration, login, and personal route library. Each user has a list of their uploaded routes and can manage them.

**Authentication:**
- Email + password
- Google OAuth (reduces friction)

**Route library:**
- List of uploaded routes
- Route metadata (name, distance, elevation gain, processing status)
- Delete route

**Acceptance criteria:**
- Registration and login work correctly
- Routes are associated with the correct user account
- Route processing status is visible (queued, processing, ready, failed)

---

### 7. Community Route Sharing (Basic)

**What it does:**
Users can make their routes public. A simple route browser lets other users discover and download community routes.

**MVP scope:**
- Toggle route visibility (private / public)
- Browse public routes (list view, sortable by distance, elevation, recency)
- Download and add a route from the community library to your personal library

**Not included in MVP:**
- Route ratings or reviews
- Route collections or categories
- Search by location or region
- Curated or featured routes
- Route marketplace / paid routes

---

## Not Included in MVP

| Feature | Reason for Deferral | Target Phase |
|---|---|---|
| Multiplayer / group rides | Significant networking complexity; not essential to core loop | Phase 3 |
| FIT / TCX file support | GPX covers most use cases; format converters can be added cheaply later | Phase 2 |
| Advanced environment (buildings, full biomes) | Nice-to-have; doesn't affect physics or core experience | Phase 2 |
| Weather simulation (rain, wind effects) | High engineering effort; not essential to MVP | Phase 3 |
| VR support | Hardware requirement limits accessibility; defer until core is solid | Phase 4 |
| Smart glasses HUD | Niche use case for MVP audience | Phase 4 |
| Route marketplace (paid routes) | Requires payment infrastructure; premature for MVP | Phase 3 |
| AI training coach | Complex product feature; build core training tools first | Phase 4 |
| Race recon / team mode | Requires multiplayer and weather; defer | Phase 3 |
| Mobile companion app | Desktop app is sufficient for MVP | Phase 3 |
| Tyre / bike configuration | Useful but not essential; default values are adequate | Phase 2 |
| Route editing tools | Power feature; not needed at MVP | Phase 2 |

---

## Technical Stack — MVP

| Component | Technology |
|---|---|
| Client (rendering + physics) | Unreal Engine 5 + C++ |
| Physics engine | Custom C++ (no third-party physics library for MVP) |
| Smart trainer BLE | BlueZ (Linux) / Windows BLE API / macOS CoreBluetooth |
| Smart trainer ANT+ | libant or OpenANT |
| Route processing backend | Python (pipeline workers) |
| API backend | Go + REST (gRPC deferred to Phase 2) |
| Database | PostgreSQL |
| Cache | Redis |
| Object storage | AWS S3 |
| LiDAR processing | GDAL, rasterio, numpy |
| Map matching | Valhalla (self-hosted) |
| Terrain data | USGS 3DEP API + Copernicus DEM |
| Auth | JWTs + Google OAuth |
| Deployment | Docker + AWS EC2 (basic; Kubernetes in Phase 2) |

---

## Development Timeline

### Phase 1 — Research and Architecture (Months 1–2)

**Goal:** Validate technical assumptions before building.

- Evaluate LiDAR data sources and APIs; test terrain reconstruction pipeline on 3–5 real routes
- Evaluate map matching services (Valhalla vs Mapbox); validate road geometry output
- Set up development environment; choose and configure Unreal Engine 5 project
- Implement basic smart trainer communication (BLE FTMS read/write)
- Define data schemas for routes, users, rides
- Build CI/CD pipeline and development infrastructure

**Deliverable:** Technical proof-of-concept — a single hardcoded route with accurate terrain mesh, rendering in Unreal, with trainer resistance responding to gradient. Not user-facing.

---

### Phase 2 — Core Pipeline and Physics (Months 3–5)

**Goal:** Build the automated route pipeline and physics simulation.

- Build full GPX → road mesh pipeline (Stages 1–4)
- Implement simplified environment generation (Stage 5 MVP version)
- Implement physics simulation engine: gravity, rolling resistance, aerodynamic drag
- Integrate physics engine with Unreal Engine renderer
- Full smart trainer integration (BLE + ANT+)
- Basic solo riding mode (no HUD polish, functional only)
- Internal testing on 10–20 real routes across different terrain types

**Deliverable:** A working ride — upload GPX, ride in simulation with correct trainer resistance. Internal use only. Rough visually.

---

### Phase 3 — User Experience and Accounts (Months 6–9)

**Goal:** Make the product usable by external testers.

- User registration, authentication, and account management
- Route library and basic route management
- HUD design and implementation
- Session recording and ride history
- Community route sharing (basic)
- UX polish on route upload flow and riding interface
- Performance optimisation (frame rate, loading times)
- Windows and macOS client builds
- Closed alpha with 20–50 invited users

**Deliverable:** Closed alpha — functional product, invitable to trusted external testers.

---

### Phase 4 — Beta Preparation (Months 9–12)

**Goal:** Stabilise and scale for public beta.

- Bug fixing and stability pass from alpha feedback
- Route processing performance improvements
- Expanded LiDAR data source coverage
- Expanded trainer compatibility testing and calibration profiles
- Route processing queue improvements (handle concurrent users)
- Basic analytics and error reporting (Sentry, Datadog)
- Steam or standalone launcher packaging
- Open beta or waitlist-gated launch

**Deliverable:** Public beta — available to general users via waitlist or Steam early access.

---

## Success Metrics for MVP

| Metric | Target |
|---|---|
| Route processing success rate | >95% of valid GPX uploads produce a rideable route |
| Physics accuracy | Trainer gradient within ±0.5% of LiDAR-measured actual gradient |
| Route processing time (median) | <5 minutes for routes up to 100km |
| Client frame rate | 60 FPS on RTX 3070 at 1080p |
| Trainer pairing success rate | >95% on supported devices |
| Session stability | <1 crash per 10 hours of riding |
| Alpha user retention | >40% ride again within 7 days of first ride |