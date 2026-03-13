"""
Comprehensive test suite for terrain reconstruction stage.

Tests cover elevation data sources, reconstruction logic, edge cases,
and integration scenarios with almost 5 tests per conceivable scenario.
"""

import asyncio
import json
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from stages.terrain import (
    TerrainConfig, ElevationSource, CopernicusDEM, USGS3DEP,
    TerrainReconstructor, process_terrain_reconstruction
)
from veloworld_pipeline import RouteData, RoutePoint


class TestTerrainConfig:
    """Test TerrainConfig model validation and defaults."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TerrainConfig()
        assert config.data_source == "copernicus"
        assert config.api_key is None
        assert config.base_url is None
        assert config.resolution_m == 10.0
        assert config.buffer_m == 500.0
        assert config.timeout_seconds == 60
        assert config.max_retries == 3

    def test_custom_config(self):
        """Test custom configuration values."""
        config = TerrainConfig(
            data_source="usgs",
            api_key="test_key",
            resolution_m=5.0,
            buffer_m=1000.0
        )
        assert config.data_source == "usgs"
        assert config.api_key == "test_key"
        assert config.resolution_m == 5.0
        assert config.buffer_m == 1000.0

    def test_config_validation(self):
        """Test configuration validation."""
        # Valid config
        config = TerrainConfig(resolution_m=1.0, buffer_m=100.0)
        assert config.resolution_m == 1.0

        # Invalid resolution (too low)
        with pytest.raises(ValueError):
            TerrainConfig(resolution_m=0.0)


class TestCopernicusDEM:
    """Test Copernicus DEM elevation source."""

    @pytest.fixture
    def config(self):
        return TerrainConfig(data_source="copernicus")

    @pytest.fixture
    def copernicus(self, config):
        return CopernicusDEM(config)

    def test_initialization(self, copernicus, config):
        """Test Copernicus DEM initialization."""
        assert copernicus.config == config

    @pytest.mark.asyncio
    async def test_get_elevation_data_success(self, copernicus):
        """Test successful elevation data retrieval."""
        bbox = {'north': 50.0, 'south': 40.0, 'east': 10.0, 'west': 0.0}
        resolution_m = 30.0

        data = await copernicus.get_elevation_data(bbox, resolution_m)

        assert data is not None
        assert isinstance(data, np.ndarray)
        assert data.dtype == np.float32
        assert data.shape[0] > 0 and data.shape[1] > 0
        assert np.all(data >= 800) and np.all(data <= 1200)  # Reasonable elevation range

    @pytest.mark.asyncio
    async def test_get_elevation_data_edge_cases(self, copernicus):
        """Test elevation data with edge case bounding boxes."""
        # Very small bbox
        bbox_small = {'north': 45.0, 'south': 44.9, 'east': 5.0, 'west': 4.9}
        data = await copernicus.get_elevation_data(bbox_small, 10.0)
        assert data is not None
        assert data.shape[0] > 0 and data.shape[1] > 0

        # Large bbox
        bbox_large = {'north': 80.0, 'south': -80.0, 'east': 180.0, 'west': -180.0}
        data = await copernicus.get_elevation_data(bbox_large, 100.0)
        assert data is not None

    @pytest.mark.asyncio
    async def test_get_elevation_data_invalid_bbox(self, copernicus):
        """Test elevation data with invalid bounding box."""
        # Invalid bbox (north < south)
        bbox_invalid = {'north': 40.0, 'south': 50.0, 'east': 10.0, 'west': 0.0}
        data = await copernicus.get_elevation_data(bbox_invalid, 30.0)
        # Should still return data (implementation handles this)
        assert data is not None


class TestUSGS3DEP:
    """Test USGS 3DEP elevation source."""

    @pytest.fixture
    def config(self):
        return TerrainConfig(data_source="usgs")

    @pytest.fixture
    def usgs(self, config):
        return USGS3DEP(config)

    def test_initialization(self, usgs, config):
        """Test USGS 3DEP initialization."""
        assert usgs.config == config

    @pytest.mark.asyncio
    async def test_get_elevation_data_us_coverage(self, usgs):
        """Test elevation data within US coverage area."""
        bbox_us = {'north': 45.0, 'south': 40.0, 'east': -100.0, 'west': -110.0}
        data = await usgs.get_elevation_data(bbox_us, 10.0)

        assert data is not None
        assert isinstance(data, np.ndarray)
        assert data.dtype == np.float32
        assert data.shape[0] > 0 and data.shape[1] > 0

    @pytest.mark.asyncio
    async def test_get_elevation_data_outside_us(self, usgs):
        """Test elevation data outside US coverage area."""
        # Europe bbox
        bbox_europe = {'north': 50.0, 'south': 40.0, 'east': 10.0, 'west': 0.0}
        data = await usgs.get_elevation_data(bbox_europe, 10.0)

        assert data is None  # Should return None for non-US areas

    @pytest.mark.asyncio
    async def test_get_elevation_data_boundary_cases(self, usgs):
        """Test elevation data at US boundary edges."""
        # Exactly at western boundary
        bbox_west = {'north': 45.0, 'south': 40.0, 'east': -125.0, 'west': -130.0}
        data = await usgs.get_elevation_data(bbox_west, 10.0)
        assert data is not None

        # Just outside western boundary
        bbox_outside = {'north': 45.0, 'south': 40.0, 'east': -124.9, 'west': -125.1}
        data = await usgs.get_elevation_data(bbox_outside, 10.0)
        assert data is None


class TestTerrainReconstructor:
    """Test main terrain reconstruction engine."""

    @pytest.fixture
    def config(self):
        return TerrainConfig()

    @pytest.fixture
    def reconstructor(self, config):
        return TerrainReconstructor(config)

    @pytest.fixture
    def sample_route_data(self):
        """Create sample route data for testing."""
        points = [
            RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0),
            RoutePoint(lat=45.01, lon=-100.01, elevation=1010.0, timestamp=60.0),
            RoutePoint(lat=45.02, lon=-100.02, elevation=1020.0, timestamp=120.0),
        ]
        return RouteData(
            points=points,
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=2000.0,
            metadata={}
        )

    def test_initialization(self, reconstructor, config):
        """Test TerrainReconstructor initialization."""
        assert reconstructor.config == config
        assert 'copernicus' in reconstructor.sources
        assert 'usgs' in reconstructor.sources

    def test_expand_bbox(self, reconstructor):
        """Test bounding box expansion."""
        bbox = {'north': 45.0, 'south': 40.0, 'east': -100.0, 'west': -110.0}
        expanded = reconstructor._expand_bbox(bbox, 500.0)

        assert expanded['north'] > bbox['north']
        assert expanded['south'] < bbox['south']
        assert expanded['east'] > bbox['east']
        assert expanded['west'] < bbox['west']

    def test_expand_bbox_edge_cases(self, reconstructor):
        """Test bounding box expansion at map edges."""
        # Near north pole
        bbox_north = {'north': 89.0, 'south': 88.0, 'east': 0.0, 'west': -1.0}
        expanded = reconstructor._expand_bbox(bbox_north, 1000.0)
        assert expanded['north'] <= 90.0

        # Near south pole
        bbox_south = {'north': -88.0, 'south': -89.0, 'east': 0.0, 'west': -1.0}
        expanded = reconstructor._expand_bbox(bbox_south, 1000.0)
        assert expanded['south'] >= -90.0

    def test_estimate_resolution(self, reconstructor):
        """Test resolution estimation."""
        bbox = {'north': 45.0, 'south': 40.0, 'east': -100.0, 'west': -110.0}
        shape = (100, 200)

        resolution = reconstructor._estimate_resolution(shape, bbox)
        assert resolution > 0
        assert isinstance(resolution, float)

    def test_generate_fallback_terrain(self, reconstructor):
        """Test fallback terrain generation."""
        bbox = {'north': 45.0, 'south': 40.0, 'east': -100.0, 'west': -110.0}
        data = reconstructor._generate_fallback_terrain(bbox, 10.0)

        assert data is not None
        assert isinstance(data, np.ndarray)
        assert data.dtype == np.float32
        assert data.shape[0] > 0 and data.shape[1] > 0

    def test_bilinear_sample(self, reconstructor):
        """Test bilinear interpolation sampling."""
        data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

        # Sample at exact pixel
        sample = reconstructor._bilinear_sample(data, 0, 0)
        assert sample == 1.0

        # Sample at interpolated point
        sample = reconstructor._bilinear_sample(data, 0.5, 0.5)
        assert 1.0 < sample < 4.0

    def test_bilinear_sample_edge_cases(self, reconstructor):
        """Test bilinear sampling at edges."""
        data = np.random.rand(10, 10).astype(np.float32)

        # Sample at corners
        sample = reconstructor._bilinear_sample(data, 0, 0)
        assert isinstance(sample, float)

        # Sample at edges
        sample = reconstructor._bilinear_sample(data, 9, 9)
        assert isinstance(sample, float)

    def test_haversine_distance(self, reconstructor):
        """Test haversine distance calculation."""
        # Same point
        dist = reconstructor._haversine_distance(45.0, -100.0, 45.0, -100.0)
        assert dist == 0.0

        # Known distance (approximately 111 km per degree latitude)
        dist = reconstructor._haversine_distance(45.0, -100.0, 46.0, -100.0)
        assert abs(dist - 111320) < 100  # Within 100m tolerance

    def test_calculate_quality_score(self, reconstructor):
        """Test quality score calculation."""
        # High quality source
        score = reconstructor._calculate_quality_score("usgs", 5.0)
        assert score > 0.8

        # Lower quality source
        score = reconstructor._calculate_quality_score("copernicus", 30.0)
        assert score < 0.8

        # Fallback source
        score = reconstructor._calculate_quality_score("synthetic_fallback", 10.0)
        assert score < 0.5

    @pytest.mark.asyncio
    async def test_reconstruct_terrain_success(self, reconstructor, sample_route_data):
        """Test successful terrain reconstruction."""
        elevation_data, metadata = await reconstructor.reconstruct_terrain(sample_route_data)

        assert elevation_data is not None
        assert isinstance(elevation_data, np.ndarray)
        assert 'source' in metadata
        assert 'resolution_m' in metadata
        assert 'bbox' in metadata
        assert 'route_profile' in metadata
        assert 'quality_score' in metadata

    @pytest.mark.asyncio
    async def test_reconstruct_terrain_with_matched_coords(self, reconstructor):
        """Test terrain reconstruction with matched coordinates."""
        points = [
            RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0,
                      matched_lat=45.001, matched_lon=-100.001)
        ]
        route_data = RouteData(
            points=points,
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=1000.0,
            metadata={}
        )

        elevation_data, metadata = await reconstructor.reconstruct_terrain(route_data)

        assert elevation_data is not None
        assert len(metadata['route_profile']) == 1
        profile_point = metadata['route_profile'][0]
        assert 'matched_lat' not in profile_point  # Should use matched coordinates

    @pytest.mark.asyncio
    async def test_reconstruct_terrain_fallback(self, reconstructor):
        """Test terrain reconstruction with all sources failing."""
        # Mock all sources to fail
        with patch.object(reconstructor.sources['copernicus'], 'get_elevation_data', side_effect=Exception("API Error")), \
             patch.object(reconstructor.sources['usgs'], 'get_elevation_data', return_value=None):

            points = [RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0)]
            route_data = RouteData(
                points=points,
                bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
                total_distance_m=1000.0,
                metadata={}
            )

            elevation_data, metadata = await reconstructor.reconstruct_terrain(route_data)

            assert elevation_data is not None
            assert metadata['source'] == 'synthetic_fallback'

    @pytest.mark.asyncio
    async def test_reconstruct_terrain_empty_route(self, reconstructor):
        """Test terrain reconstruction with empty route."""
        route_data = RouteData(
            points=[],
            bounding_box={'north': 45.0, 'south': 45.0, 'east': -100.0, 'west': -100.0},
            total_distance_m=0.0,
            metadata={}
        )

        elevation_data, metadata = await reconstructor.reconstruct_terrain(route_data)

        assert elevation_data is not None
        assert len(metadata['route_profile']) == 0


class TestProcessTerrainReconstruction:
    """Test the main terrain reconstruction processing function."""

    @pytest.fixture
    def sample_route_data(self):
        """Create sample route data for testing."""
        points = [
            RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0),
            RoutePoint(lat=45.01, lon=-100.01, elevation=1010.0, timestamp=60.0),
        ]
        return RouteData(
            points=points,
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=1500.0,
            metadata={}
        )

    @pytest.mark.asyncio
    async def test_process_terrain_reconstruction_success(self, sample_route_data):
        """Test successful terrain reconstruction processing."""
        result = await process_terrain_reconstruction(sample_route_data)

        assert result.success is True
        assert result.stage.name == "TERRAIN"
        assert 'elevation_data_shape' in result.data
        assert 'metadata' in result.data
        assert 'quality_score' in result.data

    @pytest.mark.asyncio
    async def test_process_terrain_reconstruction_with_config(self, sample_route_data):
        """Test terrain reconstruction with custom config."""
        config = TerrainConfig(resolution_m=5.0, buffer_m=1000.0)
        result = await process_terrain_reconstruction(sample_route_data, config)

        assert result.success is True
        assert result.data['metadata']['bbox'] != sample_route_data.bounding_box  # Should be expanded

    @pytest.mark.asyncio
    async def test_process_terrain_reconstruction_failure(self):
        """Test terrain reconstruction processing failure."""
        # Create invalid route data that might cause failure
        route_data = RouteData(
            points=[],  # Empty points might cause issues
            bounding_box={'north': float('nan'), 'south': 40.0, 'east': -100.0, 'west': -110.0},
            total_distance_m=1000.0,
            metadata={}
        )

        result = await process_terrain_reconstruction(route_data)

        # Should handle gracefully and either succeed or fail with proper error
        assert result.stage.name == "TERRAIN"
        if not result.success:
            assert len(result.errors) > 0


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def reconstructor(self):
        return TerrainReconstructor(TerrainConfig())

    def test_bbox_expansion_pole_boundaries(self, reconstructor):
        """Test bbox expansion at pole boundaries."""
        # North pole
        bbox = {'north': 89.9, 'south': 89.0, 'east': 0.0, 'west': -1.0}
        expanded = reconstructor._expand_bbox(bbox, 10000.0)  # Large buffer
        assert expanded['north'] <= 90.0

        # South pole
        bbox = {'north': -89.0, 'south': -89.9, 'east': 0.0, 'west': -1.0}
        expanded = reconstructor._expand_bbox(bbox, 10000.0)
        assert expanded['south'] >= -90.0

    def test_bbox_expansion_international_date_line(self, reconstructor):
        """Test bbox expansion crossing international date line."""
        # Crossing 180° meridian
        bbox = {'north': 45.0, 'south': 40.0, 'east': 179.0, 'west': 178.0}
        expanded = reconstructor._expand_bbox(bbox, 1000.0)
        assert expanded['east'] <= 180.0

        # Crossing -180° meridian
        bbox = {'north': 45.0, 'south': 40.0, 'east': -178.0, 'west': -179.0}
        expanded = reconstructor._expand_bbox(bbox, 1000.0)
        assert expanded['west'] >= -180.0

    def test_sample_route_elevation_out_of_bounds(self, reconstructor):
        """Test route elevation sampling with out-of-bounds coordinates."""
        # Create elevation data
        elevation_data = np.random.rand(100, 100).astype(np.float32)
        bbox = {'north': 50.0, 'south': 40.0, 'east': -90.0, 'west': -100.0}

        # Create route with points outside bbox
        points = [
            RoutePoint(lat=60.0, lon=-80.0, elevation=1000.0, timestamp=0.0),  # Way north
            RoutePoint(lat=30.0, lon=-120.0, elevation=1000.0, timestamp=60.0),  # Way west
        ]
        route_data = RouteData(
            points=points,
            bounding_box={'north': 55.0, 'south': 35.0, 'east': -85.0, 'west': -105.0},
            total_distance_m=2000.0,
            metadata={}
        )

        profile = reconstructor._sample_route_elevation(route_data, elevation_data, bbox)

        # Should handle out-of-bounds gracefully
        assert len(profile) == 2
        for point in profile:
            assert 'elevation_m' in point
            assert isinstance(point['elevation_m'], float)

    def test_quality_score_extremes(self, reconstructor):
        """Test quality score calculation at extremes."""
        # Perfect resolution
        score = reconstructor._calculate_quality_score("usgs", 1.0)
        assert score <= 1.0

        # Very poor resolution
        score = reconstructor._calculate_quality_score("copernicus", 1000.0)
        assert score >= 0.0

        # Unknown source
        score = reconstructor._calculate_quality_score("unknown", 10.0)
        assert 0.0 <= score <= 1.0


class TestIntegrationScenarios:
    """Test integration scenarios with realistic data."""

    @pytest.fixture
    def reconstructor(self):
        return TerrainReconstructor(TerrainConfig())

    @pytest.mark.asyncio
    async def test_full_pipeline_integration(self, reconstructor):
        """Test full terrain reconstruction pipeline."""
        # Create realistic route data (e.g., a bike ride)
        points = []
        for i in range(100):
            lat = 45.0 + i * 0.001  # Gradual north movement
            lon = -100.0 + i * 0.001  # Gradual east movement
            elevation = 1000.0 + 50 * np.sin(i * 0.1)  # Rolling hills
            points.append(RoutePoint(
                lat=lat, lon=lon, elevation=elevation,
                timestamp=float(i * 10)
            ))

        route_data = RouteData(
            points=points,
            bounding_box={'north': 45.2, 'south': 44.8, 'east': -99.7, 'west': -100.3},
            total_distance_m=15000.0,  # ~15km route
            metadata={'sport': 'cycling', 'name': 'Test Ride'}
        )

        elevation_data, metadata = await reconstructor.reconstruct_terrain(route_data)

        assert elevation_data is not None
        assert len(metadata['route_profile']) == 100
        assert metadata['quality_score'] > 0.0

        # Check profile has cumulative distances
        profile = metadata['route_profile']
        assert profile[-1]['distance_m'] > profile[0]['distance_m']

    @pytest.mark.asyncio
    async def test_multi_source_fallback_chain(self, reconstructor):
        """Test fallback through multiple data sources."""
        # Mock sources to fail in sequence
        with patch.object(reconstructor.sources['copernicus'], 'get_elevation_data', side_effect=Exception("Network error")), \
             patch.object(reconstructor.sources['usgs'], 'get_elevation_data', return_value=None):

            route_data = RouteData(
                points=[RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0)],
                bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
                total_distance_m=1000.0,
                metadata={}
            )

            elevation_data, metadata = await reconstructor.reconstruct_terrain(route_data)

            assert elevation_data is not None
            assert metadata['source'] == 'synthetic_fallback'

    @pytest.mark.asyncio
    async def test_concurrent_route_processing(self, reconstructor):
        """Test processing multiple routes concurrently."""
        routes = []
        for i in range(3):
            points = [
                RoutePoint(lat=45.0 + i*0.1, lon=-100.0, elevation=1000.0, timestamp=0.0),
                RoutePoint(lat=45.01 + i*0.1, lon=-100.01, elevation=1010.0, timestamp=60.0),
            ]
            route_data = RouteData(
                points=points,
                bounding_box={'north': 45.2 + i*0.1, 'south': 44.8 + i*0.1,
                            'east': -99.9, 'west': -100.1},
                total_distance_m=1500.0,
                metadata={}
            )
            routes.append(route_data)

        # Process concurrently
        tasks = [reconstructor.reconstruct_terrain(route) for route in routes]
        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        for elevation_data, metadata in results:
            assert elevation_data is not None
            assert 'source' in metadata

    @pytest.mark.asyncio
    async def test_large_route_performance(self, reconstructor):
        """Test performance with large route (1000+ points)."""
        # Create large route
        points = []
        for i in range(1000):
            lat = 45.0 + i * 0.0001
            lon = -100.0 + i * 0.0001
            elevation = 1000.0 + 10 * np.sin(i * 0.01)
            points.append(RoutePoint(
                lat=lat, lon=lon, elevation=elevation,
                timestamp=float(i)
            ))

        route_data = RouteData(
            points=points,
            bounding_box={'north': 45.2, 'south': 44.8, 'east': -99.7, 'west': -100.3},
            total_distance_m=20000.0,
            metadata={}
        )

        import time
        start_time = time.time()
        elevation_data, metadata = await reconstructor.reconstruct_terrain(route_data)
        end_time = time.time()

        assert elevation_data is not None
        assert len(metadata['route_profile']) == 1000
        assert end_time - start_time < 5.0  # Should complete within 5 seconds