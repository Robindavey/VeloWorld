"""
Comprehensive tests for map matching stage.

Tests cover various map matching services, error handling, and edge cases.
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import aiohttp
import pytest

from stages.map_matching import (
    MapMatcher, MapMatchingConfig, process_map_matching
)
from veloworld_pipeline import RouteData, RoutePoint


class TestMapMatchingConfig:
    """Test MapMatchingConfig validation."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MapMatchingConfig()
        assert config.service == "valhalla"
        assert config.timeout_seconds == 30
        assert config.max_points_per_request == 100

    def test_custom_config(self):
        """Test custom configuration."""
        config = MapMatchingConfig(
            service="mapbox",
            api_key="test_key",
            timeout_seconds=60,
            max_points_per_request=50
        )
        assert config.service == "mapbox"
        assert config.api_key == "test_key"
        assert config.timeout_seconds == 60
        assert config.max_points_per_request == 50


class TestMapMatcher:
    """Test MapMatcher class."""

    @pytest.fixture
    async def matcher(self):
        """Create a test matcher instance."""
        config = MapMatchingConfig(service="mock")
        async with MapMatcher(config) as matcher:
            yield matcher

    def test_chunk_route_small(self, matcher):
        """Test chunking a small route."""
        points = [RoutePoint(lat=45.0 + i*0.001, lon=6.0 + i*0.001) for i in range(50)]
        chunks = matcher._chunk_route(points)
        assert len(chunks) == 1
        assert len(chunks[0]) == 50

    def test_chunk_route_large(self, matcher):
        """Test chunking a large route."""
        matcher.config.max_points_per_request = 50
        points = [RoutePoint(lat=45.0 + i*0.001, lon=6.0 + i*0.001) for i in range(150)]
        chunks = matcher._chunk_route(points)
        assert len(chunks) == 3
        assert len(chunks[0]) == 50
        assert len(chunks[1]) == 50
        assert len(chunks[2]) == 50

    def test_chunk_route_exact_multiple(self, matcher):
        """Test chunking when route length is exact multiple of chunk size."""
        matcher.config.max_points_per_request = 50
        points = [RoutePoint(lat=45.0 + i*0.001, lon=6.0 + i*0.001) for i in range(100)]
        chunks = matcher._chunk_route(points)
        assert len(chunks) == 2
        assert len(chunks[0]) == 50
        assert len(chunks[1]) == 50

    @patch('aiohttp.ClientSession.post')
    async def test_match_with_valhalla_success(self, mock_post):
        """Test successful Valhalla map matching."""
        # Mock response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "trip": {
                "legs": [{
                    "shape": "test_shape",
                    "road_type": "secondary",
                    "surface": "asphalt",
                    "speed_limit": 50
                }]
            }
        })
        mock_post.return_value.__aenter__.return_value = mock_response

        config = MapMatchingConfig(service="valhalla")
        async with MapMatcher(config) as matcher:
            points = [RoutePoint(lat=45.0, lon=6.0)]
            result = await matcher._match_with_valhalla(points)

            assert len(result) > 0
            mock_post.assert_called_once()

    @patch('aiohttp.ClientSession.post')
    async def test_match_with_valhalla_api_error(self, mock_post):
        """Test Valhalla API error handling."""
        mock_response = Mock()
        mock_response.status = 500
        mock_post.return_value.__aenter__.return_value = mock_response

        config = MapMatchingConfig(service="valhalla")
        async with MapMatcher(config) as matcher:
            points = [RoutePoint(lat=45.0, lon=6.0)]

            with pytest.raises(Exception, match="Valhalla API error"):
                await matcher._match_with_valhalla(points)

    @patch('aiohttp.ClientSession.get')
    async def test_match_with_mapbox_success(self, mock_get):
        """Test successful Mapbox map matching."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "matchings": [{
                "geometry": {
                    "coordinates": [[6.0, 45.0], [6.001, 45.001]]
                }
            }]
        })
        mock_get.return_value.__aenter__.return_value = mock_response

        config = MapMatchingConfig(service="mapbox", api_key="test_key")
        async with MapMatcher(config) as matcher:
            points = [RoutePoint(lat=45.0, lon=6.0), RoutePoint(lat=45.001, lon=6.001)]
            result = await matcher._match_with_mapbox(points)

            assert len(result) == 2
            mock_get.assert_called_once()

    async def test_match_with_mapbox_no_api_key(self):
        """Test Mapbox matching without API key."""
        config = MapMatchingConfig(service="mapbox")
        async with MapMatcher(config) as matcher:
            points = [RoutePoint(lat=45.0, lon=6.0)]

            with pytest.raises(ValueError, match="Mapbox API key required"):
                await matcher._match_with_mapbox(points)

    @patch('aiohttp.ClientSession.get')
    async def test_match_with_osrm_success(self, mock_get):
        """Test successful OSRM route matching."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "routes": [{
                "geometry": {
                    "coordinates": [[6.0, 45.0], [6.001, 45.001]]
                }
            }]
        })
        mock_get.return_value.__aenter__.return_value = mock_response

        config = MapMatchingConfig(service="osrm")
        async with MapMatcher(config) as matcher:
            points = [RoutePoint(lat=45.0, lon=6.0), RoutePoint(lat=45.001, lon=6.001)]
            result = await matcher._match_with_osrm(points)

            assert len(result) == 2
            mock_get.assert_called_once()

    async def test_unsupported_service(self):
        """Test unsupported map matching service."""
        config = MapMatchingConfig(service="unsupported")
        async with MapMatcher(config) as matcher:
            points = [RoutePoint(lat=45.0, lon=6.0)]

            with pytest.raises(ValueError, match="Unsupported map matching service"):
                await matcher._match_chunk(points)

    def test_validate_matched_route_no_points(self, matcher):
        """Test validation with no matched points."""
        warnings = matcher._validate_matched_route([])
        assert "No matched points returned" in warnings

    def test_validate_matched_route_large_jumps(self, matcher):
        """Test validation with large jumps in matched route."""
        points = [
            RoutePoint(matched_lat=45.0, matched_lon=6.0),
            RoutePoint(matched_lat=45.1, matched_lon=6.1),  # Large jump
        ]
        warnings = matcher._validate_matched_route(points)
        assert any("Large jump" in w for w in warnings)

    def test_validate_matched_route_bad_roads(self, matcher):
        """Test validation with points not on drivable roads."""
        points = [
            RoutePoint(road_type="path"),
            RoutePoint(road_type="footway"),
        ]
        warnings = matcher._validate_matched_route(points)
        assert any("may not be on drivable roads" in w for w in warnings)

    def test_validate_matched_route_good_roads(self, matcher):
        """Test validation with points on good roads."""
        points = [
            RoutePoint(road_type="primary"),
            RoutePoint(road_type="secondary"),
        ]
        warnings = matcher._validate_matched_route(points)
        assert not any("may not be on drivable roads" in w for w in warnings)

    def test_ensure_chunk_continuity(self, matcher):
        """Test chunk continuity (basic implementation)."""
        points = [RoutePoint(lat=45.0, lon=6.0), RoutePoint(lat=45.001, lon=6.001)]
        result = matcher._ensure_chunk_continuity(points)
        assert len(result) == 2
        assert result == points

    def test_haversine_distance_calculation(self, matcher):
        """Test haversine distance calculation."""
        # Test zero distance
        dist = matcher._haversine_distance(45.0, 6.0, 45.0, 6.0)
        assert dist == 0

        # Test known distance (approximately 111km per degree latitude)
        dist = matcher._haversine_distance(0, 0, 1, 0)
        assert abs(dist - 111320) < 100  # Within 100m tolerance


class TestProcessMapMatching:
    """Test the main process_map_matching function."""

    @pytest.fixture
    def sample_route_data(self):
        """Create sample route data for testing."""
        route_id = uuid4()
        points = [
            RoutePoint(lat=45.0 + i*0.001, lon=6.0 + i*0.001)
            for i in range(10)
        ]

        return RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=1000.0,
            point_count=len(points),
            bounding_box={'north': 45.01, 'south': 45.0, 'east': 6.01, 'west': 6.0}
        )

    @pytest.mark.asyncio
    async def test_process_map_matching_mock_success(self, sample_route_data):
        """Test successful mock map matching."""
        config = MapMatchingConfig(service="mock")
        result = await process_map_matching(sample_route_data, config)

        assert result.success
        assert result.stage.name == "MAP_MATCHING"
        assert 'matched_route' in result.data
        assert 'matched_point_count' in result.data
        assert result.data['matched_point_count'] == 10
        assert 'warnings' in result.data
        assert any("mock map matching" in w.lower() for w in result.data['warnings'])

    @pytest.mark.asyncio
    async def test_process_map_matching_empty_route(self):
        """Test map matching with empty route."""
        route_id = uuid4()
        empty_route = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=[],
            total_distance_m=0.0,
            point_count=0,
            bounding_box={'north': 0, 'south': 0, 'east': 0, 'west': 0}
        )

        config = MapMatchingConfig(service="mock")
        result = await process_map_matching(empty_route, config)

        assert result.success
        assert result.data['matched_point_count'] == 0

    @pytest.mark.asyncio
    async def test_process_map_matching_default_config(self, sample_route_data):
        """Test map matching with default config."""
        result = await process_map_matching(sample_route_data)

        assert result.success
        assert result.stage.name == "MAP_MATCHING"

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_process_map_matching_valhalla_error(self, mock_post, sample_route_data):
        """Test map matching with Valhalla API error."""
        # Mock a network error
        mock_post.side_effect = aiohttp.ClientError("Network error")

        config = MapMatchingConfig(service="valhalla")
        result = await process_map_matching(sample_route_data, config)

        assert not result.success
        assert "Map matching failed" in str(result.errors)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_single_point_route(self):
        """Test map matching with single point route."""
        route_id = uuid4()
        single_point_route = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=[RoutePoint(lat=45.0, lon=6.0)],
            total_distance_m=0.0,
            point_count=1,
            bounding_box={'north': 45.0, 'south': 45.0, 'east': 6.0, 'west': 6.0}
        )

        config = MapMatchingConfig(service="mock")
        result = await process_map_matching(single_point_route, config)

        assert result.success
        assert result.data['matched_point_count'] == 1

    @pytest.mark.asyncio
    async def test_max_chunk_size_boundary(self):
        """Test chunking at maximum chunk size boundary."""
        route_id = uuid4()
        # Create exactly max_points_per_request points
        max_points = 100
        points = [
            RoutePoint(lat=45.0 + i*0.0001, lon=6.0 + i*0.0001)
            for i in range(max_points)
        ]

        route_data = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=1000.0,
            point_count=max_points,
            bounding_box={'north': 45.01, 'south': 45.0, 'east': 6.01, 'west': 6.0}
        )

        config = MapMatchingConfig(service="mock", max_points_per_request=max_points)
        result = await process_map_matching(route_data, config)

        assert result.success
        assert result.data['matched_point_count'] == max_points

    @pytest.mark.asyncio
    async def test_route_with_timestamps_and_elevation(self):
        """Test map matching preserves timestamps and elevation."""
        route_id = uuid4()
        points = [
            RoutePoint(
                lat=45.0,
                lon=6.0,
                timestamp="2024-01-01T10:00:00Z",
                raw_elevation=1000.0
            ),
            RoutePoint(
                lat=45.001,
                lon=6.001,
                timestamp="2024-01-01T10:01:00Z",
                raw_elevation=1005.0
            )
        ]

        route_data = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=150.0,
            point_count=2,
            bounding_box={'north': 45.001, 'south': 45.0, 'east': 6.001, 'west': 6.0}
        )

        config = MapMatchingConfig(service="mock")
        result = await process_map_matching(route_data, config)

        assert result.success
        matched_route = result.data['matched_route']
        assert len(matched_route['points']) == 2

        # Check that timestamps and elevations are preserved
        for i, point in enumerate(matched_route['points']):
            assert point['timestamp'] == points[i].timestamp
            assert point['raw_elevation'] == points[i].raw_elevation

    @pytest.mark.asyncio
    async def test_route_at_extreme_coordinates(self):
        """Test map matching with coordinates near valid boundaries."""
        route_id = uuid4()
        points = [
            RoutePoint(lat=89.999, lon=179.999),  # Near north pole, international date line
            RoutePoint(lat=-89.999, lon=-179.999),  # Near south pole, international date line
        ]

        route_data = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=20000000.0,  # Roughly antipodal distance
            point_count=2,
            bounding_box={'north': 89.999, 'south': -89.999, 'east': 179.999, 'west': -179.999}
        )

        config = MapMatchingConfig(service="mock")
        result = await process_map_matching(route_data, config)

        assert result.success
        assert result.data['matched_point_count'] == 2

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test timeout handling in map matching."""
        route_id = uuid4()
        points = [RoutePoint(lat=45.0 + i*0.001, lon=6.0 + i*0.001) for i in range(10)]

        route_data = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=1000.0,
            point_count=10,
            bounding_box={'north': 45.01, 'south': 45.0, 'east': 6.01, 'west': 6.0}
        )

        # Test with very short timeout
        config = MapMatchingConfig(service="mock", timeout_seconds=0)
        result = await process_map_matching(route_data, config)

        # Should still succeed with mock service
        assert result.success


class TestIntegrationScenarios:
    """Test integration scenarios and complex cases."""

    @pytest.mark.asyncio
    async def test_long_route_chunking(self):
        """Test processing of a long route that requires chunking."""
        route_id = uuid4()
        # Create a route with 250 points (more than default 100 max per request)
        num_points = 250
        points = [
            RoutePoint(lat=45.0 + i*0.0001, lon=6.0 + i*0.0001)
            for i in range(num_points)
        ]

        route_data = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=2500.0,
            point_count=num_points,
            bounding_box={'north': 45.025, 'south': 45.0, 'east': 6.025, 'west': 6.0}
        )

        config = MapMatchingConfig(service="mock", max_points_per_request=100)
        result = await process_map_matching(route_data, config)

        assert result.success
        assert result.data['matched_point_count'] == num_points

    @pytest.mark.asyncio
    async def test_route_with_gaps(self):
        """Test route with GPS gaps (sparse points)."""
        route_id = uuid4()
        # Create route with some large gaps
        points = [
            RoutePoint(lat=45.0, lon=6.0),
            RoutePoint(lat=45.01, lon=6.01),  # 1.5km gap
            RoutePoint(lat=45.0, lon=6.0),   # Back to start (loop)
        ]

        route_data = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=3000.0,
            point_count=3,
            bounding_box={'north': 45.01, 'south': 45.0, 'east': 6.01, 'west': 6.0}
        )

        config = MapMatchingConfig(service="mock")
        result = await process_map_matching(route_data, config)

        assert result.success
        assert result.data['matched_point_count'] == 3

    @pytest.mark.asyncio
    async def test_route_crossing_time_zones(self):
        """Test route crossing time zones with timestamps."""
        route_id = uuid4()
        points = [
            RoutePoint(
                lat=45.0,
                lon=6.0,  # Central Europe
                timestamp="2024-01-01T10:00:00+01:00"
            ),
            RoutePoint(
                lat=45.0,
                lon=15.0,  # Eastern Europe
                timestamp="2024-01-01T11:00:00+02:00"
            ),
        ]

        route_data = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=500000.0,  # ~500km
            point_count=2,
            bounding_box={'north': 45.0, 'south': 45.0, 'east': 15.0, 'west': 6.0}
        )

        config = MapMatchingConfig(service="mock")
        result = await process_map_matching(route_data, config)

        assert result.success
        # Timestamps should be preserved
        matched_points = result.data['matched_route']['points']
        assert matched_points[0]['timestamp'] == "2024-01-01T10:00:00+01:00"
        assert matched_points[1]['timestamp'] == "2024-01-01T11:00:00+02:00"