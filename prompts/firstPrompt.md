# VeloWorld — Agentic Build Prompt

## Context

You are an expert software engineer and technical architect. You are building **VeloWorld**, a next-generation indoor cycling simulator. VeloWorld converts real-world GPS route files into physics-accurate, procedurally-generated 3D cycling simulations. Users upload a GPX route, the platform reconstructs the terrain from LiDAR elevation data, generates a 3D environment, and delivers a rideable simulation with accurate gradient resistance communicated to a smart trainer in real time.

The full product specification is in the `/veloworld/docs/` directory. Read all six documents before beginning any work:

- `veloworld_concept.md` — Product vision, modes, and user segments
- `veloworld_architecture.md` — System architecture, components, and infrastructure
- `veloworld_data_pipeline.md` — The route processing pipeline (GPX → rideable simulation)
- `veloworld_physics_model_specifications.md` — The complete cycling physics model
- `veloworld_mvp.md` — The MVP feature set, timeline, and success metrics
- `veloworld_technical_deep_dive.md` — Detailed technical implementation, APIs, code patterns, schemas

Read these documents thoroughly before writing any code. The answers to most architecture questions are in these documents.

---

## Your Task

Build the VeloWorld MVP as defined in `veloworld_mvp.md`. The MVP must be functional, tested, and deployable.

Work through the deliverables in order. Complete each one fully before moving to the next. Do not skip steps or leave stubs — implement each component to production quality.

---

## Deliverable 1: Project Structure and Infrastructure

Set up the full project directory structure and development infrastructure.

**Repository layout:**

```
veloworld/
├── docs/                    ← specification documents (already present)
├── client/                  ← Unreal Engine 5 project
│   ├── Source/
│   │   ├── VeloWorld/
│   │   │   ├── Physics/     ← Physics engine C++ module
│   │   │   ├── Trainer/     ← Smart trainer interface C++
│   │   │   ├── Route/       ← Route player and spline management
│   │   │   ├── HUD/         ← Heads-up display
│   │   │   └── Multiplayer/ ← Multiplayer sync client
│   └── Content/
├── pipeline/                ← Route processing pipeline (Python)
│   ├── stages/
│   │   ├── ingestion.py
│   │   ├── map_matching.py
│   │   ├── terrain.py
│   │   ├── road_mesh.py
│   │   ├── environment.py
│   │   └── packaging.py
│   ├── workers/
│   ├── tests/
│   └── requirements.txt
├── backend/                 ← API backend (Go)
│   ├── cmd/
│   │   └── api/
│   ├── internal/
│   │   ├── auth/
│   │   ├── routes/
│   │   ├── rides/
│   │   └── marketplace/
│   ├── db/
│   │   └── migrations/
│   └── go.mod
├── infra/                   ← Infrastructure as code
│   ├── docker-compose.yml
│   ├── Dockerfile.pipeline
│   ├── Dockerfile.backend
│   └── terraform/           ← (stub for Phase 2)
└── README.md
```

**Actions:**
1. Create the full directory structure
2. Write `docker-compose.yml` that starts: PostgreSQL, Redis, pipeline worker, and API backend
3. Write `README.md` covering: project overview, local development setup, running the stack, running tests
4. Create a `Makefile` with targets: `make dev` (start all services), `make test` (run all tests), `make migrate` (run DB migrations)

---

## Deliverable 2: Backend API

Build the Go backend API. This covers user accounts, route management, ride history, and the route processing job system.

**Requirements:**

Implement REST endpoints:

```
POST   /auth/register          — Email + password registration
POST   /auth/login             — Returns JWT
GET    /auth/me                — Current user profile

POST   /routes                 — Upload a route (GPX file, multipart form)
GET    /routes                 — List current user's routes
GET    /routes/{id}            — Get route detail + processing status
DELETE /routes/{id}            — Delete a route
GET    /routes/public          — Browse public community routes
POST   /routes/{id}/publish    — Make a route public

GET    /rides                  — Current user's ride history
POST   /rides                  — Create a ride record (called by client at session end)
GET    /rides/{id}             — Get ride detail

GET    /routes/{id}/package    — Get the streaming package definition for a route (after processing complete)
```

**Database:**
- Write all migrations in `backend/db/migrations/` using numbered SQL files (001_create_users.sql, etc.)
- Implement the schema from `veloworld_technical_deep_dive.md` Section 7 fully, including all tables and indexes

**Route upload and job queue:**
- When `POST /routes` is called, save the GPX file to S3 and insert a job record
- The job record should be visible to the pipeline workers via a SQS queue (or for local dev, a PostgreSQL-based queue using LISTEN/NOTIFY)
- The API should poll/subscribe to job status and expose it via `GET /routes/{id}`

**Authentication:**
- JWT-based, 24-hour expiry
- Middleware that validates JWT on all protected routes
- Google OAuth integration (POST /auth/google — accepts Google ID token, creates or fetches user)

**Testing:**
- Write integration tests for all endpoints using a test PostgreSQL database
- Tests should cover: happy path, missing auth, invalid input, not-found errors
- Aim for >80% line coverage on handler code

---

## Deliverable 3: Route Processing Pipeline

Build the Python-based route processing pipeline. This is the core technical innovation of the product. Implement all six stages.

Read `veloworld_data_pipeline.md` in full before starting. Every design decision for this pipeline is documented there.

**Stage 1 — Ingestion (`pipeline/stages/ingestion.py`):**
- Parse GPX files using a custom XML parser (do not use a GPX library that abstracts away the raw data — implement your own)
- Extract: coordinate array, timestamps, raw elevation (if present), source device metadata
- Validate: minimum 100 points, minimum 500m distance, coordinate plausibility check (no jumps >500m between consecutive points)
- Output: normalised route JSON matching the schema in the data pipeline document
- Handle malformed files gracefully with descriptive error messages

**Stage 2 — Map Matching (`pipeline/stages/map_matching.py`):**
- Submit GPS points to Valhalla (self-hosted in the Docker stack) using the `/trace_attributes` API
- Process in batches of 100 points with overlap at boundaries
- Extract per-point: corrected coordinates, road_class, surface, road_width_estimate
- Handle Valhalla failures with exponential backoff retry
- Fall back to raw GPS coordinates if map matching fails (log a warning, do not fail the job)
- Output: matched route JSON with per-point attribute table

**Stage 3 — Terrain Reconstruction (`pipeline/stages/terrain.py`):**
- Select data source based on bounding box: USGS 3DEP for USA, Copernicus GLO-30 for Europe, SRTM 30m as global fallback
- Implement a tile cache: check S3 cache before fetching, store fetched tiles in S3 cache
- Download and mosaic tiles covering the route bounding box + 500m buffer
- Reproject to local UTM zone using GDAL
- Interpolate to 2m resolution using bicubic interpolation
- Compute per-point elevation for the route by sampling the height map
- Output: terrain height map (GeoTIFF in S3), route elevation profile JSON

**Stage 4 — Road Mesh Generation (`pipeline/stages/road_mesh.py`):**
- Fit a cubic spline through the map-matched coordinates
- Sample the spline at 0.5m intervals
- Project each spline point onto the terrain height map to get the road surface height
- Extrude road width perpendicular to the travel direction (use road_class to determine width)
- Compute banking angle at corners (use corner_radius estimate from map matching output)
- Build the triangle mesh
- Compute per-segment physics attributes: gradient_percent, corner_radius_m, banking_deg, surface_type, elevation_m
- Export road mesh as GLTF (.glb)
- Export physics attribute table as JSON (1m resolution)

**Stage 5 — Environment Generation (`pipeline/stages/environment.py`):**
- Fetch OSM data for the route bounding box using the Overpass API (buildings, land use, natural features, waterways, POIs)
- Assign biomes to terrain cells based on elevation, land use, and geographic region
- Place vegetation using Poisson disk sampling within appropriate polygons
- Build the scene manifest JSON (asset placements, terrain tile references, sky preset)
- For MVP: implement alpine, deciduous forest, and lowland agricultural biomes only
- Do not generate building meshes yet (stub this — log that buildings are deferred)

**Stage 6 — Packaging (`pipeline/stages/packaging.py`):**
- Resolve asset IDs in the scene manifest to S3 paths
- Divide the route into 500m streaming chunks
- For each chunk: reference the terrain tile, road section, and asset list
- Generate the streaming package definition JSON
- Upload all outputs to S3
- Update the route's processing status to "ready" in the database
- Notify the API (via database update or message queue) that the route is complete

**Pipeline runner (`pipeline/workers/runner.py`):**
- Poll the job queue for pending jobs
- Run the full pipeline for each job, stage by stage
- Log stage start, completion, and duration
- On stage failure: update the job's stage status to "failed", store the error message, do NOT proceed to the next stage
- Implement retry logic: up to 3 retries on transient failures (network errors, API timeouts), no retry on data errors (invalid file, unsupported format)

**Testing:**
- Include a suite of test GPX files covering: normal road ride, mountain switchbacks, flat criterium circuit, route with GPS gaps, very short route (should be rejected), route with bad coordinates (should be rejected)
- Write unit tests for each stage using these test files
- Write an end-to-end test that runs the full pipeline on a real GPX file and validates the output
- Mock external APIs (Valhalla, USGS, Overpass) with recorded responses for deterministic testing

---

## Deliverable 4: Physics Simulation Engine (C++)

Build the physics simulation engine as a C++ module. This module will be integrated into the Unreal Engine 5 client but must be buildable and testable as a standalone library.

Read `veloworld_physics_model_specifications.md` in full before starting. All formulas, constants, and parameter tables are defined there.

**Module structure:**

```
client/Source/VeloWorld/Physics/
├── PhysicsEngine.h / .cpp        — Main simulation class
├── ForceModel.h / .cpp           — All force computation
├── RouteProfile.h / .cpp         — Route data access
├── RiderConfig.h                 — Rider + bike configuration struct
├── SimulationState.h             — Rider state struct
├── TrainerInterface.h            — Abstract trainer interface
├── SimulatedTrainer.h / .cpp     — Mock trainer for testing
└── PhysicsTests.cpp              — Unit tests (Google Test)
```

**ForceModel — implement exactly:**
- `ComputeGravityForce(float gradientDeg, float systemMassKg)` — F = m × g × sin(θ)
- `ComputeRollingResistance(float crr, float systemMassKg, float gradientDeg)` — F = Crr × m × g × cos(θ)
- `ComputeAerodynamicDrag(float cdA, float velocityMs, float airDensity, float windComponentMs)` — F = 0.5 × ρ × CdA × v_air²
- `ComputeAirDensity(float altitudeM, float temperatureC)` — density model from spec
- `ComputeTotalForce(const RouteAttributes& route, const RiderConfig& config, float velocityMs, float windComponentMs)` — sum of all forces
- `SolveVelocity(float powerW, float totalForceN, float systemMassKg, float prevVelocityMs, float dtS)` — semi-implicit Euler integration

**RouteProfile:**
- Load route physics attribute table from JSON
- `GetAttributesAtPosition(float positionM)` — returns `RouteAttributes` by linear interpolation between 1m samples
- `RouteAttributes` struct: gradient_percent, corner_radius_m, banking_deg, surface_type, elevation_m

**PhysicsEngine — 60Hz simulation loop:**
- `Initialise(routeJson, riderConfig, trainerInterface)`
- `Tick(float deltaTimeS)` — one simulation step
- Implements the full loop from the spec: read power → compute forces → solve velocity → advance position → send resistance
- `GetState()` returns current `SimulationState` (position, velocity, power, gradient, etc.)

**TrainerInterface — implement mock for testing:**
- `SimulatedTrainer` generates synthetic power output (constant wattage or configurable ramp)
- Records all resistance commands sent to it (for test validation)

**Unit tests (Google Test):**
- Test each force formula against hand-calculated reference values
- Test velocity solver: at constant power on flat road, verify steady-state velocity converges to correct value
- Test gradient simulation: at 5% gradient with 200W, verify trainer receives the correct equivalent gradient command
- Test surface type switching: verify Crr changes when surface type changes at a known position
- Test corner braking: verify rider is decelerated before a corner with radius below the traction limit

**Build system:**
- Provide a standalone `CMakeLists.txt` so the physics module can be built and tested independently of Unreal Engine
- `cmake --build && ctest` should run all tests and pass

---

## Deliverable 5: Smart Trainer Integration (C++)

Build the smart trainer interface layer. This must handle BLE FTMS and ANT+ FE-C communication.

**BLE FTMS Driver (`client/Source/VeloWorld/Trainer/BLEFTMSDriver`):**
- Scan for nearby BLE devices advertising the FTMS service (UUID 0x1826)
- Connect to the selected device
- Subscribe to Indoor Bike Data characteristic (0x2AD2) notifications
- Parse the Indoor Bike Data bitfield to extract: instantaneous power (W), cadence (RPM), speed (km/h)
- Send Set Indoor Bike Simulation Parameters command (opcode 0x11) to Fitness Machine Control Point (0x2AD9)
- Handle BLE connection drops: attempt reconnect up to 5 times with 2s delay between attempts, emit `OnTrainerDisconnected` event after 5 failures

**ANT+ FE-C Driver (`client/Source/VeloWorld/Trainer/ANTPlusFECDriver`):**
- Open the ANT+ USB dongle (OpenANT library)
- Search for FE-C device on ANT+ channel
- Read Page 25 (Trainer Data) for power, cadence, accumulated power
- Send Page 51 (Track Resistance) to set gradient and Crr
- Send Page 49 (Target Power) for ERG mode

**Hardware Abstraction Layer:**
- Implement the `TrainerInterface` abstract class defined in Deliverable 4
- Both drivers implement this interface
- `TrainerManager` class: detects available connection methods, instantiates the correct driver, exposes a single `TrainerInterface*` to the physics engine
- `TrainerCalibration` class: stores per-device resistance curve correction factors; loaded from a bundled JSON database

**Platform considerations:**
- BLE implementation must be cross-platform: Windows (WinRT BLE API), macOS (CoreBluetooth via Objective-C++ bridge), Linux (BlueZ D-Bus API)
- ANT+ USB dongle: libusb-based, works cross-platform
- Provide compile-time flags to enable/disable each platform implementation

---

## Deliverable 6: Unreal Engine 5 Client — Core

Build the core Unreal Engine 5 client application covering: scene loading, route player, physics integration, and basic HUD.

**Project setup:**
- Create a new UE5 C++ project named `VeloWorld`
- Configure the build system to include the Physics module (Deliverable 4) and Trainer module (Deliverable 5) as UE plugin modules
- Set up the primary game mode: `AVeloWorldGameMode`

**Route Player (`client/Source/VeloWorld/Route/RoutePlayer`):**
- Load the route streaming package definition JSON
- Manages the rider's progress along the route spline
- Drives the main camera (configurable: first-person / third-person chase / side view)
- Communicates position to the physics engine at each tick
- Triggers asset streaming: requests the next chunk from the Asset Streaming Manager when the rider is within 1.5km of a chunk boundary

**Asset Streaming Manager:**
- Downloads terrain tile, road section, and asset list for the upcoming chunk from S3 (via CloudFront)
- Maintains a prefetch buffer of 4 chunks ahead of the rider
- Unloads chunks more than 3km behind the rider to manage memory
- Handles download failures: retry 3 times, then continue without the chunk (log error)

**Scene Construction:**
- Load terrain tiles and road mesh sections dynamically as they are streamed in
- Place vegetation assets according to the scene manifest placement data
- Use Unreal's instanced static mesh component for all repeated assets (trees, signs) — critical for render performance
- Apply appropriate materials to road sections based on surface type

**HUD (`client/Source/VeloWorld/HUD/`):**

Implement the following HUD elements using Unreal's UMG widget system:

```
┌─────────────────────────────────────────────────┐
│  [Power: 224W]    [Speed: 34.2 km/h]   [00:42:15]│
│                                                 │
│  [Gradient: +5.2%]              [HR: 158 bpm]  │
│                                                 │
│  [Distance: 24.8 km / 68.3 km remaining]        │
│                                                 │
│  [Elevation profile strip with position marker] │
│                                                 │
│  [Mini map - top right corner]                  │
└─────────────────────────────────────────────────┘
```

All values update every second from the `SimulationState`. Elevation profile strip shows the full route with a moving position marker and 5km lookahead highlight.

**Session Flow:**
- Route selection screen (fetches user's route list from API)
- Pre-ride configuration screen: rider weight, bike weight, rider position (for CdA), tyre type
- Trainer pairing screen: scan for BLE/ANT+ devices, select and connect
- Countdown (3-2-1) then simulation starts
- End-of-ride summary screen: total distance, time, avg power, avg speed, elevation gain/loss, power curve chart
- Save ride button (calls `POST /rides` on API)

---

## Deliverable 7: Integration Testing and End-to-End Validation

Write a comprehensive integration test suite that validates the full system from GPX upload to completed ride.

**End-to-end test scenario:**

```
1. Register a new user via API
2. Upload a test GPX file (include a 50km route with 800m elevation gain)
3. Poll GET /routes/{id} until processing status = "ready" (timeout: 10 minutes)
4. Validate the route package:
   - Route has a physics attribute table with >40,000 entries (1 per meter at 40km)
   - Gradient values match known reference values at 5 known points on the route
   - Road mesh file exists and is valid GLTF
   - Scene manifest references valid asset IDs
5. Initialise the physics engine with the route package and a simulated trainer
6. Run a simulated ride: 10 minutes at 200W constant power
   - Verify rider advances along the route at a physically plausible speed
   - Verify trainer resistance changes correctly at 3 known gradient transitions on the route
   - Verify the simulation completes 10 minutes without errors
7. Save the ride record via API
8. Verify the ride appears in GET /rides for the user
```

**Physics validation tests:**
- At 0% gradient, 200W, 75kg rider, standard CdA=0.32: verify steady-state speed converges to 38–42 km/h (known reference range)
- At 8% gradient, 250W, 75kg rider: verify speed converges to 12–16 km/h
- At -5% gradient (downhill), 0W: verify rider accelerates to a reasonable speed and doesn't exceed 70 km/h (terminal velocity check)
- Drafting test: add a second rider 0.5m ahead; verify trailing rider's effective CdA drops by approximately 25%

**Trainer protocol tests:**
- Connect to `SimulatedTrainer`, run 5 minutes of simulation, verify the trainer received the correct number of resistance commands (300 at 1Hz) and that command values fall within valid ranges for each gradient encountered

---

## Deliverable 8: Documentation

Write developer documentation covering the complete system.

**`docs/developer/setup.md`:**
- Prerequisites: OS requirements, installed tools, hardware
- Full local development setup from scratch (clone → `make dev` → working system)
- Running the test suite
- Connecting a real smart trainer for local testing

**`docs/developer/pipeline.md`:**
- How to run a single pipeline stage manually for debugging
- How to add a new LiDAR data source
- How to add a new biome type and its asset palette
- How to inspect and debug processed route outputs

**`docs/developer/physics.md`:**
- How to modify force model parameters
- How to add a new surface type
- How to add a new trainer device
- How to run physics unit tests

**`docs/developer/api.md`:**
- All API endpoints with request/response examples
- Authentication flow
- Error codes and their meanings
- Rate limits

---

## Technical Constraints and Standards

**All code must:**
- Be production quality — no placeholders, no `TODO` stubs, no `pass` statements in critical paths
- Have meaningful error handling — every error that can occur at runtime must be caught, logged with context, and handled gracefully
- Have unit tests — every function with logic must have at least one test
- Follow language-specific style: Go (`gofmt` + `golangci-lint`), Python (`black` + `mypy`), C++ (ClangFormat with LLVM style)
- Include structured logging at key events: job start/end, stage transitions, API requests, trainer connection events

**Performance requirements:**
- Pipeline: process a 50km GPX route in under 5 minutes on a single worker
- API: all endpoints respond in under 200ms at P95 (excluding file upload)
- Physics engine: maintain 60 Hz simulation loop with <1ms per tick
- Client: maintain 60 FPS at 1080p on an RTX 3070-class GPU

**Security requirements:**
- All API endpoints that access user data must validate the JWT and compare the resource owner to the authenticated user
- S3 objects are never publicly accessible — all client downloads go through presigned URLs (1-hour expiry)
- User passwords are hashed with bcrypt (cost factor 12)
- SQL queries use parameterised statements throughout — no string concatenation in queries

---

## Working Approach

1. **Read all six specification documents first.** Do not begin coding until you have read every document. The documents contain specific APIs, data schemas, formula implementations, and architectural decisions that you must follow.

2. **Work sequentially through deliverables.** Each deliverable builds on the previous. Do not skip ahead.

3. **Build, then test.** For each deliverable, build the implementation first, then write and run tests. Do not move to the next deliverable if tests are failing.

4. **Ask before inventing.** If a specification is unclear or seems incomplete, re-read the relevant document before making assumptions. If genuinely ambiguous, state your assumption explicitly in a comment before implementing.

5. **Favour correctness over cleverness.** The physics model must be mathematically correct. If in doubt, implement the formula exactly as specified rather than optimising prematurely.

6. **Real integrations, not mocks, in production code.** The pipeline must connect to real Valhalla, real USGS/Copernicus APIs, and real S3. Mocks are for the test suite only. Do not build a system that hardcodes responses.

Begin with Deliverable 1. When it is complete, confirm completion and move to Deliverable 2. Proceed through all eight deliverables in order.