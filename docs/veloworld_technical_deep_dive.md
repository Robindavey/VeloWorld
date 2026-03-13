# VeloWorld — Technical Deep Dive

## Purpose

This document provides a detailed technical reference for the VeloWorld system. It is intended for engineers working on the platform and covers all major technical decisions, design patterns, interfaces, and engineering challenges in depth.

It covers:
- System overview and component boundaries
- Client application architecture
- Route generation pipeline (detailed)
- Physics simulation engine (detailed)
- Smart trainer integration
- Multiplayer infrastructure
- Backend services
- Data storage and infrastructure
- Distribution strategy
- Development hardware requirements
- Key engineering challenges and mitigations

---

## 1. System Overview

VeloWorld is composed of four primary technical systems:

| System | Where it runs | Primary responsibility |
|---|---|---|
| Route Generation Pipeline | Cloud (async workers) | Converts GPS data into 3D simulation environments |
| Physics Simulation Engine | Client device | Computes cycling forces; communicates with smart trainer |
| Rendering Engine | Client device | Renders the 3D environment in real time |
| Cloud Services Platform | Cloud (servers) | Handles accounts, storage, routes, multiplayer |

### System Boundary Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     USER DEVICE (CLIENT)                     │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │   Rendering  │   │   Physics    │   │ Trainer        │  │
│  │   Engine     │◄──│   Engine     │──►│ Interface      │  │
│  │  (Unreal 5)  │   │   (C++)      │   │ (BLE / ANT+)   │  │
│  └──────┬───────┘   └──────┬───────┘   └────────┬───────┘  │
│         │                  │                     │           │
│         └──────────────────┼─────────────────────┘           │
│                            │                                 │
│                      ┌─────▼──────┐                          │
│                      │ Game Loop  │                          │
│                      │  60 Hz     │                          │
│                      └─────┬──────┘                          │
│                            │                                 │
└────────────────────────────┼────────────────────────────────┘
                             │ HTTPS / WebSocket / gRPC
                             │
┌────────────────────────────▼────────────────────────────────┐
│                       API GATEWAY                            │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                    BACKEND SERVICES                          │
│                                                             │
│  Auth    Route    Ride     Market    Multi     Notify       │
│  Svc     Svc      Svc      place     player    Svc          │
│                                                             │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                      DATA LAYER                              │
│                                                             │
│  PostgreSQL    Redis       AWS S3      Route Workers        │
│  (relational)  (cache)     (objects)   (async pipeline)     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Client Application Architecture

### Rendering Engine: Unreal Engine 5

Unreal Engine 5 is selected as the rendering and application framework for the following reasons:

**Nanite Virtualised Geometry**: Enables rendering of extremely high-polygon terrain meshes (generated from 1m LiDAR data) without manual LOD management. Critical for VeloWorld's terrain quality requirements.

**Lumen Global Illumination**: Real-time global illumination and reflections without baked lighting. This is essential for outdoor environment realism — skylight, shadows, and time-of-day changes all work automatically.

**Strong C++ Integration**: The physics engine and trainer interface are pure C++ components. Unreal's C++ API is first-class and the engine is designed around it.

**Native VR/XR Support**: Future VR mode and smart glasses integration will require VR rendering. Unreal supports OpenXR natively.

**Chaos Physics Integration**: Unreal's Chaos physics system is available for collision detection (bike/road interaction) and any future rigid body simulation. Custom cycling physics are implemented independently but can leverage Chaos for collision queries.

### Client Application Layers

```
┌─────────────────────────────────────────────────┐
│              Game Client Application             │
│                                                 │
│  ┌────────────────┐  ┌───────────────────────┐  │
│  │   UI / Menus   │  │    HUD / Overlay       │  │
│  │   (UMG/Slate)  │  │    (C++ / Blueprints)  │  │
│  └────────────────┘  └───────────────────────┘  │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │           Route Player                  │    │
│  │  (manages rider position on spline,     │    │
│  │   scene streaming, camera control)      │    │
│  └────────────────┬────────────────────────┘    │
│                   │                             │
│  ┌────────────────▼────────────────────────┐    │
│  │         Physics Simulation Engine        │    │
│  │  (C++ module, 60Hz loop)                │    │
│  └────────────────┬────────────────────────┘    │
│                   │                             │
│  ┌────────────────▼────────────────────────┐    │
│  │       Smart Trainer Interface            │    │
│  │  (Hardware Abstraction Layer)           │    │
│  │  ┌──────────┐  ┌──────────────────────┐ │    │
│  │  │BLE FTMS  │  │  ANT+ FE-C Driver    │ │    │
│  │  │ Driver   │  │                      │ │    │
│  │  └──────────┘  └──────────────────────┘ │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │       Multiplayer Sync Client            │    │
│  │  (WebSocket / gRPC streaming)           │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │        Asset Streaming Manager           │    │
│  │  (CDN prefetch, tile cache)             │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### Game Loop Structure

The main game loop runs at 60 Hz. Each tick:

```
Tick (16.7ms budget):

[1] Asset Streaming Manager — check prefetch buffer, request next tiles if needed
[2] Trainer Interface — poll for new power/cadence readings (BLE / ANT+)
[3] Physics Engine — run simulation step
    [3a] Read power from trainer
    [3b] Compute forces at current position
    [3c] Solve for velocity
    [3d] Advance position
    [3e] Output trainer resistance command
[4] Trainer Interface — send resistance command
[5] Multiplayer Sync — send position update (if active)
[6] Multiplayer Sync — receive other riders' positions
[7] Route Player — update rider position on spline, camera
[8] Renderer — render frame
[9] HUD — update display values
```

Budget allocation (approximate at 60 FPS):
- Physics + trainer: 1–2ms
- Multiplayer: 1ms
- Rendering: 10–12ms
- Remaining: 2–4ms buffer

---

## 3. Route Generation Pipeline

### Overview

The pipeline is the core technical innovation of VeloWorld. It runs server-side as an asynchronous job system. Each pipeline run processes one route and produces a packaged simulation environment.

The pipeline is designed to be:
- **Idempotent**: re-running with the same inputs produces the same output
- **Observable**: each stage logs progress, errors, and metrics
- **Resumable**: if a stage fails, it can be retried from that stage without re-running earlier stages
- **Parallelisable**: stages with no dependencies can run concurrently

### Stage 1: GPX Ingestion

**Input**: Raw uploaded file (GPX / FIT / TCX)

**Processing:**

```python
def ingest_route(file_path: str, format: str) -> NormalisedRoute:
    if format == "gpx":
        points = parse_gpx(file_path)
    elif format == "fit":
        points = parse_fit(file_path)
    elif format == "tcx":
        points = parse_tcx(file_path)
    
    validate_route(points)  # raises on failure
    
    return NormalisedRoute(
        points=points,
        bounding_box=compute_bbox(points),
        total_distance=compute_distance(points),
        raw_elevation_available=any(p.elevation for p in points)
    )
```

**Libraries:**
- GPX: custom XML parser (GPX is simple enough to parse directly)
- FIT: Garmin FIT SDK Python bindings (`fitparse`)
- TCX: custom XML parser
- Coordinate operations: `pyproj`, `shapely`

**Output**: `NormalisedRoute` JSON stored to S3, pipeline advances to Stage 2.

---

### Stage 2: Map Matching

**Input**: `NormalisedRoute` JSON

**Process:**

GPS points are submitted to the map matching service in batches of 100 points. Valhalla returns a corrected path and road attributes per matched segment.

**Valhalla API call example:**

```json
POST /trace_attributes
{
  "shape": [
    { "lat": 45.832, "lon": 6.865 },
    ...
  ],
  "costing": "bicycle",
  "shape_match": "map_snap",
  "filters": {
    "attributes": ["edge.road_class", "edge.surface", "edge.length", "node.lat", "node.lon"],
    "action": "include"
  }
}
```

**Response processing:**

The matched path is re-sampled at 1m intervals along the road spline. Road attributes are interpolated per meter. The result is a per-meter attribute table covering the full route length.

**Output**: `MatchedRoute` — corrected path with per-meter attribute table. Stored to S3.

---

### Stage 3: Terrain Reconstruction

**Input**: `MatchedRoute` bounding box

**Process:**

```python
def reconstruct_terrain(bbox: BoundingBox, route_id: str) -> TerrainHeightMap:
    
    # Check tile cache first
    cached = check_tile_cache(bbox)
    if cached:
        return cached
    
    # Determine best available data source
    source = select_lidar_source(bbox)  # USGS, Copernicus, SRTM
    
    # Query and download elevation data
    raw_dem = fetch_dem(source, bbox, buffer_m=500)
    
    # Reproject to local UTM zone
    dem_local = reproject(raw_dem, target_crs=utm_for_bbox(bbox))
    
    # Interpolate to 2m resolution
    dem_fine = interpolate_dem(dem_local, target_resolution=2)
    
    # Cache tiles
    cache_tiles(dem_fine, bbox)
    
    return TerrainHeightMap(data=dem_fine, crs=utm_for_bbox(bbox), resolution=2)
```

**USGS 3DEP API Integration:**

```python
BASE_URL = "https://tnmapi.cr.usgs.gov/api/products"

def fetch_usgs_lidar(bbox: BoundingBox) -> bytes:
    params = {
        "bbox": f"{bbox.west},{bbox.south},{bbox.east},{bbox.north}",
        "prodFormats": "IMG",
        "datasets": "Digital Elevation Model (DEM) 1 meter"
    }
    response = requests.get(BASE_URL, params=params)
    return download_dem_file(response.json())
```

**Copernicus DEM Integration:**

Copernicus GLO-30 tiles are available as static GeoTIFF files on AWS S3 (open data). Tiles are identified by 1-degree bounding boxes. The pipeline downloads the relevant tiles and mosaics them.

**Output**: `TerrainHeightMap` — GeoTIFF stored to S3 with tile cache populated.

---

### Stage 4: Road Mesh Generation

**Input**: `MatchedRoute` + `TerrainHeightMap`

**Process:**

The road centreline spline is parameterised at 0.1m intervals. At each point:

1. Look up terrain height at (lat, lon) from height map
2. Add road surface height offset (0.1m above terrain)
3. Compute road normal vector (for cross-section orientation)
4. Extrude road width perpendicular to travel direction
5. Apply banking rotation at corners

The result is a continuous triangle mesh representing the road surface.

**Mesh generation pseudocode:**

```
vertices = []
triangles = []

for i, point in enumerate(spline_points):
    height = terrain.get_height(point.lat, point.lon) + 0.1
    normal = compute_road_normal(point, spline_points, i)
    width = get_road_width(point.road_type)
    banking = compute_banking(point.corner_radius, point.road_type)
    
    left  = point.position + rotate(normal * (width/2), banking)
    right = point.position - rotate(normal * (width/2), banking)
    
    left.z  = height
    right.z = height
    
    vertices.extend([left, right])
    
    if i > 0:
        triangles.extend(quad(i-1, i))  # connect to previous pair

mesh = TriangleMesh(vertices, triangles)
mesh.apply_uv_mapping(road_length=spline.total_length)
mesh.assign_material(surface_type=point.surface_type)
```

**Output**: Road mesh (`.glb` format) + per-meter physics attribute array. Both stored to S3.

---

### Stage 5: Environment Generation

**Input**: `MatchedRoute`, `TerrainHeightMap`, OSM building/landuse data

**OSM Data Fetching (Overpass API):**

```
[out:json][timeout:120];
(
  way["building"](bbox);
  way["landuse"](bbox);
  way["natural"](bbox);
  relation["natural"](bbox);
);
out geom;
```

**Biome Assignment:**

Each terrain cell is assigned a biome based on elevation, land use classification, and geographic region. Biome determines the vegetation density rules and asset palette.

**Vegetation Placement:**

Vegetation assets are placed within OSM land use polygons using Poisson disk sampling:

```python
def place_vegetation(polygon: Polygon, biome: Biome, min_spacing: float) -> list[AssetPlacement]:
    samples = poisson_disk_sample(polygon, min_spacing)
    placements = []
    for point in samples:
        asset = biome.sample_asset(point)  # weighted random selection
        rotation = random.uniform(0, 360)
        scale = random.gauss(1.0, 0.15)
        placements.append(AssetPlacement(asset, point, rotation, scale))
    return placements
```

**Output**: Scene manifest JSON stored to S3.

---

### Stage 6: Asset Resolution and Packaging

The scene manifest references asset IDs. This stage resolves those IDs to S3 paths and produces a streaming package definition.

The package definition tells the client's Asset Streaming Manager which tile chunks to prefetch as the rider advances along the route:

```json
{
  "route_id": "abc-123",
  "chunks": [
    {
      "start_m": 0,
      "end_m": 500,
      "terrain_tile": "s3://veloworld/routes/abc-123/terrain/tile_0000.glb",
      "road_section": "s3://veloworld/routes/abc-123/road/section_0000.glb",
      "assets": ["s3://veloworld/assets/trees/alpine_01.glb", ...]
    },
    ...
  ]
}
```

Chunk size: 500m. The client prefetches 4 chunks ahead (2km buffer).

---

## 4. Physics Simulation Engine

Refer to the Physics Model Specification document for the complete force model. This section covers the implementation architecture.

### Module Structure

```
physics/
├── PhysicsEngine.h / .cpp     — Main simulation class, game loop integration
├── ForceModel.h / .cpp        — Force computation (gravity, rolling, drag)
├── DraftingModel.h / .cpp     — Aerodynamic wake simulation (multiplayer)
├── WindModel.h / .cpp         — Wind direction/speed effects
├── CornerModel.h / .cpp       — Corner traction and braking
├── RouteProfile.h / .cpp      — Route data access (gradient, surface lookup)
├── TrainerInterface.h         — Abstract trainer interface
├── BLEFTMSDriver.h / .cpp     — Bluetooth FTMS implementation
├── ANTPlusFECDriver.h / .cpp  — ANT+ FE-C implementation
└── SimulationState.h          — Rider state struct (position, velocity, etc.)
```

### PhysicsEngine Interface

```cpp
class PhysicsEngine {
public:
    void Initialise(const RouteProfile& route, const RiderConfig& config);
    void Tick(float DeltaTime);  // Called every game frame
    
    SimulationState GetCurrentState() const;
    void SetMultiplayerRiders(const std::vector<RiderState>& others);
    
private:
    void ReadTrainerData();
    float ComputeTotalForce(float velocity, float gradient, SurfaceType surface);
    float ComputeDraftBenefit(const SimulationState& state);
    float SolveVelocity(float power, float totalForce, float dt);
    void SendTrainerResistance(float forceN);
    void AdvancePosition(float velocity, float dt);
    
    RouteProfile m_route;
    RiderConfig m_config;
    TrainerInterface* m_trainer;
    SimulationState m_state;
};
```

### Trainer Hardware Abstraction Layer

```cpp
class TrainerInterface {
public:
    virtual bool Connect() = 0;
    virtual void Disconnect() = 0;
    virtual bool IsConnected() const = 0;
    
    virtual float GetPowerWatts() const = 0;
    virtual float GetCadenceRPM() const = 0;
    virtual float GetSpeedKph() const = 0;
    
    virtual void SetResistanceForceN(float forceN) = 0;
    virtual void SetGradientPercent(float gradient) = 0;
    virtual void SetERGTargetWatts(float targetWatts) = 0;
    
    virtual TrainerCapabilities GetCapabilities() const = 0;
};
```

Concrete implementations: `BLEFTMSTrainer`, `ANTPlusFECTrainer`, `SimulatedTrainer` (for testing without hardware).

---

## 5. Smart Trainer Integration — Detail

### Bluetooth FTMS

FTMS (Fitness Machine Service) is a Bluetooth GATT service (UUID 0x1826) defined by the Bluetooth SIG.

**Reading rider data:**

Indoor Bike Data characteristic (0x2AD2) is a notification characteristic that sends data every 1 second. Fields used:
- Instantaneous Power (sint16, Watts)
- Instantaneous Cadence (uint16, 0.5 RPM resolution)
- Instantaneous Speed (uint16, 0.01 km/h resolution)

**Sending resistance:**

Fitness Machine Control Point (0x2AD9) accepts control commands:
- **Set Indoor Bike Simulation Parameters** (opcode 0x11): sends wind speed (m/s), grade (%), Crr, CdA. Trainer computes resistance internally.
- **Set Target Resistance Level** (opcode 0x04): sends resistance as a percentage of max.

VeloWorld uses **Set Indoor Bike Simulation Parameters** as the primary command. This delegates the force curve to the trainer's internal model, which is tuned for its specific flywheel. The grade value is set to the equivalent gradient from the physics model:

```cpp
void BLEFTMSTrainer::SetResistanceForceN(float forceN) {
    float equivalentGrade = ComputeEquivalentGrade(forceN, m_config.systemMassKg);
    SendSimulationParameters(
        windSpeedMs: m_currentWindComponent,
        gradePercent: equivalentGrade,
        crr: m_config.crr,
        cdA: m_config.cdA
    );
}
```

### ANT+ FE-C

ANT+ FE-C (Fitness Equipment - Controls) operates on 2.4GHz using ANT+ protocol.

**Library:** `libant` (C++) or `OpenANT`

Key data pages:
- **Page 25 (Trainer Data)**: Trainer sends power, cadence, and accumulated power
- **Page 48 (Basic Resistance)**: Host sends resistance as % of max
- **Page 49 (Target Power)**: Host sends target power in watts (ERG mode)
- **Page 51 (Track Resistance)**: Host sends grade (%) and Crr (for slope simulation)

VeloWorld uses **Page 51** (Track Resistance) for free riding and **Page 49** (Target Power) for ERG mode.

---

## 6. Multiplayer Infrastructure

### Architecture

Multiplayer uses a **client-authoritative physics, server-position-reconciliation** model.

Each client runs its own physics simulation. The server does not run physics. Rider positions are broadcast from each client to the server, which relays them to other clients in the same session. The server validates positions for anti-cheat (future) and maintains session state.

This approach keeps latency low (physics is local) at the cost of allowing minor position discrepancies between clients. For a cycling simulation, exact position synchrony is less critical than in a twitch game — riders can be within a few meters of "true" position without a perceptible experience difference.

### Network Protocol

**WebSockets** for session management and position updates.

**Message format** (JSON for MVP, consider MessagePack or Protobuf at scale):

```json
{
  "type": "position_update",
  "session_id": "uuid",
  "rider_id": "uuid",
  "timestamp_ms": 1705312000123,
  "position_m": 24853.2,
  "velocity_kph": 34.7,
  "power_w": 220,
  "drafting_ids": ["rider-uuid-2", "rider-uuid-3"]
}
```

**Update rate:** 10 Hz (every 100ms) — sufficient for smooth rendering of other riders; higher rates increase bandwidth without meaningful quality improvement.

**Latency target:** <100ms end-to-end. At 100ms, position interpolation on the receiver can hide the latency entirely for typical cycling speeds.

### Session Rooms

A multiplayer session is a "room" with up to N riders on the same route. Room management:

```
POST /sessions          — Create a new session
GET  /sessions          — Browse active sessions for a route
POST /sessions/{id}/join — Join a session
WS   /sessions/{id}/stream — WebSocket connection for a session
```

### Data Synchronised

| Data | Update Rate | Method |
|---|---|---|
| Rider position (m) | 10 Hz | WebSocket push |
| Rider velocity (kph) | 10 Hz | WebSocket push |
| Power output (W) | 10 Hz | WebSocket push |
| Drafting state | 10 Hz | WebSocket push (list of rider IDs being drafted) |
| Chat messages | On event | WebSocket push |
| Session events (start, finish) | On event | WebSocket push |

---

## 7. Backend Services — Detail

### Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| API language | Go | High concurrency, low latency, strong standard library |
| API framework | gRPC + grpc-gateway | Type-safe internal APIs; REST for external clients |
| Auth | JWT + Google/Apple OAuth | Standard, well-understood |
| Database | PostgreSQL 16 | Relational integrity; excellent JSON support for semi-structured data |
| Cache | Redis 7 | Session store, leaderboards, live session state |
| Object storage | AWS S3 | Route files, terrain tiles, assets, ride recordings |
| Queue | AWS SQS | Route processing job queue |
| Workers | Python on EC2 (auto-scaling) | Route pipeline is Python; auto-scale based on queue depth |
| CDN | AWS CloudFront | Asset delivery to game clients |

### Core Database Schema (simplified)

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Routes
CREATE TABLE routes (
    id UUID PRIMARY KEY,
    owner_id UUID REFERENCES users(id),
    name TEXT NOT NULL,
    distance_m FLOAT NOT NULL,
    elevation_gain_m FLOAT,
    source_format TEXT NOT NULL,  -- gpx, fit, tcx
    processing_status TEXT NOT NULL,  -- queued, processing, ready, failed
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Rides
CREATE TABLE rides (
    id UUID PRIMARY KEY,
    rider_id UUID REFERENCES users(id),
    route_id UUID REFERENCES routes(id),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_s INTEGER,
    distance_m FLOAT,
    elevation_gain_m FLOAT,
    avg_power_w FLOAT,
    avg_speed_kph FLOAT
);

-- Route processing jobs
CREATE TABLE route_jobs (
    id UUID PRIMARY KEY,
    route_id UUID REFERENCES routes(id),
    stage TEXT NOT NULL,  -- ingestion, map_matching, terrain, road_mesh, environment, packaging
    status TEXT NOT NULL,  -- pending, running, complete, failed
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT
);
```

---

## 8. Data Storage Architecture

### Storage Tiers

| Data Type | Storage | Access Pattern |
|---|---|---|
| User accounts, route metadata | PostgreSQL | Frequent reads/writes, indexed |
| Ride telemetry (compressed) | PostgreSQL (partitioned by month) | Write-heavy, batch reads |
| Session / auth tokens | Redis | Very frequent, sub-ms read |
| Leaderboard data | Redis sorted sets | Frequent reads, real-time updates |
| Route GPX originals | S3 (Standard) | Write once, rare re-reads |
| Processed terrain tiles | S3 (Standard) + CloudFront | Frequent reads (game clients) |
| 3D assets (trees, buildings) | S3 (Standard) + CloudFront | Frequent reads, rarely changes |
| Cold ride archives (>1 year) | S3 Glacier | Write once, very rare access |

### Terrain Tile Cache Strategy

Terrain tiles are large (10–50MB each) and expensive to regenerate. Pre-generation strategy:

- On first request for any tile, generate and cache permanently
- Popular regions (Alps, Pyrenees, Dolomites, major US climbs) are pre-generated proactively
- Tile keys: `terrain/{latitude_floor}/{longitude_floor}/{resolution}.tif`
- Cache-control: immutable (terrain doesn't change)
- Total estimated storage for top 1000 cycling regions: ~2TB

---

## 9. Distribution

### Desktop Client

| Platform | Distribution Channel |
|---|---|
| Windows 10/11 | Steam (primary), standalone installer, Epic Games Store |
| macOS 13+ | Standalone installer (Mac App Store for future consideration) |
| Linux | Steam (Proton), native build for enthusiasts |

**Steam:** Preferred primary distribution. Provides: auto-updates, VAC (if needed), community features, review system, broad payment infrastructure. Valve takes 30% revenue share (reduces to 25% at $10M, 20% at $50M).

**Standalone installer:** Required for B2B distribution (team licences, race organisers). Supports site licensing.

### Mobile Companion App

iOS and Android companion apps (Phase 3). Functionality:
- Route upload from phone (Strava, Garmin Connect integration)
- Route library browsing
- Ride history and analytics
- Trainer pairing assistant (Bluetooth device scanner)
- Social feed, following, community
- Notification management

The companion app does not run the simulation. It is a companion to the desktop experience.

---

## 10. Development Hardware

### Workstation Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 8-core, 3.5GHz | AMD Ryzen 9 7950X or Intel Core i9-14900K |
| RAM | 32 GB DDR5 | 64 GB DDR5 |
| GPU | RTX 3070 | RTX 4080 or RTX 4090 |
| Storage | 1 TB NVMe | 2 TB NVMe (Unreal projects and terrain data are large) |
| Display | 1080p | 4K, colour-calibrated |
| Network | 100 Mbps | 1 Gbps (LiDAR dataset downloads are large) |

### Testing Hardware

All supported trainer models should be physically available in the development environment:

| Trainer | Protocol | Notes |
|---|---|---|
| Wahoo KICKR v6 | BLE FTMS + ANT+ FE-C | Market leader; reference device |
| Tacx NEO 2T | BLE FTMS + ANT+ FE-C | Excellent force feedback simulation |
| Elite Direto XR | BLE FTMS + ANT+ FE-C | Popular mid-range option |
| Wahoo KICKR CORE | BLE FTMS + ANT+ FE-C | Popular budget option |
| Garmin Tacx Flux S | ANT+ FE-C primary | ANT+ heavy; good test case |

Additional sensors:
- Garmin Rally RS200 power meter pedals (for power accuracy validation)
- Stages LR power meter (alternative accuracy reference)
- Garmin Edge 840 GPS computer (FIT/GPX file generation)
- Wahoo ELEMNT BOLT v2 (FIT/GPX file generation; alternative format variants)
- Polar H10 heart rate monitor (BLE)
- Garmin HRM-Pro heart rate monitor (ANT+)

---

## 11. Key Engineering Challenges

### Challenge 1 — Route Processing Speed

**Problem:**
LiDAR data queries, DEM processing, and mesh generation are computationally expensive. A naive sequential implementation may take 15–30 minutes per route, which is an unacceptable user experience.

**Target:** Under 5 minutes for routes up to 100km. Under 10 minutes for 200km.

**Solution:**

1. **Terrain tile caching**: Pre-generate and cache LiDAR tiles for all popular cycling regions. Cache hit rate target: >70% of uploaded routes. Cache misses trigger a full tile generation; hits skip Steps 3 entirely.

2. **Parallel stage execution**: Stages 2 and 5 are partially independent after map matching. Stage 3 (terrain) and Stage 5 (OSM data fetch) can be parallelised.

3. **Distributed workers**: Use an auto-scaling pool of EC2 spot instances for pipeline workers. Scale based on SQS queue depth. At peak load, 10–20 workers can run in parallel.

4. **Progressive delivery**: Begin streaming the first 5km of the route to the client as soon as those segments complete processing. The rider can start riding immediately while the rest processes in the background.

5. **Pre-caching popular routes**: Identify routes that appear frequently in uploads (popular race courses, famous climbs). Pre-process and cache these globally so any user uploading them gets instant results.

---

### Challenge 2 — Drafting Physics in Large Groups

**Problem:**
Accurate drafting requires simulating aerodynamic wakes for every rider in a group. In a 100-person event, computing full wake interactions per-rider is prohibitively expensive.

**Solution:**

For groups up to ~10 riders: compute individual pairwise wake interactions. This is accurate and computationally feasible.

For larger groups: use a **simplified zone model**:
- Riders are grouped into a "bunch"
- Each rider is assigned a position within the bunch (front, mid, rear, echelon)
- Position determines a fixed CdA reduction factor
- Position is updated based on rider's power output relative to group average

This sacrifices some physical accuracy for computational practicality. The model is tuned to match empirically measured group draft reductions from cycling aerodynamics research.

---

### Challenge 3 — Smart Trainer Hardware Inconsistency

**Problem:**
Smart trainers vary significantly in their resistance curves, BLE firmware behaviour, and response latency. A command that produces the correct resistance on a Wahoo KICKR may feel very different on an Elite Direto.

**Solution:**

1. **Hardware abstraction layer**: All trainer-specific code is isolated behind the `TrainerInterface` abstract class. The physics engine never interacts with hardware directly.

2. **Per-device calibration profiles**: Maintain a database of per-device resistance curve corrections. These are applied when converting physics force output to trainer commands.

3. **User spin-down calibration**: At session start, optionally prompt the user to perform a spin-down calibration. The calibration result is used to refine the device's correction factor.

4. **Fuzzing test harness**: Simulate trainer firmware bugs in the test environment (random delays, dropped packets, out-of-range values). Ensure the client handles all edge cases gracefully.

5. **User feedback loop**: In-app reporting for resistance accuracy issues. Reports are tagged with trainer model and firmware version, enabling systematic correction updates.

---

### Challenge 4 — LiDAR Data Gaps and Inconsistency

**Problem:**
LiDAR coverage is not uniform globally. Some regions have 1m resolution LiDAR; others have only 30m SRTM. The transition between data sources can create jarring gradient artefacts.

**Solution:**

1. **Graceful resolution degradation**: The pipeline selects the best available source per region. Routes processed with lower-resolution data are clearly labelled with a quality indicator.

2. **Elevation smoothing**: Regardless of source, the elevation profile is smoothed with a 5m rolling average before physics use. This eliminates most artefacts from data resolution differences.

3. **Multi-source mosaicking**: When a route crosses a region boundary (e.g. USA/Canada border where USGS ends), mosaic tiles from both sources with a smooth transition.

4. **Community corrections**: Allow users to flag and report elevation artefacts. Verified reports trigger a manual correction to the cached terrain tile.

---

## 12. Future Extensions

### VR Riding Mode
Full VR integration using OpenXR. Riders see a stereoscopic first-person view of the route. Head tracking drives the in-world camera. Targeting Valve Index, Meta Quest 3 (via PC Link), PlayStation VR2 (future). Primary challenge: VR requires consistent 90 FPS; current environments must be optimised for VR frame budgets.

### AR Smart Glasses HUD
Integration with heads-up display glasses (Garmin Varia Vision, Engopass, future AR glasses). During an outdoor ride, the glasses display a semi-transparent overlay showing: route navigation, power/speed targets, gradient ahead, competitor positions. The glasses connect to the VeloWorld companion app running on the cyclist's phone.

### AI Training Coach
An AI system that analyses the rider's power profile, historical ride data, and fitness metrics to generate personalised training recommendations. Selects routes appropriate to the rider's current training phase. Generates adaptive interval workouts. Monitors for overtraining signals.

### Outdoor Ride Replay
Replay a recorded outdoor ride as an indoor session. The rider's actual power and speed data from the outdoor ride is played back as a ghost rider. The indoor rider races against their own outdoor performance — useful for comparing performance over time on a familiar route.

### Professional Race Simulation
Collaboration with UCI race organisers to provide official race course routes, full peloton simulation, live race integration (riders watching live, or ghost-racing the peloton at race speed). Target market: professional team training camps, fan engagement during major tours.