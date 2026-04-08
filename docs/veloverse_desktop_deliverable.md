# VeloVerse Desktop App Deliverable

## Purpose
Define the desktop app as a separate, shippable product for Windows, macOS, and Linux that launches and manages the VeloVerse local experience with minimal setup.

## Product Definition
The desktop app is a companion launcher and runtime shell for VeloVerse.
It is not a replacement backend in v1.
It packages startup, diagnostics, updates, and user onboarding into one installable app.

## Primary User Outcomes
- Install once and run VeloVerse without terminal commands.
- Start and stop required local services from a single UI.
- Verify trainer, Bluetooth, and route-processing readiness before ride.
- Launch Map Tracer and 3D Route with secure local context.
- Keep app and local runtime up to date.

## Platform Targets
- Windows 11+
- macOS 13+
- Ubuntu 22.04+

## Recommended Tech Stack
- Shell: Electron + TypeScript
- UI: React + Vite inside Electron renderer
- Local process manager: Node child_process with structured logs
- Packaging:
  - Windows: NSIS installer
  - macOS: DMG + signed app bundle
  - Linux: AppImage and optional deb

## Desktop MVP Scope
### Included
- Login token bootstrap for local frontend session.
- One-click Start Environment and Stop Environment.
- Health panel for backend API, pipeline worker, and frontend HTTPS endpoint.
- Open buttons:
  - Open Dashboard
  - Open Map Tracer
  - Open Route 3D
- Route processing queue status panel.
- Basic crash-safe logging and user-visible error messages.

### Excluded
- Offline full map tile packs.
- Embedded PostgreSQL management UI.
- Full trainer firmware diagnostics.
- Multi-user account switching.

## Functional Requirements
1. App startup check:
- Validate Docker availability.
- Validate cert files for HTTPS mode.
- Validate required ports are free or explain conflict.

2. Environment control:
- Start/stop scripts integrated with existing project scripts.
- Streaming logs per service with severity highlighting.

3. Secure frontend launch:
- Open HTTPS frontend URL.
- Inject or refresh veloverse_token only when user opts in.

4. Device readiness:
- Show browser security context guidance for Bluetooth.
- Show trainer connectivity status from frontend heartbeat.

5. Update channel:
- Manual check in MVP.
- Auto-update channel in v1.1.

## Non-Functional Requirements
- Cold launch to usable dashboard: under 10 seconds on recommended hardware.
- Clear recovery path for all startup failures.
- No silent failures.
- Signed binaries for Windows/macOS releases.

## Architecture Overview
- Main process:
  - service orchestration
  - local IPC endpoints
  - update checks
- Renderer process:
  - onboarding
  - controls
  - health status
  - logs view
- Local runtime:
  - existing backend
  - existing worker/pipeline
  - existing frontend HTTPS server

## Release Plan
### Milestone A: Internal Alpha
- Manual install
- Start/stop controls
- health checks
- logs panel

### Milestone B: Closed Beta
- Signed installers
- error telemetry (opt-in)
- guided recovery flows

### Milestone C: Public Desktop MVP
- production installers for 3 platforms
- versioned release notes
- support docs and rollback path

## QA Acceptance Criteria
- Fresh machine setup succeeds with no terminal usage.
- Backend, worker, and frontend start from desktop app controls.
- User can upload route and open Route 3D in one session.
- Weather and biome overlays function after desktop launch.
- App can stop all managed processes cleanly.

## Risks and Mitigations
- Bluetooth permission differences per OS:
  - mitigation: per-OS first-run guidance and checks.
- Docker runtime variability:
  - mitigation: preflight diagnostics and actionable errors.
- Certificate trust friction:
  - mitigation: automated cert generation flow with clear prompts.

## Definition of Done
Desktop deliverable is complete when:
- Installers are available for Windows, macOS, Linux.
- Startup, diagnostics, and browser launch work without terminal commands.
- Core ride flow works end-to-end from desktop app.
- Release documentation and troubleshooting guide are published.
