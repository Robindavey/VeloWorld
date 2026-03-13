# VeloWorld — Product Concept

## Overview

VeloWorld is a next-generation indoor cycling simulator designed to recreate real-world cycling routes with high physical and visual realism. It bridges the gap between indoor training tools and immersive simulation, combining GPS data, LiDAR elevation models, physics-accurate cycling dynamics, and AI-generated environments to deliver rides that feel genuinely representative of their real-world counterparts.

The platform is built for serious cyclists who want training sessions that are both physiologically effective and mentally engaging. It is also designed for accessibility — enabling riders who cannot travel to famous routes, or who are returning from injury, to experience and prepare for real-world terrain.

Users upload a recorded or planned cycling route in GPX, FIT, or TCX format. The platform automatically constructs a fully rideable simulation: terrain mesh from LiDAR elevation data, road surface from map-matched geometry, and visual environment from procedural generation augmented by AI assets and optionally street-level imagery.

---

## Problem Being Solved

Existing indoor cycling platforms fall into two categories:

**Gamified environments** (e.g. Zwift): Custom-built fantasy worlds with simplified physics. Engaging but not representative of real routes.

**Video playback systems** (e.g. RGT, Fulgaz): Real-world video footage overlaid with basic gradient resistance. Realistic visually but limited by video quality, physics accuracy, and route availability.

VeloWorld occupies a new category: **physics-accurate, procedurally-generated real-world simulation**. Routes are not filmed — they are reconstructed from geospatial data and rendered in real time. Physics are not approximated — they are modelled from first principles using established cycling biomechanics and fluid dynamics.

---

## Core Concept: The Route Pipeline

The central innovation is the route processing pipeline. Given any GPS route as input, the system:

1. Parses and validates the GPS track
2. Aligns it to the road network using map matching
3. Queries LiDAR elevation datasets to reconstruct true terrain
4. Generates a 3D road mesh with accurate gradients, corner radii, and surface types
5. Populates the environment with procedurally placed and AI-generated assets
6. Delivers a fully rideable simulation within minutes of upload

This means any route in the world — a local training loop, a famous race course, a holiday destination — can become a rideable VeloWorld experience, without any manual content creation.

---

## Key Modes

### Solo Training Mode
The rider uploads a route or selects from the route library. The simulation runs the route with full gradient resistance communicated to the smart trainer. The rider can configure: workout overlays (power zones, targets), pacing guides, and head-up display elements. Structured workout intervals can be overlaid on any route, combining the training value of ERG-mode workouts with the mental engagement of riding a real place.

### Experience Mode
An immersive, scenic ride experience aimed at accessibility and enjoyment. AI-generated landscape rendering emphasises beauty and realism over training data. Optional audio narration describes the route — geography, culture, race history. Designed for riders who are returning from injury, warming up, or simply want a meditative experience. Suitable for use on standard exercise bikes without smart trainers via power estimation.

### Team Recon Mode
Professional-grade race preparation. Teams or individual riders can pre-ride courses before racing them. Supports: configurable weather conditions (wind speed and direction, rain, temperature), realistic road surface modelling, drafting simulation within a team, team time trial pace management, and tactical zone analysis. Designed for use by professional cycling teams and serious amateur racers preparing for events.

### Holiday Preparation Mode
Allows riders to preview real routes before travelling to ride them. Ride the full route or selected segments. Analyse climbs, descents, and technical sections. Test equipment configurations — gearing, tyre choice, bike setup — against the actual route profile before departure.

### Route Recon (Segment Analysis)
Riders can isolate individual segments — a single climb, a technical descent, a sprint section — and repeat them in isolation. Useful for targeted training, pacing practice, or familiarisation with key race moments.

---

## Bike Handling Simulation

Unlike all existing indoor cycling platforms, VeloWorld simulates bike handling mechanics as a first-class feature:

- **Braking zones**: The rider must manage braking force before corners. Excessive speed entering a corner results in a handling event (loss of traction, crash simulation, or time penalty depending on mode).
- **Cornering grip**: Lateral traction is modelled per surface type and banking angle. Road camber and corner radius affect maximum safe speed.
- **Surface traction**: Transitions between tarmac, wet road, gravel, and cobbles affect both rolling resistance and handling limits.
- **Tyre model**: Different tyre profiles (road, gravel, tubeless) carry different rolling resistance and traction characteristics. Riders can configure their virtual tyre choice.

These mechanics are communicated to the rider visually and, where supported, through resistance changes on the smart trainer — increased resistance through a technical corner, reduced resistance on a smooth descent.

---

## Route Marketplace

VeloWorld includes a community and commercial route marketplace:

- **Free sharing**: Riders upload and share personal routes freely within the community
- **Premium routes**: Curated high-quality routes sold by official content creators, race organisers, and professional teams
- **Official event routes**: Race organisers license VeloWorld to distribute official event routes ahead of races
- **Collaborative routes**: Teams or groups build shared route libraries

Marketplace routes carry quality ratings, rider reviews, difficulty tags, and estimated completion times.

---

## Disruptive Features Summary

1. **LiDAR-based terrain reconstruction** — True elevation from geospatial data, not GPS approximation
2. **Real cycling physics engine** — Forces modelled from first principles: gravity, drag, rolling resistance, wind
3. **Bike handling simulation** — Cornering, braking, surface traction — unique in indoor cycling
4. **Race-team tactical simulation** — Drafting, wind, team dynamics for professional preparation
5. **Universal route generation** — Any GPX route becomes a rideable simulation within minutes
6. **Route marketplace** — Community and commercial route ecosystem
7. **Smart glasses HUD integration** — Heads-up display for riders using AR glasses during real outdoor rides for recon
8. **Accessibility mode** — Narrated, scenic experience for non-training use cases

---

## Target Users

| Segment | Use Case |
|---|---|
| Competitive road cyclists | Race preparation, structured training, route recon |
| Triathlon athletes | Bike leg simulation, power-based training |
| Amateur enthusiasts | Engaging indoor rides, community routes |
| Professional teams | Tactical preparation, shared route libraries |
| Returning-from-injury riders | Low-intensity scenic riding, gradual return |
| Travelling cyclists | Preview destinations before arrival |
| Cycling tourists | Explore routes virtually before booking travel |

---

## Platform Philosophy

VeloWorld is built on three principles:

**Accuracy over approximation.** Physics, terrain, and handling are modelled correctly, not simplified for convenience.

**Real places, not invented ones.** The world's roads are the content. VeloWorld's job is to faithfully represent them.

**Training value and mental engagement are not opposites.** The platform proves that a rigorous physiological workout and an immersive, enjoyable experience can occupy the same session.
