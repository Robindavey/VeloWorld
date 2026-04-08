# VeloVerse — Physics Model Specification

## Purpose

This document defines the physics model used in the VeloVerse simulation. The objective is to accurately simulate the forces acting on a cyclist moving through a real-world environment, and to translate those forces into smart trainer resistance commands in real time.

VeloVerse's physics model is designed to be the most accurate cycling dynamics simulation available in any consumer indoor training platform. Unlike platforms that use simplified gradient-only resistance models, VeloVerse computes all significant forces every simulation frame.

The model covers:
- Gravity (gradient resistance)
- Rolling resistance (tyre/surface dependent)
- Aerodynamic drag (velocity-squared, rider position dependent)
- Drafting (group aerodynamics)
- Wind (direction and magnitude effects)
- Braking (pre-corner deceleration)
- Cornering traction (lateral force limits)
- Surface type variation

---

## Simulation Architecture

The physics engine runs locally on the client device at **60 Hz** (one frame every ~16.7ms). Running locally ensures sub-millisecond response to trainer input changes, which is essential for realistic resistance feel.

The simulation loop:

```
1. Read rider power output from smart trainer (W)
2. Read current rider position along route spline
3. Look up route attributes at current position:
   - gradient (degrees)
   - surface type
   - corner radius (if applicable)
   - wind zone (if weather active)
4. Compute all force components
5. Sum to total resistance force
6. Solve power equation for velocity
7. Advance rider position: Δposition = v × Δt
8. Compute target trainer resistance for next frame
9. Send resistance command to smart trainer
10. Update rider state (velocity, position, virtual speed)
11. Send position update to renderer and (if multiplayer) to server
```

---

## Core Force Model

All forces are computed in the direction of motion (along the road). The sign convention is:
- Positive = resisting motion (rider must apply power to overcome)
- Negative = assisting motion (rider gains speed)

### Total Resistance Force

```
F_total = F_gravity + F_rolling + F_aerodynamic + F_wind
```

Net rider acceleration:

```
a = (P_rider / v - F_total) / m
```

Where:
- `P_rider` = current power output (W)
- `v` = current velocity (m/s)
- `m` = total system mass (rider + bike, kg)

---

## 1. Gravity Force

Gravity is the dominant force on any significant gradient. It acts on the full system mass.

### Formula

```
F_gravity = m × g × sin(θ)
```

Where:
- `m` = rider mass + bike mass (kg). Default bike mass: 8 kg. Rider mass entered at setup.
- `g` = 9.81 m/s²
- `θ` = road gradient angle (radians), derived from elevation profile

### Gradient Computation

Gradient at any point is derived from the LiDAR elevation profile sampled along the road spline:

```
gradient_percent = (Δelevation / Δdistance) × 100
θ = arctan(gradient_percent / 100)
```

The elevation profile is smoothed with a rolling average over 5m to eliminate artefacts from data interpolation.

### Practical Range

| Gradient | F_gravity (75kg rider+bike) | Typical context |
|---|---|---|
| 0% | 0 N | Flat road |
| 5% | 40.4 N | Moderate climb |
| 10% | 79.6 N | Steep climb |
| 20% | 153.3 N | Extreme climb (e.g. Angliru) |
| -5% | -40.4 N | Moderate descent (assists rider) |

---

## 2. Rolling Resistance

Rolling resistance results from the deformation of the tyre contact patch as the wheel rotates. It acts continuously regardless of gradient.

### Formula

```
F_rolling = Crr × m × g × cos(θ)
```

Where:
- `Crr` = rolling resistance coefficient (dimensionless)
- `cos(θ)` accounts for the reduction in normal force on a gradient (very small at typical gradients; included for accuracy)

### Rolling Resistance Coefficients by Surface Type

| Surface Type | Crr Range | Notes |
|---|---|---|
| Smooth race asphalt | 0.003 – 0.004 | New road surface, high-end tyre |
| Standard tarmac | 0.004 – 0.006 | Typical road surface |
| Rough asphalt | 0.006 – 0.008 | Worn, patched, or poor quality |
| Wet asphalt | 0.006 – 0.008 | Additional deformation and water resistance |
| Concrete | 0.005 – 0.007 | Varies with joint roughness |
| Cobblestone (pavé) | 0.010 – 0.020 | Paris-Roubaix-style pavé up to 0.020 |
| Compacted gravel | 0.008 – 0.012 | Gravel race roads |
| Loose gravel | 0.015 – 0.030 | Soft or loose surface |

Crr is looked up from the surface type field in the road mesh metadata, set during the map matching stage.

### Tyre Configuration

The rider configures their virtual tyre type at session start. Tyre type applies a Crr multiplier:

| Tyre Type | Crr Modifier | Example |
|---|---|---|
| Race tubeless 25c | ×0.85 | Continental GP5000 TL |
| Race clincher 25c | ×1.00 | Standard reference |
| Race clincher 28c | ×0.95 | Slightly wider, lower pressure |
| Gravel tyre 38c | ×1.20 | Mixed surface tyre |
| MTB tyre | ×1.80 | Off-road tyre |

---

## 3. Aerodynamic Drag

Aerodynamic drag is the dominant resistance force at speeds above ~25 km/h. It increases with the square of velocity, making it increasingly significant as speed rises.

### Formula

```
F_drag = 0.5 × ρ × CdA × v_air²
```

Where:
- `ρ` = air density (kg/m³) — default 1.225 at sea level, 15°C. Reduced at altitude.
- `CdA` = drag coefficient × frontal area (m²) — depends on rider position
- `v_air` = airspeed relative to the rider (m/s) = rider velocity + headwind component

### Air Density at Altitude

Air density decreases with altitude, reducing aerodynamic drag. For rides at altitude (e.g. mountain passes), this is significant:

```
ρ = 1.225 × exp(-altitude_m / 8500)
```

Example: At 2000m altitude, ρ ≈ 1.007 kg/m³ — approximately 18% reduction in aerodynamic drag compared to sea level.

### CdA by Rider Position

| Position | CdA (m²) | Description |
|---|---|---|
| Upright touring | 0.40 – 0.50 | Hands on tops, upright posture |
| Standard road | 0.32 – 0.38 | Hands on hoods, typical racing posture |
| Drops / aggressive | 0.28 – 0.34 | Hands in drops, back flat |
| TT position | 0.20 – 0.25 | Aero bars, full time-trial position |
| Pro TT extreme | 0.17 – 0.20 | Elite athlete, optimised equipment |

The rider selects their position at session setup, or it can be estimated from power/speed data if the rider has performed an outdoor calibration ride.

### Effect on Power Requirement

At 40 km/h on flat road with CdA = 0.32:
```
F_drag = 0.5 × 1.225 × 0.32 × (40/3.6)² = 60.4 N
```
Power required to overcome drag alone: `60.4 × (40/3.6) = 671 W` — illustrating why aerodynamics dominate on flat fast roads.

---

## 4. Drafting Model

Drafting allows a trailing rider to exploit the aerodynamic wake of a leading rider, significantly reducing their drag force.

### Physical Basis

A rider moving through air creates a turbulent wake behind them. A following rider partially sheltered in this wake experiences reduced effective headwind, and therefore reduced drag.

### Drag Reduction by Position

| Position in Group | CdA Reduction | Effective CdA (from 0.32 base) |
|---|---|---|
| Solo (no draft) | 0% | 0.32 |
| 2nd wheel, 0.5m gap | 27% | 0.234 |
| 2nd wheel, 1.0m gap | 22% | 0.250 |
| Mid-peloton (10+ riders) | 38–42% | 0.186–0.197 |
| Echelon (crosswind) | 12–18% | 0.262–0.282 |

### Implementation

Each rider in the simulation occupies a position in 3D space. The drafting engine computes, for each trailing rider:
- Longitudinal separation (m)
- Lateral offset (m) — determines echelon or direct draft benefit
- Number of riders in the wake corridor

Draft benefit is applied as a multiplier on the trailing rider's CdA. The benefit falls off smoothly with distance and degrades rapidly with lateral offset beyond ~0.5m.

In crosswind conditions, the optimal drafting position shifts laterally (echelon formation). Riders who fail to position correctly in echelon receive reduced benefit.

---

## 5. Wind Model

Wind is directional and adds or subtracts from the rider's effective airspeed.

### Effective Airspeed

```
v_air = v_rider + v_wind_component
```

Where `v_wind_component` is the projection of wind velocity onto the rider's direction of motion:

```
v_wind_component = wind_speed × cos(wind_angle - road_bearing)
```

- Headwind (wind_angle = road_bearing): full additive effect
- Tailwind (wind_angle = road_bearing + 180°): full subtractive effect
- Crosswind (90°): zero component along road direction, but affects handling

### Wind Parameters

| Parameter | Range | Notes |
|---|---|---|
| Wind speed | 0–80 km/h | Values above 40 km/h are rare in race simulation |
| Wind direction | 0–360° | Degrees true north |
| Turbulence | 0.0–1.0 | Adds random variance to wind speed |
| Gusts | Boolean | If enabled, periodic sharp increases in wind speed |

Wind parameters can be:
- Set manually per session
- Derived from historical weather data for the route date (if the route is a recorded ride)
- Randomised within realistic bounds for training sessions

### Terrain Wind Shading

Routes through sheltered valleys, forests, or urban canyons experience reduced effective wind. A wind shade factor (0.0–1.0) is precomputed for each route segment based on terrain geometry and vegetation classification. This affects the wind component calculation:

```
v_wind_component_effective = v_wind_component × wind_shade_factor
```

---

## 6. Power-to-Speed Relationship

The simulation solves the power balance equation each frame to compute rider velocity.

### Energy Balance

```
P_rider = (F_gravity + F_rolling + F_aerodynamic) × v + dKE/dt
```

Where `dKE/dt` is the rate of change of kinetic energy (acceleration term):

```
dKE/dt = m × v × dv/dt
```

### Numerical Solution

At 60 Hz, each frame covers a time step Δt ≈ 0.0167s. The simulation uses a semi-implicit Euler integration scheme:

```
F_net = P_rider / v_prev - F_total(v_prev)
a = F_net / m
v_new = v_prev + a × Δt
position_new = position_prev + v_new × Δt
```

For the first frame and after stops, the solver handles the singularity at v=0 by imposing a minimum velocity of 0.1 m/s during the calculation, clamped to 0 in output.

### Virtual Mass (Inertia Simulation)

Smart trainers can vary their flywheel resistance, but cannot perfectly simulate the inertia of a real bicycle. VeloVerse applies a virtual mass correction: the simulation uses the actual system mass for all force calculations, while the trainer resistance command includes a small compensation factor to partially simulate the flywheel inertia difference.

---

## 7. Braking Model

The braking model governs the rider's ability to slow before corners and on descents. In Solo Training mode, braking is automatic (the simulation enforces safe corner entry speeds). In future advanced modes, rider-controlled braking inputs may be supported.

### Automatic Corner Speed Management

Before each corner, the simulation computes the maximum safe entry speed:

```
v_max_corner = sqrt(F_traction_lateral / m × r)
```

Where:
- `F_traction_lateral` = lateral traction limit (N) = μ_lateral × m × g
- `r` = corner radius (m)
- `μ_lateral` = lateral friction coefficient (surface type dependent)

If the rider's current velocity exceeds `v_max_corner` at the corner entry point, the simulation applies braking force to decelerate the rider to a safe speed. This deceleration is communicated to the rider via:
- Visual braking indicator on HUD
- Optional: increased trainer resistance (simulating braking effort)

### Braking Force

```
F_brake = μ_brake × m × g × cos(θ)
```

Where `μ_brake` is the braking friction coefficient, limited by surface traction.

| Surface | μ_brake (dry) | μ_brake (wet) |
|---|---|---|
| Smooth asphalt | 0.75 | 0.45 |
| Standard tarmac | 0.70 | 0.40 |
| Wet tarmac | — | 0.35 |
| Cobblestone (dry) | 0.60 | 0.30 |
| Gravel | 0.55 | 0.40 |

---

## 8. Cornering Physics

Cornering introduces lateral (centripetal) forces that determine whether a rider can safely navigate a corner at a given speed.

### Centripetal Force Requirement

```
F_centripetal = m × v² / r
```

The maximum available lateral traction is:

```
F_traction_max = μ_lateral × m × g
```

If `F_centripetal > F_traction_max`, traction is exceeded. In simulation terms, the rider cannot navigate the corner at this speed.

### Traction Coefficients by Surface

| Surface | μ_lateral (dry) | μ_lateral (wet) |
|---|---|---|
| Smooth asphalt | 0.70 | 0.40 |
| Standard tarmac | 0.65 | 0.38 |
| Cobblestone | 0.50 | 0.25 |
| Gravel | 0.45 | 0.35 |

### Banking Correction

Road banking (superelevation) reduces the centripetal force required:

```
v_max_banked = sqrt((μ_lateral + tan(α)) × g × r / (1 - μ_lateral × tan(α)))
```

Where `α` is the banking angle in radians. Banking data is derived from the road mesh generation stage.

---

## 9. Surface Type Model

Road surface type is one of the key parameters connecting the pipeline to the physics engine. Each surface modifies multiple physics parameters simultaneously.

### Surface Parameter Table

| Surface | Crr | μ_lateral (dry) | μ_lateral (wet) | μ_brake (dry) | Vibration Level |
|---|---|---|---|---|---|
| Race asphalt | 0.003 | 0.70 | 0.42 | 0.76 | 0 |
| Standard tarmac | 0.005 | 0.65 | 0.38 | 0.70 | 1 |
| Rough tarmac | 0.007 | 0.62 | 0.36 | 0.68 | 2 |
| Wet tarmac | 0.007 | 0.40 | 0.35 | 0.45 | 1 |
| Concrete | 0.006 | 0.63 | 0.35 | 0.68 | 2 |
| Cobblestone | 0.015 | 0.52 | 0.28 | 0.55 | 4 |
| Compacted gravel | 0.010 | 0.50 | 0.38 | 0.55 | 3 |
| Loose gravel | 0.022 | 0.42 | 0.32 | 0.48 | 4 |

**Vibration level** (0–5) drives haptic feedback on supported trainers and audio feedback in the simulation.

---

## 10. Smart Trainer Interface

The physics engine communicates with smart trainers over BLE (Bluetooth Low Energy) or ANT+ wireless protocols.

### Protocols Supported

**Bluetooth FTMS (Fitness Machine Service)**
- Modern standard, supported by all current-generation trainers
- BLE GATT service 0x1826
- Key characteristics:
  - Indoor Bike Data (0x2AD2): receives power, cadence, speed from trainer
  - Fitness Machine Control Point (0x2AD9): sends resistance commands

**ANT+ FE-C (Fitness Equipment - Controls)**
- Legacy standard, still in wide use (Garmin ecosystem)
- Two-way communication over ANT+ 2.4GHz
- Sends target resistance in ERG mode (watts) or slope simulation mode (%)

### Resistance Modes

**ERG Mode** (power target): The trainer holds a fixed wattage regardless of cadence. Used for structured workout intervals overlaid on routes.

**Slope Mode** (gradient simulation): The trainer resistance matches the simulated gradient and forces. Used for free riding. The physics engine computes `F_total` and converts to an equivalent gradient for the trainer:

```
simulated_gradient = arcsin(F_total / (m × g)) × 180/π
```

This gradient value is sent to the trainer. The trainer applies a resistance curve calibrated to simulate that gradient.

### Trainer Calibration

Different trainers have different resistance curves. The physics engine includes a per-trainer calibration layer that adjusts the resistance command to account for device-specific non-linearities. Calibration data is loaded from a trainer database and can be refined by the user via a spin-down calibration procedure.

---

## 11. Weather Integration

Weather conditions modify multiple physics parameters simultaneously.

### Rain

- Increases all surface friction coefficients to wet values
- Increases Crr by ~30–50%
- Adds visual rain particle effects
- Adds audio effects

### Temperature

- Modifies air density: `ρ = 1.225 × (273.15 / (273.15 + temp_celsius))`
- Higher temperatures reduce aerodynamic drag slightly

### Altitude (Automatic)

Altitude is derived from the route elevation profile. Air density and oxygen availability are updated continuously as the rider ascends or descends. This affects aerodynamic drag but not physiology (the platform does not model rider fatigue, though this is a future extension).

---

## 12. Future Extensions

### Rider Fatigue Model
Model declining power output over time based on Training Stress Score (TSS) and CP (Critical Power) curve. Useful for very long rides and race simulation.

### Tyre Puncture Simulation
Progressive increase in rolling resistance following a user-initiated puncture event. Used in training for race contingency preparation.

### Dynamic Peloton Turbulence
Simulate the chaotic wind environment inside a large group: unpredictable draft benefit fluctuations, cross-wheel turbulence, and surge-response dynamics.

### Rider Body Position Detection
Using body tracking (camera or sensor input), detect rider position changes (e.g. sitting vs standing, aero vs upright) and update CdA in real time without manual configuration.

### Bike Fit Integration
Import bike fit data (from Retül, Guru, or similar) to compute a personalised CdA estimate based on the rider's actual position on their specific bike.