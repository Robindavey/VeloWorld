# VeloVerse — Next Work Prompt

## Completed This Session

- Added rider profile metrics to backend with defaults:
  - `rider_weight_kg` default `75.0`
  - `ftp_w` default `210.0`
- New migration:
  - `backend/db/migrations/003_add_rider_metrics.sql`
- Added profile update API:
  - `PUT /auth/profile`
  - Existing `GET /auth/me` now returns weight + FTP
- Extended render profile point model to include geolocation:
  - `lat`, `lon` now flow in render-data points
- Pipeline worker now stores route render profile with lat/lon in Redis:
  - key `route_render:{route_id}`
- Created a dedicated demo page:
  - `frontend/demo.html`
  - route dropdown for ready routes
  - satellite imagery map (Esri World Imagery via Leaflet)
  - moving rider dot following true route lat/lon
  - collapsible/expandable side panel for elevation chart
  - upgraded HUD with speed, grade, power, distance, time, power zone
  - rider profile editor (weight/FTP) on-page, saved via API
  - time multiplier control for long routes
- Added entry link from `frontend/index.html` to `demo.html`
- Updated `scripts/dev.sh` migration runner to include migration `003`

## Runtime Status

- DB migration `003` applied.
- Backend rebuilt + running.
- Pipeline worker rebuilt + running.
- API health endpoint OK.

## Next Tasks

1. Add route status auto-polling on `demo.html` and `index.html` until ready.
2. Add min/max smoothing for grade calculation to reduce jitter on noisy GPS elevation.
3. Add optional map source selector (Esri/OSM/Topo).
4. Add reset-to-start and scrub/seek controls on demo timeline.
5. Persist render profile to durable storage (S3/DB) and use Redis as cache only.

## Latest Work (31 March 2026)

- Fixed `createRoadsideProps` syntax error in `frontend/route-3d.html`.
- Implemented densify fallback for sparse route render payloads to avoid only-start point.
- Increased roadside propagation frequency (`i += 3` and cluster every 15 points) for richer tree/rock coverage.
- Retained gradient path coloring and camera follow after patch.

## Session Rule

Always update `prompts/nextPrompt.md` at the end of each session with latest completed work + next tasks.
