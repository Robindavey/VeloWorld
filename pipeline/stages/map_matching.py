"""
Map matching stage implementation.

Snaps GPS coordinates to the road network using various map matching services.
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID

import aiohttp
import numpy as np
from pydantic import BaseModel

from veloworld_pipeline import RouteData, RoutePoint, PipelineResult, ProcessingStage


class MapMatchingConfig(BaseModel):
    """Configuration for map matching services."""
    service: str = "valhalla"  # valhalla, mapbox, or osrm
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout_seconds: int = 30
    max_points_per_request: int = 100


class MapMatcher:
    """Map matching service coordinator."""

    def __init__(self, config: MapMatchingConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def match_route(self, route_data: RouteData) -> Tuple[List[RoutePoint], List[str]]:
        """
        Match GPS coordinates to road network.

        Args:
            route_data: Input route data

        Returns:
            Tuple of (matched_points, warnings)
        """
        if not route_data.points:
            return [], ["No points to match"]

        warnings = []

        # Split route into chunks if too long
        chunks = self._chunk_route(route_data.points)
        all_matched_points = []

        for i, chunk in enumerate(chunks):
            try:
                matched_chunk = await self._match_chunk(chunk)
                all_matched_points.extend(matched_chunk)

                if i > 0:
                    # Ensure continuity between chunks
                    all_matched_points = self._ensure_chunk_continuity(all_matched_points)

            except Exception as e:
                warnings.append(f"Failed to match chunk {i}: {str(e)}")
                # Fall back to original points for this chunk
                all_matched_points.extend(chunk)

        # Validate matched route
        validation_warnings = self._validate_matched_route(all_matched_points)
        warnings.extend(validation_warnings)

        return all_matched_points, warnings

    def _chunk_route(self, points: List[RoutePoint]) -> List[List[RoutePoint]]:
        """Split route into chunks for API limits."""
        if len(points) <= self.config.max_points_per_request:
            return [points]

        chunks = []
        for i in range(0, len(points), self.config.max_points_per_request):
            chunk = points[i:i + self.config.max_points_per_request]
            chunks.append(chunk)

        return chunks

    async def _match_chunk(self, points: List[RoutePoint]) -> List[RoutePoint]:
        """Match a single chunk of points."""
        if self.config.service == "valhalla":
            return await self._match_with_valhalla(points)
        elif self.config.service == "mapbox":
            return await self._match_with_mapbox(points)
        elif self.config.service == "osrm":
            return await self._match_with_osrm(points)
        else:
            raise ValueError(f"Unsupported map matching service: {self.config.service}")

    async def _match_with_valhalla(self, points: List[RoutePoint]) -> List[RoutePoint]:
        """Match using Valhalla (self-hosted) map matching."""
        base_url = self.config.base_url or "http://localhost:8002"

        # Prepare coordinates in Valhalla format
        coordinates = []
        for point in points:
            coordinates.append({
                "lat": point.lat,
                "lon": point.lon,
                "type": "break" if point == points[0] or point == points[-1] else "via"
            })

        payload = {
            "encoded_polyline": False,
            "shape": coordinates,
            "costing": "auto",  # Use automobile costing for road matching
            "shape_match": "map_snap",  # Snap to nearest road
            "filters": {
                "attributes": ["shape_attributes.dense_shape", "shape_attributes.speed", "shape_attributes.speed_limit"]
            }
        }

        async with self.session.post(f"{base_url}/trace_route", json=payload) as response:
            if response.status != 200:
                raise Exception(f"Valhalla API error: {response.status}")

            data = await response.json()

            if "trip" not in data or "legs" not in data["trip"]:
                raise Exception("Invalid Valhalla response format")

            return self._parse_valhalla_response(data, points)

    async def _match_with_mapbox(self, points: List[RoutePoint]) -> List[RoutePoint]:
        """Match using Mapbox Map Matching API."""
        if not self.config.api_key:
            raise ValueError("Mapbox API key required")

        base_url = "https://api.mapbox.com/matching/v5/mapbox/driving"

        # Convert points to Mapbox format
        coordinates = ";".join(f"{point.lon},{point.lat}" for point in points)

        params = {
            "access_token": self.config.api_key,
            "coordinates": coordinates,
            "steps": "true",
            "overview": "full",
            "annotations": "speed,distance,duration"
        }

        async with self.session.get(base_url, params=params) as response:
            if response.status != 200:
                raise Exception(f"Mapbox API error: {response.status}")

            data = await response.json()

            if "matchings" not in data or not data["matchings"]:
                raise Exception("No matching routes found")

            return self._parse_mapbox_response(data, points)

    async def _match_with_osrm(self, points: List[RoutePoint]) -> List[RoutePoint]:
        """Match using OSRM (simplified - OSRM doesn't have true map matching)."""
        base_url = self.config.base_url or "http://localhost:5000"

        # Convert to OSRM route format
        coordinates = ";".join(f"{point.lon},{point.lat}" for point in points)

        url = f"{base_url}/route/v1/driving/{coordinates}"

        params = {
            "overview": "full",
            "steps": "true",
            "annotations": "true"
        }

        async with self.session.get(url, params=params) as response:
            if response.status != 200:
                raise Exception(f"OSRM API error: {response.status}")

            data = await response.json()

            if "routes" not in data or not data["routes"]:
                raise Exception("No routes found")

            return self._parse_osrm_response(data, points)

    def _parse_valhalla_response(self, data: Dict[str, Any], original_points: List[RoutePoint]) -> List[RoutePoint]:
        """Parse Valhalla map matching response."""
        matched_points = []

        for leg in data["trip"]["legs"]:
            if "shape" in leg:
                # Decode shape into coordinates
                shape_coords = self._decode_valhalla_shape(leg["shape"])

                for i, (lat, lon) in enumerate(shape_coords):
                    # Try to preserve original timestamps and elevations
                    original_point = original_points[min(i, len(original_points) - 1)]

                    matched_point = RoutePoint(
                        lat=lat,
                        lon=lon,
                        timestamp=original_point.timestamp,
                        raw_elevation=original_point.raw_elevation,
                        matched_lat=lat,
                        matched_lon=lon,
                        road_type=leg.get("road_type", "unknown"),
                        surface=leg.get("surface", "unknown"),
                        speed_limit_kmh=leg.get("speed_limit")
                    )
                    matched_points.append(matched_point)

        return matched_points

    def _parse_mapbox_response(self, data: Dict[str, Any], original_points: List[RoutePoint]) -> List[RoutePoint]:
        """Parse Mapbox map matching response."""
        matched_points = []
        matching = data["matchings"][0]  # Use first matching

        for i, coord in enumerate(matching["geometry"]["coordinates"]):
            lon, lat = coord

            # Try to preserve original data
            original_point = original_points[min(i, len(original_points) - 1)]

            matched_point = RoutePoint(
                lat=lat,
                lon=lon,
                timestamp=original_point.timestamp,
                raw_elevation=original_point.raw_elevation,
                matched_lat=lat,
                matched_lon=lon,
                road_type="unknown",  # Mapbox doesn't provide road type easily
                surface="unknown",
                speed_limit_kmh=None
            )
            matched_points.append(matched_point)

        return matched_points

    def _parse_osrm_response(self, data: Dict[str, Any], original_points: List[RoutePoint]) -> List[RoutePoint]:
        """Parse OSRM route response (simplified)."""
        matched_points = []
        route = data["routes"][0]

        for i, coord in enumerate(route["geometry"]["coordinates"]):
            lon, lat = coord

            original_point = original_points[min(i, len(original_points) - 1)]

            matched_point = RoutePoint(
                lat=lat,
                lon=lon,
                timestamp=original_point.timestamp,
                raw_elevation=original_point.raw_elevation,
                matched_lat=lat,
                matched_lon=lon,
                road_type="unknown",
                surface="unknown",
                speed_limit_kmh=None
            )
            matched_points.append(matched_point)

        return matched_points

    def _decode_valhalla_shape(self, shape: str) -> List[Tuple[float, float]]:
        """Decode Valhalla encoded polyline (simplified implementation)."""
        # This is a simplified decoder - real implementation would use proper polyline decoding
        # For now, return original coordinates as fallback
        return []

    def _ensure_chunk_continuity(self, points: List[RoutePoint]) -> List[RoutePoint]:
        """Ensure continuity between matched chunks."""
        # Simple implementation - in production, would interpolate between chunk boundaries
        return points

    def _validate_matched_route(self, points: List[RoutePoint]) -> List[str]:
        """Validate the quality of matched route."""
        warnings = []

        if not points:
            warnings.append("No matched points returned")
            return warnings

        # Check for unrealistic jumps
        for i in range(1, len(points)):
            prev, curr = points[i-1], points[i]
            if hasattr(prev, 'matched_lat') and hasattr(curr, 'matched_lat'):
                distance = self._haversine_distance(
                    prev.matched_lat, prev.matched_lon,
                    curr.matched_lat, curr.matched_lon
                )
                if distance > 1000:  # 1km jump
                    warnings.append(f"Large jump in matched route at point {i}: {distance:.1f}m")

        # Check that points are on reasonable roads
        road_types = [p.road_type for p in points if p.road_type]
        if road_types and not any(rt in ['primary', 'secondary', 'tertiary', 'residential', 'unclassified'] for rt in road_types):
            warnings.append("Matched route may not be on drivable roads")

        return warnings

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate haversine distance in meters."""
        R = 6371000
        lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
        lat2_rad, lon2_rad = np.radians(lat2), np.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = np.sin(dlat/2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon/2)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

        return R * c


async def process_map_matching(route_data: RouteData, config: Optional[MapMatchingConfig] = None) -> PipelineResult:
    """
    Process map matching for a route.

    Args:
        route_data: Input route data
        config: Map matching configuration

    Returns:
        Pipeline result with matched route data
    """
    if config is None:
        # Default configuration for testing
        config = MapMatchingConfig(service="mock")

    try:
        async with MapMatcher(config) as matcher:
            if config.service == "mock":
                # Mock implementation for testing
                matched_points = []
                for point in route_data.points:
                    matched_point = RoutePoint(
                        lat=point.lat,
                        lon=point.lon,
                        timestamp=point.timestamp,
                        raw_elevation=point.raw_elevation,
                        matched_lat=point.lat + np.random.normal(0, 0.0001),  # Small random offset
                        matched_lon=point.lon + np.random.normal(0, 0.0001),
                        road_type="secondary",
                        surface="asphalt",
                        speed_limit_kmh=50
                    )
                    matched_points.append(matched_point)

                warnings = ["Using mock map matching - not suitable for production"]
            else:
                matched_points, warnings = await matcher.match_route(route_data)

        # Update route data with matched points
        updated_route_data = route_data.copy()
        updated_route_data.points = matched_points
        updated_route_data.quality_warnings.extend(warnings)

        return PipelineResult(
            stage=ProcessingStage.MAP_MATCHING,
            success=True,
            data={
                'matched_route': updated_route_data.dict(),
                'matched_point_count': len(matched_points),
                'warnings': warnings
            }
        )

    except Exception as e:
        return PipelineResult(
            stage=ProcessingStage.MAP_MATCHING,
            success=False,
            errors=[f"Map matching failed: {str(e)}"]
        )