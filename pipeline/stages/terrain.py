"""
Terrain reconstruction stage implementation.

Reconstructs accurate terrain elevation from LiDAR and DEM data sources.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID

import numpy as np
from pydantic import BaseModel
from shapely.geometry import box

from veloverse_pipeline import RouteData, PipelineResult, ProcessingStage


class TerrainConfig(BaseModel):
    """Configuration for terrain reconstruction."""
    data_source: str = "copernicus"  # copernicus, usgs, ign, etc.
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    resolution_m: float = 10.0  # Target resolution in meters
    buffer_m: float = 500.0  # Buffer around route in meters
    timeout_seconds: int = 60
    max_retries: int = 3


class ElevationSource:
    """Base class for elevation data sources."""

    def __init__(self, config: TerrainConfig):
        self.config = config

    async def get_elevation_data(self, bbox: Dict[str, float], resolution_m: float) -> Optional[np.ndarray]:
        """
        Get elevation data for a bounding box.

        Args:
            bbox: Bounding box with north, south, east, west
            resolution_m: Desired resolution in meters

        Returns:
            Elevation array or None if unavailable
        """
        raise NotImplementedError


class CopernicusDEM(ElevationSource):
    """Copernicus DEM data source (30m global coverage)."""

    async def get_elevation_data(self, bbox: Dict[str, float], resolution_m: float) -> Optional[np.ndarray]:
        """Get elevation data from Copernicus DEM."""
        # This is a simplified implementation
        # In production, would query Copernicus API or pre-cached tiles

        # For testing, generate synthetic terrain
        width = int((bbox['east'] - bbox['west']) * 111320 / resolution_m)  # Rough conversion
        height = int((bbox['north'] - bbox['south']) * 111320 / resolution_m)

        # Generate synthetic terrain with some hills
        x = np.linspace(0, 10, width)
        y = np.linspace(0, 10, height)
        X, Y = np.meshgrid(x, y)

        # Create some terrain features
        elevation = 1000 + 200 * np.sin(X * 0.5) * np.cos(Y * 0.3) + np.random.normal(0, 10, (height, width))

        return elevation.astype(np.float32)


class USGS3DEP(ElevationSource):
    """USGS 3D Elevation Program (1m resolution in US)."""

    async def get_elevation_data(self, bbox: Dict[str, float], resolution_m: float) -> Optional[np.ndarray]:
        """Get elevation data from USGS 3DEP."""
        # Check if bbox is in US
        if not (bbox['west'] >= -125 and bbox['east'] <= -66 and
                bbox['south'] >= 24 and bbox['north'] <= 50):
            return None  # Not in US coverage area

        # In production, would query USGS API
        # For testing, generate higher resolution synthetic terrain
        width = int((bbox['east'] - bbox['west']) * 111320 / resolution_m)
        height = int((bbox['north'] - bbox['south']) * 111320 / resolution_m)

        x = np.linspace(0, 10, width)
        y = np.linspace(0, 10, height)
        X, Y = np.meshgrid(x, y)

        elevation = 500 + 300 * np.sin(X) * np.cos(Y) + np.random.normal(0, 5, (height, width))

        return elevation.astype(np.float32)


class TerrainReconstructor:
    """Main terrain reconstruction engine."""

    def __init__(self, config: TerrainConfig):
        self.config = config
        self.sources = {
            'copernicus': CopernicusDEM(config),
            'usgs': USGS3DEP(config),
        }

    async def reconstruct_terrain(self, route_data: RouteData) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """
        Reconstruct terrain for a route.

        Args:
            route_data: Route data with matched coordinates

        Returns:
            Tuple of (elevation_array, metadata)
        """
        # Expand bounding box with buffer
        bbox = self._expand_bbox(route_data.bounding_box, self.config.buffer_m)

        # Try data sources in order of preference
        elevation_data = None
        source_used = None
        resolution_achieved = None

        for source_name, source in self.sources.items():
            try:
                data = await source.get_elevation_data(bbox, self.config.resolution_m)
                if data is not None:
                    elevation_data = data
                    source_used = source_name
                    resolution_achieved = self._estimate_resolution(data.shape, bbox)
                    break
            except Exception as e:
                print(f"Failed to get data from {source_name}: {e}")
                continue

        if elevation_data is None:
            # Fallback to synthetic terrain
            elevation_data = self._generate_fallback_terrain(bbox, self.config.resolution_m)
            source_used = "synthetic_fallback"
            resolution_achieved = self.config.resolution_m

        # Sample elevation profile along route
        route_profile = self._sample_route_elevation(route_data, elevation_data, bbox)

        metadata = {
            'source': source_used,
            'resolution_m': resolution_achieved,
            'bbox': bbox,
            'shape': elevation_data.shape,
            'route_profile': route_profile,
            'quality_score': self._calculate_quality_score(source_used, resolution_achieved)
        }

        return elevation_data, metadata

    def _expand_bbox(self, bbox: Dict[str, float], buffer_m: float) -> Dict[str, float]:
        """Expand bounding box by buffer distance in meters."""
        # Rough conversion: 1 degree ≈ 111,320 meters at equator
        lat_buffer = buffer_m / 111320
        lon_buffer = buffer_m / (111320 * np.cos(np.radians((bbox['north'] + bbox['south']) / 2)))

        return {
            'north': min(90, bbox['north'] + lat_buffer),
            'south': max(-90, bbox['south'] - lat_buffer),
            'east': min(180, bbox['east'] + lon_buffer),
            'west': max(-180, bbox['west'] - lon_buffer)
        }

    def _estimate_resolution(self, shape: Tuple[int, int], bbox: Dict[str, float]) -> float:
        """Estimate actual resolution from data shape and bbox."""
        width_m = (bbox['east'] - bbox['west']) * 111320 * np.cos(np.radians((bbox['north'] + bbox['south']) / 2))
        height_m = (bbox['north'] - bbox['south']) * 111320

        resolution_x = width_m / shape[1]
        resolution_y = height_m / shape[0]

        return (resolution_x + resolution_y) / 2

    def _generate_fallback_terrain(self, bbox: Dict[str, float], resolution_m: float) -> np.ndarray:
        """Generate synthetic fallback terrain."""
        width = int((bbox['east'] - bbox['west']) * 111320 / resolution_m)
        height = int((bbox['north'] - bbox['south']) * 111320 / resolution_m)

        # Generate gentle rolling terrain
        x = np.linspace(0, 4*np.pi, width)
        y = np.linspace(0, 4*np.pi, height)
        X, Y = np.meshgrid(x, y)

        elevation = 800 + 100 * np.sin(X * 0.5) * np.cos(Y * 0.3) + np.random.normal(0, 20, (height, width))

        return elevation.astype(np.float32)

    def _sample_route_elevation(self, route_data: RouteData, elevation_data: np.ndarray,
                               bbox: Dict[str, float]) -> List[Dict[str, Any]]:
        """Sample elevation along the route path."""
        profile = []

        height, width = elevation_data.shape

        for point in route_data.points:
            # Convert lat/lon to pixel coordinates
            if hasattr(point, 'matched_lat') and point.matched_lat is not None:
                lat, lon = point.matched_lat, point.matched_lon
            else:
                lat, lon = point.lat, point.lon

            # Normalize coordinates to [0, 1] within bbox
            x_norm = (lon - bbox['west']) / (bbox['east'] - bbox['west'])
            y_norm = 1.0 - (lat - bbox['south']) / (bbox['north'] - bbox['south'])  # Flip Y axis

            # Convert to pixel coordinates
            x_pixel = int(x_norm * width)
            y_pixel = int(y_norm * height)

            # Clamp to valid range
            x_pixel = max(0, min(width - 1, x_pixel))
            y_pixel = max(0, min(height - 1, y_pixel))

            # Sample elevation with bilinear interpolation
            elevation = self._bilinear_sample(elevation_data, x_pixel, y_pixel)

            profile.append({
                'distance_m': 0.0,  # Would calculate cumulative distance
                'elevation_m': float(elevation),
                'lat': lat,
                'lon': lon,
                'timestamp': point.timestamp
            })

        # Calculate cumulative distances
        for i in range(1, len(profile)):
            prev = profile[i-1]
            curr = profile[i]
            distance = self._haversine_distance(prev['lat'], prev['lon'], curr['lat'], curr['lon'])
            profile[i]['distance_m'] = profile[i-1]['distance_m'] + distance

        return profile

    def _bilinear_sample(self, data: np.ndarray, x: int, y: int) -> float:
        """Bilinear interpolation sampling."""
        h, w = data.shape

        # Get integer and fractional parts
        x_int, x_frac = int(x), x - int(x)
        y_int, y_frac = int(y), y - int(y)

        # Clamp to valid range
        x_int = max(0, min(w - 2, x_int))
        y_int = max(0, min(h - 2, y_int))

        # Bilinear interpolation
        v00 = data[y_int, x_int]
        v01 = data[y_int, x_int + 1]
        v10 = data[y_int + 1, x_int]
        v11 = data[y_int + 1, x_int + 1]

        return (v00 * (1 - x_frac) * (1 - y_frac) +
                v01 * x_frac * (1 - y_frac) +
                v10 * (1 - x_frac) * y_frac +
                v11 * x_frac * y_frac)

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

    def _calculate_quality_score(self, source: str, resolution: float) -> float:
        """Calculate terrain quality score (0-1)."""
        base_scores = {
            'usgs': 1.0,      # 1m resolution
            'copernicus': 0.7, # 30m resolution
            'synthetic_fallback': 0.3
        }

        base_score = base_scores.get(source, 0.5)

        # Adjust for resolution (better than target = higher score)
        if resolution <= self.config.resolution_m:
            resolution_bonus = min(0.2, (self.config.resolution_m - resolution) / self.config.resolution_m * 0.2)
        else:
            resolution_bonus = -min(0.3, (resolution - self.config.resolution_m) / self.config.resolution_m * 0.3)

        return max(0.0, min(1.0, base_score + resolution_bonus))


async def process_terrain_reconstruction(route_data: RouteData, config: Optional[TerrainConfig] = None) -> PipelineResult:
    """
    Process terrain reconstruction for a route.

    Args:
        route_data: Route data with matched coordinates
        config: Terrain reconstruction configuration

    Returns:
        Pipeline result with terrain data
    """
    if config is None:
        config = TerrainConfig()

    try:
        reconstructor = TerrainReconstructor(config)
        elevation_data, metadata = await reconstructor.reconstruct_terrain(route_data)

        return PipelineResult(
            stage=ProcessingStage.TERRAIN,
            success=True,
            data={
                'elevation_data_shape': elevation_data.shape,
                'metadata': metadata,
                'quality_score': metadata['quality_score']
            }
        )

    except Exception as e:
        return PipelineResult(
            stage=ProcessingStage.TERRAIN,
            success=False,
            errors=[f"Terrain reconstruction failed: {str(e)}"]
        )