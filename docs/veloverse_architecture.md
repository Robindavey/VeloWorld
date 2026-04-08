# VeloVerse — System Architecture

## Overview

VeloVerse is composed of four major technical systems that work in concert to deliver real-time physics-accurate cycling simulation:

1. **Route Processing Pipeline** — converts raw GPS data into rideable 3D environments
2. **Physics Simulation Engine** — computes cycling forces and communicates resistance to smart trainers
3. **Rendering Engine** — renders the 3D environment in real time on the client
4. **Cloud Services Platform** — handles backend logic, data storage, user accounts, and route delivery

These systems are distributed across client (user device) and cloud (server-side processing) layers, with clear responsibility boundaries.

---

## High-Level Architecture Diagram

```
User Device (Game Client)
├── Rendering Engine (Unreal Engine)
├── Physics Simulation Engine (C++ / Rust)
├── Smart Trainer Interface (BLE / ANT+)
├── Input & HUD Layer
└── Multiplayer Sync Client
        |
        v
API Gateway (HTTPS / WebSocket / gRPC)
        |
        v
Backend Services
├── Auth Service
├── Route Service
├── Ride Recording Service
├── Marketplace Service
└── Multiplayer Server
        |
        v
Data Layer
├── PostgreSQL (relational data)
├── Redis (caching, sessions, real-time state)
├── AWS S3 (route files, terrain tiles, assets)
└── Route Processing Workers (async pipeline)
```

---

## 1. Route Processing Pipeline

### Purpose
The pipeline converts a user-uploaded GPS route file into a fully rideable 3D simulation. It runs server-side as an asynchronous job, triggered on route upload.

### Input Formats
- GPX (primary)
- FIT (Garmin/ANT+ device format)
- TCX (Training Center XML)

### Pipeline Stages

**Stage 1 — GPX Ingestion**
Parse the raw file. Extract: coordinate array, timestamps, raw elevation data (if present), speed data (if present). Validate for minimum point density and coordinate plausibility. Output: normalised route JSON.

**Stage 2 — Map Matching**
Align the GPS track to the actual road network. GPS tracks drift by 5–20m. Map matching corrects this and adds road metadata. Output: corrected road path, road classification, surface type, road width, speed limits, corner geometry.

APIs:
- OpenStreetMap Overpass API (free, open)
- Mapbox Map Matching API (commercial, higher quality)
- Valhalla (self-hostable open-source option)

**Stage 3 — Terrain Reconstruction**
Query LiDAR elevation datasets to build a true terrain height map for the region around the route. This is far more accurate than GPS elevation data which carries 3–10m error.

LiDAR Sources:
- USGS 3DEP LiDAR (USA — 1m resolution available in many regions)
- Copernicus DEM (Europe — 25m GLO-30, 10m in dense areas)
- LINZ (New Zealand)
- National mapping agency datasets (UK Ordnance Survey, IGN France, etc.)

Libraries: GDAL, PDAL, rasterio

Output: terrain height map grid, terrain mesh.

**Stage 4 — Road Mesh Generation**
Build the actual rideable road surface along the route.

Steps:
- Generate cubic spline from corrected GPS path
- Project spline onto terrain mesh
- Extrude road width (configurable per road classification)
- Apply corner banking based on curvature radius
- Smooth elevation transitions (remove GPS noise artefacts)
- Apply surface type material

Output: 3D road mesh with UV mapping for surface textures.

**Stage 5 — Environment Generation**
Populate the world around the road.

Sources:
- OpenStreetMap data (buildings, land use, water, forests, points of interest)
- Procedural generation rules (vegetation density, terrain-type-based biome selection)
- AI-generated asset variation (texture variants, building style matching)
- Optional: street-view imagery for landmark reference and texture seeding

Output: Scene description with asset placement manifest.

**Stage 6 — Asset Pipeline**
Resolve the asset placement manifest to actual 3D assets. Assets are drawn from:
- A curated base library (trees, generic buildings, road furniture)
- Procedurally generated variants
- Region-specific asset packs (alpine, Mediterranean, urban, etc.)

Terrain tiles and assets are packaged and uploaded to S3 for delivery to the client.

### Processing Time Targets
- Simple route (<50km, low terrain complexity): under 3 minutes
- Medium route (50–200km): under 10 minutes
- Complex route (high terrain variation, dense urban): under 20 minutes

Optimisations:
- Pre-cached terrain tile grids for popular regions
- Parallelised processing workers (AWS Lambda or EC2 auto-scaling)
- Priority queue for routes in active use by paying users

---

## 2. Physics Simulation Engine

### Purpose
Compute cycling forces in real time and communicate target resistance to the smart trainer. Runs locally on the client at 60 Hz.

### Language and Libraries
- Primary implementation: **C++** for performance-critical simulation loop
- Rust considered for memory safety in networked subsystems
- Physics libraries: **Bullet Physics** or **NVIDIA PhysX** for collision and rigid body handling where needed
- Custom force model for cycling-specific dynamics (not delegated to general physics engine)

### Forces Modelled

The net resistance force at any point is:

```
F_total = F_gravity + F_rolling + F_aerodynamic + F_braking + F_corner
```

Where:
- **F_gravity** = m × g × sin(θ) — slope-dependent, dominant on climbs
- **F_rolling** = Crr × m × g × cos(θ) — tyre/surface-dependent
- **F_aerodynamic** = 0.5 × ρ × CdA × v² — velocity-squared, dominant at speed
- **F_braking** — applied when rider exceeds safe corner entry speed
- **F_corner** — centripetal force requirement at corners

The power-to-speed relationship:

```
P_rider = F_total × v
```

Solved per frame to yield target velocity and corresponding trainer load.

### Drafting Model
Aerodynamic wake zones are computed behind each rider in multiplayer. The trailing rider's effective CdA is reduced based on proximity, lateral offset, and number of riders in the group. Second rider reduction: ~25–30%. Large peloton: up to 40%.

### Trainer Communication
The physics engine outputs a resistance setpoint each frame. This is sent to the smart trainer via:
- **Bluetooth FTMS** (Fitness Machine Service) — the modern standard
- **ANT+ FE-C** — legacy and Garmin-ecosystem trainers

The trainer reads power output from the rider and returns it to the physics engine, closing the control loop.

### Simulation Loop

```
[Read rider power from trainer]
    ↓
[Calculate F_total from route data at current position]
    ↓
[Solve for velocity: v = P / F_total]
    ↓
[Advance rider position along route spline]
    ↓
[Send new resistance target to trainer]
    ↓
[Update HUD and renderer]
    ↓
[Sync position to multiplayer server (if applicable)]
    ↓
[Repeat at 60 Hz]
```

---

## 3. Rendering Engine

### Recommended Engine: Unreal Engine 5

**Rationale:**
- Nanite virtualised geometry — handles high-density terrain meshes efficiently
- Lumen global illumination — realistic outdoor lighting without manual bake
- Strong C++ integration for physics engine coupling
- Native VR/AR support (required for future smart glasses and VR mode)
- Large developer ecosystem
- MetaHuman or custom character rigs for avatar rendering

### Alternative Considered: Unity
Viable but Unreal offers superior rendering quality for outdoor environments. Unity's HDRP can match quality but with higher implementation effort.

### Custom Vulkan Renderer
Not recommended for MVP. May be considered for a dedicated hardware appliance version in the distant future.

### Rendering Responsibilities
- Real-time 3D environment rendering from scene description
- Rider avatar rendering and animation
- HUD overlay rendering (speed, power, gradient, map)
- Weather visual effects (rain, fog, wind indicators)
- Spectator/replay camera modes
- VR stereo rendering (future)

---

## 4. Backend Services Platform

### Language and Framework
- Primary language: **Go** — high concurrency, low latency, strong for API services
- Supporting services in **Python** where data processing is required
- API: gRPC internally, REST + JSON externally (via gRPC gateway)
- WebSockets for real-time multiplayer and live ride sync

### Services Breakdown

| Service | Responsibility |
|---|---|
| Auth Service | Registration, login, JWT issuance, OAuth2 (Google, Apple) |
| Route Service | Route upload, pipeline triggering, route retrieval, metadata |
| Ride Service | Live ride telemetry recording, history, personal bests |
| Marketplace Service | Route listing, purchasing, licensing, ratings |
| Multiplayer Service | Room creation, rider sync, event management |
| Notification Service | Push notifications, email (via SendGrid or SES) |

### Database Layer

**PostgreSQL** — primary relational store:
- User accounts and profiles
- Route metadata and ownership
- Ride history and telemetry
- Marketplace transactions

**Redis** — caching and real-time state:
- Session tokens
- Leaderboard data (sorted sets)
- Live ride room state
- API response caching for popular routes

**AWS S3** — object storage:
- Route files (GPX originals, processed terrain tiles)
- 3D asset libraries
- Ride replay files
- Profile images

### Cloud Infrastructure
- **Primary cloud: AWS** (EC2, S3, RDS, ElastiCache, Lambda, CloudFront)
- **Alternative: Google Cloud Platform** (strong geospatial tooling — BigQuery GIS, Maps Platform — may be preferred for route processing components)
- CDN for asset delivery: CloudFront (AWS) or Cloud CDN (GCP)
- Container orchestration: Kubernetes (EKS or GKE) for service management

---

## 5. Client Distribution

| Platform | Method |
|---|---|
| Windows PC | Steam, standalone installer, Epic Games Store |
| macOS | Standalone installer (Metal rendering) |
| Linux | Steam (Proton or native build) |
| iOS (companion) | App Store |
| Android (companion) | Google Play Store |

Mobile companion app features:
- Route browsing and upload
- Ride scheduling and calendar
- Social feed and community
- Ride history and analytics
- Bluetooth trainer pairing assistant

---

## 6. Development Hardware Recommendations

### Development Workstations
- CPU: 12+ core (AMD Ryzen 9 or Intel Core i9)
- RAM: 64 GB (32 GB minimum)
- GPU: NVIDIA RTX 4080 or equivalent (required for Unreal Engine 5 development)
- Storage: 2 TB NVMe SSD (Unreal projects are large)
- Display: High-resolution, colour-accurate

### Testing Hardware
- Smart trainers: Wahoo KICKR, Tacx NEO, Elite Direto (cover the major ANT+/BLE variants)
- Power meters: Garmin Rally, Stages (for accuracy validation)
- Heart rate monitors: Garmin, Polar, Wahoo TICKR
- Cadence and speed sensors: ANT+ and BLE variants
- GPS devices: Garmin Edge, Wahoo ELEMNT (for GPX file format testing)

---

## 7. Key Engineering Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LiDAR data gaps in some regions | Poor terrain quality in affected areas | Fall back to SRTM 30m DEM; flag routes as "reduced quality"; expand dataset coverage over time |
| Route processing latency | Poor user experience on upload | Pre-cache popular regions; async processing with progress indicator; pre-process popular race routes ahead of time |
| Smart trainer hardware inconsistency | Inaccurate resistance delivery | Hardware abstraction layer; per-device calibration profiles; user-reported issue feedback loop |
| Multiplayer sync at scale | Desync, latency issues in large groups | Client-authoritative physics with server reconciliation; limit room size in early versions |
| Unreal Engine build size | Large client download | Asset streaming from CDN; initial install loads essential assets only |