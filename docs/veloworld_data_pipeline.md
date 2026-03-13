# VeloWorld — Data Pipeline Specification

## Purpose

The data pipeline is VeloWorld's core technical innovation. It automatically converts real-world route data — a GPS recording or planned route file — into a fully rideable, physics-accurate 3D simulation environment.

The pipeline must be:
- **Fast**: users should be able to upload a route and ride it within minutes, not hours
- **Accurate**: terrain must match the real world to the degree that physics simulation is meaningful
- **Scalable**: capable of processing thousands of routes per day without manual intervention
- **Global**: able to handle routes from any country where LiDAR or elevation data exists

Primary transformation:

```
GPX / FIT / TCX route file
        ↓
Validated, normalised route coordinates
        ↓
Map-matched road geometry with surface metadata
        ↓
LiDAR-accurate terrain height map
        ↓
3D road mesh with gradients, banking, and surface types
        ↓
Populated environment with procedural and AI-generated assets
        ↓
Packaged, streamed simulation — ready to ride
```

---

## Pipeline Architecture

The pipeline runs server-side as an asynchronous job. When a user uploads a route, it is queued immediately. The user receives progress updates and can begin riding as soon as the job completes.

```
User Upload (GPX / FIT / TCX)
        ↓
Route Parser & Validator
        ↓
Map Matching Service
        ↓
Terrain Reconstruction Service
        ↓
Road Mesh Generation Service
        ↓
Environment Generation Service
        ↓
Asset Resolution & Packaging
        ↓
S3 Upload & Cache Priming
        ↓
Simulation Ready — Client Notified
```

Each stage is a discrete service. Stages can be parallelised where dependencies allow (e.g. terrain reconstruction and road metadata enrichment can run concurrently after map matching completes).

---

## Stage 1: Route Upload and Parsing

### Supported Input Formats

| Format | Extension | Primary Source |
|---|---|---|
| GPX | .gpx | Most devices and planning tools (universal) |
| FIT | .fit | Garmin devices, Wahoo devices, Zwift exports |
| TCX | .tcx | Garmin Connect, older training platforms |

All three formats carry the same core data. GPX is XML-based and easiest to work with. FIT is binary and requires a dedicated parser. TCX is also XML.

### Data Extracted

- **GPS coordinates** — latitude/longitude pairs, the primary input
- **Timestamps** — per-point, used to derive speed and for replay
- **Raw elevation** — GPS-derived elevation is included if recorded, but is treated as a hint only (accuracy: ±3–10m). LiDAR replaces this.
- **Speed data** — optional, derived from timestamps if not explicitly recorded
- **Heart rate / power / cadence** — optional, ignored in route processing (used in ride replay only)

### Validation Rules

The parser rejects or flags routes that fail:
- Minimum point count (at least 100 coordinate pairs)
- Geographic plausibility (no teleportation jumps between points)
- Minimum route length (500m minimum)
- Coordinate format validity

Borderline routes (sparse GPS, large gaps) are accepted with a quality warning to the user.

### Output

Normalised route JSON:
```json
{
  "route_id": "uuid",
  "source_format": "gpx",
  "points": [
    { "lat": 45.832, "lon": 6.865, "timestamp": "2024-01-15T09:00:00Z", "raw_elevation": 1842 },
    ...
  ],
  "total_distance_m": 42500,
  "point_count": 4250,
  "bounding_box": { "north": 46.1, "south": 45.6, "east": 7.1, "west": 6.5 }
}
```

Libraries: **GPSBabel** (format conversion), **GDAL** (coordinate system handling), custom FIT parser using the Garmin FIT SDK.

---

## Stage 2: Map Matching

### Problem

Raw GPS tracks drift away from the actual road. A GPS receiver in a cycling computer has a position accuracy of approximately 3–15 metres under typical conditions. On narrow roads, switchbacks, or in urban canyons, the recorded track may appear to be in a field, on a footpath, or passing through buildings.

Map matching corrects this by snapping the GPS path to the known road network.

### Process

The route's GPS points are submitted to a map matching service. The service finds the most probable path along the road network that is consistent with the recorded coordinates, using Hidden Markov Model (HMM) algorithms.

### Services

**Option 1: Mapbox Map Matching API**
- Commercial service
- High quality, well-maintained
- Returns road metadata (type, surface, speed limits)
- Rate limits apply; paid per request

**Option 2: Valhalla (self-hosted)**
- Open source, Apache-licensed
- Can be deployed on VeloWorld infrastructure
- Uses OpenStreetMap data
- Lower ongoing cost; higher engineering overhead

**Option 3: OSRM (Open Source Routing Machine)**
- Open source
- Faster than Valhalla but returns less metadata
- Suitable for high-volume processing

Recommended approach: Valhalla self-hosted for cost efficiency at scale, with Mapbox as a quality fallback for complex routes.

### Output

For each point in the route, map matching returns:

```json
{
  "matched_lat": 45.8321,
  "matched_lon": 6.8652,
  "road_type": "secondary",
  "surface": "asphalt",
  "road_width_m": 6.5,
  "speed_limit_kmh": 80,
  "corner_radius_m": 45,
  "road_name": "Col du Grand-Saint-Bernard",
  "country_code": "FR"
}
```

Additionally, OpenStreetMap Overpass API is queried for the bounding box to retrieve:
- Building footprints
- Land use classifications (forest, farmland, urban, industrial)
- Water features (rivers, lakes)
- Points of interest

---

## Stage 3: Terrain Reconstruction

### Purpose

Terrain reconstruction produces an accurate elevation model for the area around the route. This is the foundation on which the road mesh is built and defines the gradients the physics engine will use.

GPS elevation data is discarded at this stage (used only as a quality hint). LiDAR-derived elevation is authoritative.

### LiDAR Data Sources

| Region | Dataset | Resolution | Availability |
|---|---|---|---|
| USA | USGS 3DEP (3D Elevation Program) | 1m in most areas | Free, public API |
| Europe | Copernicus DEM (GLO-30) | 30m globally, 10m EU | Free, public |
| UK | OS Terrain 50 / Terrain 5 | 5–50m | Licensed; negotiated access |
| France | RGE ALTI | 1m | Licensed via IGN |
| Australia | ELVIS (Geoscience Australia) | Variable | Free |
| New Zealand | LINZ LiDAR | 1m | Free, CC-BY |
| Global fallback | SRTM 30m | 30m | Free, public |

Coverage is expanding continuously. Routes in uncovered areas fall back to SRTM 30m DEM, which is adequate for physics purposes though less visually precise.

### Processing Steps

**Step 1: Define query bounding box**
Expand the route bounding box by 500m on all sides to ensure surrounding terrain is available for environment rendering.

**Step 2: Query elevation grid**
Call the appropriate LiDAR API or retrieve pre-cached tiles from S3. Tile caching is critical for performance — popular regions (Alps, Pyrenees, major US climbs) are pre-fetched and cached indefinitely.

**Step 3: Reproject to local coordinate system**
Convert from geographic coordinates (lat/lon) to a local projected CRS (e.g. UTM zone) for accurate metric calculations.

**Step 4: Interpolate elevation**
The elevation grid may be at 1m, 10m, or 30m resolution. Interpolate to the density required for the terrain mesh using bicubic interpolation.

**Step 5: Generate terrain height map**
Produce a regular grid height map in a format suitable for mesh generation (16-bit PNG or binary float array).

**Step 6: Compute route elevation profile**
Sample the height map along the map-matched road path to produce the authoritative elevation profile. This replaces GPS elevation data entirely.

Libraries: **GDAL**, **PDAL**, **rasterio**, **numpy** (Python-based processing workers).

### Output

- Terrain height map (GeoTIFF or binary array)
- Route elevation profile (sampled at 1m intervals along road path)
- Terrain quality flag (LiDAR resolution used)

---

## Stage 4: Road Geometry Generation

### Purpose

Build the actual 3D road surface the rider will travel along. This is a continuous mesh projected onto the terrain, representing the road as a physical object the simulation can interact with.

### Process

**Step 1: Generate road centreline spline**
Fit a smooth cubic Bezier spline through the map-matched GPS points. This eliminates residual GPS noise and produces a smooth, rideable path. Spline tension is tuned to maintain road geometry fidelity while avoiding sharp kinks.

**Step 2: Project spline onto terrain**
Project each point of the spline vertically onto the terrain height map. The road now follows the terrain surface.

**Step 3: Generate road cross-section mesh**
Extrude the spline into a mesh representing the road surface. Road width is taken from map matching metadata (or estimated from road classification). The cross-section includes:
- Carriageway
- Road edge / kerb
- Shoulder (where applicable)

**Step 4: Apply corner banking**
At corners with curvature radius below a threshold, apply road banking (superelevation) to the cross-section. Banking angle is estimated from road classification and corner radius — matching typical highway engineering standards.

**Step 5: Compute per-segment physics attributes**
For each 1m segment of road, compute and store:
- Gradient (degrees and percentage)
- Corner radius (m)
- Banking angle
- Surface type material ID
- Road quality flag

**Step 6: Apply surface materials**
Assign material types (smooth asphalt, rough asphalt, concrete, cobblestone, gravel, wet) based on map matching metadata and regional defaults.

### Output

- 3D road mesh (`.glb` or Unreal-compatible format)
- Per-segment physics attribute table
- Road spline data (for physics engine position tracking)

---

## Stage 5: Environment Generation

### Purpose

Populate the world around the road to create a visually immersive environment. The environment does not affect physics but is critical for the experience quality.

### Environment Components

**Terrain mesh**
The terrain height map is tessellated into a terrain mesh covering the route bounding box. Level-of-detail (LOD) is highest near the route and degrades with distance.

**Surface biome assignment**
The terrain is segmented into biomes based on:
- Elevation
- Land use classification from OpenStreetMap
- Country/region defaults

Biome types: Alpine, Subalpine forest, Deciduous forest, Mediterranean scrubland, Agricultural, Urban, Desert, Coastal.

Each biome has associated:
- Ground texture
- Vegetation density rules
- Ambient colour grading

**Vegetation placement**
Trees, bushes, and grass are placed procedurally according to biome rules. OpenStreetMap forest and land use polygons define placement boundaries. Within-polygon placement uses Poisson disk sampling for natural distribution. Vegetation assets are drawn from a curated per-biome library with random size and rotation variation.

**Building placement**
Building footprints from OpenStreetMap are extruded and textured. Building height is estimated from OSM tags where available, or from statistical priors per building type. Roof style is assigned per region (e.g. alpine chalet roofs in mountain areas, flat roofs in Mediterranean urban areas).

**Road furniture**
Kilometre markers, road signs, barriers, crash barriers, and traffic infrastructure placed according to road type and regional conventions.

**Landmarks**
Named POIs from OpenStreetMap are resolved to landmark assets where available in the library: churches, châteaux, mountain huts, water features, viewpoints.

**Optional: Street-level imagery integration**
Where street-view imagery is available and licensed (Mapillary open data, licensed Google Street View in commercial tiers), image data can seed texture generation for prominent buildings and landmarks, improving local realism.

### AI-Generated Asset Augmentation

For regions where the base asset library lacks variety, an AI image-to-3D pipeline (e.g. Luma AI, or a custom diffusion model) can generate additional building and landmark variants from reference imagery, expanding visual diversity without manual modelling.

### Output

Scene description manifest:
```json
{
  "terrain_mesh": "s3://veloworld-assets/routes/{id}/terrain.glb",
  "road_mesh": "s3://veloworld-assets/routes/{id}/road.glb",
  "asset_placements": [
    { "asset_id": "tree_alpine_01", "position": [x, y, z], "rotation": 42, "scale": 1.2 },
    ...
  ],
  "biome_zones": [...],
  "sky_preset": "alpine_clear",
  "ambient_audio_preset": "alpine_wind_light"
}
```

---

## Stage 6: Asset Resolution and Packaging

### Purpose

Resolve all asset references in the scene manifest to actual 3D asset files. Package terrain tiles, road mesh, and asset placements into a streamable format for the client.

### Asset Library Structure

Assets are stored in S3 with a structured taxonomy:

```
/assets/
  /vegetation/
    /trees/
      tree_alpine_01.glb
      tree_deciduous_02.glb
      ...
    /bushes/
  /buildings/
    /alpine/
    /mediterranean/
    /urban/
  /road_furniture/
  /landmarks/
```

### Streaming Architecture

Routes are not downloaded as a single file. The client streams terrain tiles and assets as the rider progresses along the route, using a prefetch buffer of 2km ahead of the rider's current position. This allows riding to begin before the full route is processed or downloaded.

Tile size: 256m × 256m terrain tiles. At 25MB per tile (compressed), a 100km route requires approximately 400 tiles covering the corridor — roughly 10GB of terrain data. Streaming eliminates the need to download this upfront.

---

## Pipeline Performance Targets

| Route Length | Processing Time Target | Notes |
|---|---|---|
| <50 km | <3 minutes | Cache hit likely for popular regions |
| 50–200 km | <10 minutes | Parallel terrain/environment workers |
| 200+ km | <25 minutes | Partitioned processing |
| Grand Tour stage | <30 minutes | Pre-processed ahead of race season |

### Optimisation Strategies

**Terrain tile caching**: Pre-process and cache LiDAR tiles for all regions where popular routes exist. Cache hit eliminates the LiDAR query and interpolation stages.

**Parallel workers**: Terrain reconstruction and environment generation are independent after map matching. Run in parallel using distributed compute workers (AWS Lambda or EC2 spot instances).

**Progressive delivery**: Begin delivering processed segments to the client before the full pipeline completes. Riders can start from the beginning while the rest of the route processes.

**Priority queue**: Routes requested by active users in a live session are processed ahead of background jobs.

---

## Data Quality and Fallback Behaviour

| Data Source | Quality Level | Fallback |
|---|---|---|
| 1m LiDAR | Excellent | Primary |
| 10m DEM | Good | When 1m unavailable |
| 30m SRTM | Adequate | Global fallback |
| GPS elevation only | Poor | Never used for physics; used only for display if all else fails |

Routes processed with degraded data sources carry a quality badge visible to the rider. The physics engine adjusts confidence bounds on gradient values when using lower-resolution elevation data.