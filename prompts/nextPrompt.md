# VeloWorld — Next Work Prompt (Resume)

## Context

You are continuing work on **VeloWorld**, following the deliverables defined in `prompts/firstPrompt.md` and the `/docs` specs.

Repo root: `C:/Users/robin/OneDrive/Cycling/VeloWorld`

Today’s goal is to **resume after Deliverable 4** and continue into **Deliverable 5**.

---

## What we completed since last session

### Deliverable 4 — Physics Simulation Engine (C++) ✅

We created a standalone, testable physics module under `client/` (this repo previously had **no `client/` directory**, so it was added).

**New files added**

- **CMake + tests**
  - `client/CMakeLists.txt` (standalone build)
- **Physics module**
  - `client/Source/VeloWorld/Physics/ForceModel.h`
  - `client/Source/VeloWorld/Physics/ForceModel.cpp`
  - `client/Source/VeloWorld/Physics/RouteProfile.h`
  - `client/Source/VeloWorld/Physics/RouteProfile.cpp`
  - `client/Source/VeloWorld/Physics/TrainerInterface.h`
  - `client/Source/VeloWorld/Physics/SimulatedTrainer.h`
  - `client/Source/VeloWorld/Physics/SimulatedTrainer.cpp`
  - `client/Source/VeloWorld/Physics/PhysicsEngine.h`
  - `client/Source/VeloWorld/Physics/PhysicsEngine.cpp`
  - `client/Source/VeloWorld/Physics/PhysicsTests.cpp`

**Implementation highlights**

- `ForceModel`
  - Implements: gravity, rolling resistance, aero drag, air density, total force, velocity solver.
  - Adds surface parameter helpers from the spec (subset for MVP):
    - `SurfaceCrr(surfaceType)`
    - `SurfaceMuLateralDry(surfaceType)`
    - `SurfaceMuBrakeDry(surfaceType)`
- `RouteProfile`
  - Loads physics attribute table from JSON (expects an array of objects with keys: `gradient_percent`, `corner_radius_m`, `banking_deg`, `surface_type`, `elevation_m`).
  - `GetAttributesAtPosition(positionM)` does linear interpolation between 1m samples.
  - Includes `SetAttributesForTesting(...)` helper to build routes in-memory for tests.
- `PhysicsEngine`
  - Tick loop: read trainer power → compute total forces → solve velocity → apply corner braking (simplified) → advance position → send resistance.
  - Sends trainer “gradient percent” derived from total force via:
    - \(theta = asin(F/(m*g))\)
    - \(gradientPercent = tan(theta)*100\)
- `SimulatedTrainer`
  - Constant power source, records last resistance/gradient/ERG commands (test assertions).

**Tests**

`client/Source/VeloWorld/Physics/PhysicsTests.cpp` includes:

- Force formula checks (gravity/rolling/air density/aero reference at 40kph).
- Integration checks:
  - Flat 200W converges into the expected 38–42 km/h range (spec target).
  - Trainer receives equivalent gradient computed from total force.
  - Surface switching increases resistance.
  - Basic corner-braking behavior guard.

**Build note (important)**

We attempted to run the build/tests but the environment reported:
- `cmake` is **not installed / not on PATH** on the Windows machine we ran commands from.

So the code is structured for `cmake --build && ctest`, but you must install CMake + a C++ toolchain (e.g. Visual Studio Build Tools) to actually compile locally.

---

## Changes / deviations vs the docs (explicitly documented)

These are the deliberate assumptions/shortcuts made to keep momentum while still aligning with the specs.

- **Surface type mapping assumption**
  - The docs specify surface tables (Crr, μ values) but not a numeric enum mapping.
  - We implemented an **internal mapping** in `ForceModel::SurfaceCrr/SurfaceMu*`:
    - 0 race asphalt, 1 standard tarmac, 2 rough tarmac, 3 wet tarmac, 4 concrete, 5 cobblestone, 6 compacted gravel, 7 loose gravel.
  - The pipeline must eventually output consistent `surface_type` IDs or we introduce a shared enum definition.

- **Corner braking implementation is simplified**
  - The docs define braking and corner traction models; we added a minimal “lookahead + clamp/decelerate” model:
    - Look ahead 15m for a corner radius
    - Compute \(v_{max} = sqrt(mu_{lat} * g * r)\)
    - If current v > vmax, apply decel = mu_brake * g (simplified)
  - This is good enough for MVP-level correctness tests but should be refined to match the full spec later (wet conditions, banking, gradient cos(theta), etc.).

- **RiderConfig change**
  - Instead of a fixed `crr` field, we now use:
    - `tyreCrrModifier` (defaults 1.0) multiplied by surface Crr from the table.
  - This better matches the spec’s “tyre config modifies Crr” approach.

---

## What we started next (Deliverable 5)

### Deliverable 5 — Smart Trainer Integration scaffolding (in progress)

We added a new `Trainer` namespace with basic plumbing (no real BLE/ANT+ yet).

**New files added**

- `client/Source/VeloWorld/Trainer/TrainerCalibration.h`
- `client/Source/VeloWorld/Trainer/TrainerCalibration.cpp`
- `client/Source/VeloWorld/Trainer/TrainerManager.h`
- `client/Source/VeloWorld/Trainer/TrainerManager.cpp`

**Current behavior**

- `TrainerCalibration` loads a JSON mapping `deviceId -> resistance_scale/resistance_offset_n`.
- `TrainerManager` can load the calibration DB and create a trainer instance.
- For now, “BLE FTMS” and “ANT FE-C” selections return an `UnsupportedTrainer` placeholder that implements the `TrainerInterface` but does not connect.

This is a scaffold so we can plug in real implementations next without rewriting the physics engine.

---

## What to do next (tomorrow)

### Immediate next steps (Deliverable 5)

1. **Add real driver class shells**
   - Create folders/files (even if platform-specific bodies are stubbed behind compile flags initially):
     - `client/Source/VeloWorld/Trainer/BLEFTMSDriver.*`
     - `client/Source/VeloWorld/Trainer/ANTPlusFECDriver.*`
   - Both must implement `VeloWorld::Physics::TrainerInterface`.

2. **Decide approach for platform code**
   - Windows BLE: WinRT APIs
   - macOS: CoreBluetooth via Objective-C++
   - Linux: BlueZ DBus
   - Add compile flags in CMake to enable/disable per platform so tests still build everywhere.

3. **Add calibration application point**
   - Decide where resistance calibration is applied:
     - either inside each driver when sending commands,
     - or in a wrapper around `TrainerInterface` used by `PhysicsEngine`.

4. **Add unit tests for Deliverable 5 scaffolding**
   - Tests for `TrainerCalibration` JSON parsing and defaults.
   - Tests for `TrainerManager::GetCalibrationForDevice`.

### Also recommended

- **Install build tooling on Windows** so we can run:
  - `cmake -S client -B client/build`
  - `cmake --build client/build`
  - `ctest --test-dir client/build`

---

## Guardrails (do not break)

- Keep the physics module buildable independently of Unreal Engine.
- Don’t change the `TrainerInterface` method signatures unless you also update the docs/Deliverable specs and all implementers.
- Prefer deterministic tests (use `SimulatedTrainer`, avoid real hardware dependencies in unit tests).

