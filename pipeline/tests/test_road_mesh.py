"""
Comprehensive test suite for road mesh generation stage.

Tests cover geometry generation, physics calculations, edge cases,
and integration scenarios with almost 5 tests per conceivable scenario.
"""

import asyncio
import math
import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List, Tuple

from stages.road_mesh import (
    RoadMeshConfig, RoadGeometry, RoadMeshGenerator, process_road_mesh_generation
)
from veloworld_pipeline import RouteData, RoutePoint


class TestRoadMeshConfig:
    """Test RoadMeshConfig model validation and defaults."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RoadMeshConfig()
        assert config.road_width_m == 6.0
        assert config.lane_count == 2
        assert config.shoulder_width_m == 1.5
        assert config.resolution_m == 1.0
        assert config.banking_max_deg == 30.0
        assert config.superelevation_rate == 0.06
        assert config.texture_repeat_m == 10.0
        assert config.physics_friction == 0.8
        assert config.generate_normals is True
        assert config.generate_uvs is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = RoadMeshConfig(
            road_width_m=8.0,
            lane_count=4,
            physics_friction=0.9,
            banking_max_deg=45.0
        )
        assert config.road_width_m == 8.0
        assert config.lane_count == 4
        assert config.physics_friction == 0.9
        assert config.banking_max_deg == 45.0

    def test_config_validation(self):
        """Test configuration validation."""
        # Valid config
        config = RoadMeshConfig(road_width_m=4.0, resolution_m=0.5)
        assert config.road_width_m == 4.0

        # Invalid width
        with pytest.raises(ValueError):
            RoadMeshConfig(road_width_m=0.0)


class TestRoadGeometry:
    """Test RoadGeometry class functionality."""

    def test_initialization(self):
        """Test RoadGeometry initialization."""
        geometry = RoadGeometry()
        assert geometry.vertices == []
        assert geometry.normals == []
        assert geometry.uvs == []
        assert geometry.indices == []
        assert geometry.physics_properties == {}

    def test_add_vertex_basic(self):
        """Test adding vertex without normal/UV."""
        geometry = RoadGeometry()
        geometry.add_vertex(1.0, 2.0, 3.0)

        assert len(geometry.vertices) == 1
        assert geometry.vertices[0] == (1.0, 2.0, 3.0)
        assert len(geometry.normals) == 0
        assert len(geometry.uvs) == 0

    def test_add_vertex_with_normal_uv(self):
        """Test adding vertex with normal and UV."""
        geometry = RoadGeometry()
        geometry.add_vertex(1.0, 2.0, 3.0, (0, 0, 1), (0.5, 0.5))

        assert len(geometry.vertices) == 1
        assert geometry.vertices[0] == (1.0, 2.0, 3.0)
        assert geometry.normals[0] == (0, 0, 1)
        assert geometry.uvs[0] == (0.5, 0.5)

    def test_add_triangle(self):
        """Test adding triangles."""
        geometry = RoadGeometry()
        geometry.add_triangle(0, 1, 2)
        geometry.add_triangle(1, 2, 3)

        assert len(geometry.indices) == 2
        assert geometry.indices[0] == (0, 1, 2)
        assert geometry.indices[1] == (1, 2, 3)


class TestRoadMeshGenerator:
    """Test main road mesh generation engine."""

    @pytest.fixture
    def config(self):
        return RoadMeshConfig()

    @pytest.fixture
    def generator(self, config):
        return RoadMeshGenerator(config)

    @pytest.fixture
    def sample_route_data(self):
        """Create sample route data for testing."""
        points = [
            RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0),
            RoutePoint(lat=45.001, lon=-100.001, elevation=1010.0, timestamp=60.0),
            RoutePoint(lat=45.002, lon=-100.002, elevation=1020.0, timestamp=120.0),
        ]
        return RouteData(
            points=points,
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=2000.0,
            metadata={}
        )

    def test_initialization(self, generator, config):
        """Test RoadMeshGenerator initialization."""
        assert generator.config == config

    def test_latlon_to_local_conversion(self, generator):
        """Test lat/lon to local coordinate conversion."""
        lat, lon = 45.0, -100.0
        x, y = generator._latlon_to_local(lat, lon)

        assert isinstance(x, float)
        assert isinstance(y, float)
        # Should be reasonable values
        assert abs(x) < 10000000  # Within reasonable bounds
        assert abs(y) < 10000000

    def test_calculate_curvature(self, generator):
        """Test curvature calculation."""
        p1 = {'x': 0.0, 'y': 0.0}
        p2 = {'x': 1.0, 'y': 0.0}
        p3 = {'x': 2.0, 'y': 1.0}  # Slight curve

        curvature = generator._calculate_curvature(p1, p2, p3)
        assert curvature >= 0  # Curvature should be positive

    def test_calculate_curvature_straight(self, generator):
        """Test curvature calculation for straight line."""
        p1 = {'x': 0.0, 'y': 0.0}
        p2 = {'x': 1.0, 'y': 0.0}
        p3 = {'x': 2.0, 'y': 0.0}  # Straight line

        curvature = generator._calculate_curvature(p1, p2, p3)
        assert abs(curvature) < 0.01  # Should be very close to zero

    def test_calculate_banking_angle(self, generator):
        """Test banking angle calculation."""
        # High curvature (tight turn)
        high_curvature = 0.1  # 10m radius
        banking = generator._calculate_banking_angle(high_curvature)
        assert banking > 0

        # Low curvature (gentle curve)
        low_curvature = 0.005  # 200m radius
        banking = generator._calculate_banking_angle(low_curvature)
        assert banking >= 0

        # Zero curvature (straight)
        zero_curvature = 0.0
        banking = generator._calculate_banking_angle(zero_curvature)
        assert banking == 0

    def test_calculate_banking_angle_limits(self, generator):
        """Test banking angle respects maximum limits."""
        # Very high curvature
        extreme_curvature = 1.0  # 1m radius
        banking = generator._calculate_banking_angle(extreme_curvature)
        assert banking <= generator.config.banking_max_deg

    def test_sample_terrain_within_bounds(self, generator):
        """Test terrain sampling within bounds."""
        terrain_data = np.random.rand(100, 100).astype(np.float32) * 100 + 800
        bbox = {'north': 50.0, 'south': 40.0, 'east': -90.0, 'west': -100.0}

        # Point within bounds
        elevation = generator._sample_terrain(0, 0, terrain_data, bbox)
        assert elevation is not None
        assert isinstance(elevation, float)

    def test_sample_terrain_out_of_bounds(self, generator):
        """Test terrain sampling out of bounds."""
        terrain_data = np.random.rand(100, 100).astype(np.float32)
        bbox = {'north': 50.0, 'south': 40.0, 'east': -90.0, 'west': -100.0}

        # Point outside bounds
        elevation = generator._sample_terrain(1000000, 1000000, terrain_data, bbox)
        assert elevation is None

    def test_calculate_grip_level(self, generator):
        """Test grip level calculation."""
        # Normal conditions
        grip = generator._calculate_grip_level(0.01, 5.0)
        assert 0.1 <= grip <= 1.0

        # Extreme curvature (should reduce grip)
        grip_extreme = generator._calculate_grip_level(0.5, 0.0)
        assert grip_extreme < grip

        # Good banking (should increase grip)
        grip_banked = generator._calculate_grip_level(0.01, 20.0)
        assert grip_banked >= grip

    @pytest.mark.asyncio
    async def test_generate_road_mesh_success(self, generator, sample_route_data):
        """Test successful road mesh generation."""
        geometry, metadata = generator.generate_road_mesh(sample_route_data)

        assert geometry is not None
        assert isinstance(geometry, RoadGeometry)
        assert len(geometry.vertices) > 0
        assert len(geometry.indices) > 0
        assert 'vertex_count' in metadata
        assert 'triangle_count' in metadata
        assert metadata['vertex_count'] == len(geometry.vertices)
        assert metadata['triangle_count'] == len(geometry.indices)

    @pytest.mark.asyncio
    async def test_generate_road_mesh_insufficient_points(self, generator):
        """Test road mesh generation with insufficient points."""
        # Single point route
        points = [RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0)]
        route_data = RouteData(
            points=points,
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=0.0,
            metadata={}
        )

        with pytest.raises(ValueError, match="Route must have at least 2 points"):
            generator.generate_road_mesh(route_data)

    @pytest.mark.asyncio
    async def test_generate_road_mesh_with_terrain(self, generator, sample_route_data):
        """Test road mesh generation with terrain data."""
        # Create mock terrain data
        terrain_data = np.ones((50, 50), dtype=np.float32) * 900  # Flat terrain at 900m
        terrain_bbox = {'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1}

        geometry, metadata = generator.generate_road_mesh(sample_route_data, terrain_data, terrain_bbox)

        assert geometry is not None
        assert len(geometry.vertices) > 0
        # Road should follow terrain elevation
        for vertex in geometry.vertices:
            assert vertex[2] >= 900  # Should be at or above terrain

    def test_generate_centerline(self, generator, sample_route_data):
        """Test centerline generation."""
        route_points = [(p.lat, p.lon, p.elevation) for p in sample_route_data.points]
        centerline = generator._generate_centerline(route_points)

        assert len(centerline) == len(route_points)
        assert 'distance' in centerline[0]
        assert 'curvature' in centerline[0]
        assert 'heading' in centerline[0]

        # Check distance accumulation
        assert centerline[0]['distance'] == 0.0
        assert centerline[1]['distance'] > centerline[0]['distance']

    def test_generate_cross_sections(self, generator, sample_route_data):
        """Test cross-section generation."""
        route_points = [(p.lat, p.lon, p.elevation) for p in sample_route_data.points]
        centerline = generator._generate_centerline(route_points)
        cross_sections = generator._generate_cross_sections(centerline, None, None)

        assert len(cross_sections) == len(centerline)
        for cs in cross_sections:
            assert 'center' in cs
            assert 'left_points' in cs
            assert 'right_points' in cs
            assert 'heading' in cs
            assert 'banking_angle' in cs
            assert len(cs['left_points']) > 0
            assert len(cs['right_points']) > 0

    def test_build_mesh_from_cross_sections(self, generator):
        """Test mesh building from cross-sections."""
        # Create mock cross-sections
        cross_sections = [
            {
                'center': {'x': 0, 'y': 0, 'z': 0, 'distance': 0},
                'left_points': [
                    {'x': -3, 'y': 0, 'z': 0, 'lateral_pos': -1, 'distance': 0},
                    {'x': -1.5, 'y': 0, 'z': 0, 'lateral_pos': -0.5, 'distance': 0}
                ],
                'right_points': [
                    {'x': 1.5, 'y': 0, 'z': 0, 'lateral_pos': 0.5, 'distance': 0},
                    {'x': 3, 'y': 0, 'z': 0, 'lateral_pos': 1, 'distance': 0}
                ]
            },
            {
                'center': {'x': 10, 'y': 0, 'z': 0, 'distance': 10},
                'left_points': [
                    {'x': 7, 'y': 0, 'z': 0, 'lateral_pos': -1, 'distance': 10},
                    {'x': 8.5, 'y': 0, 'z': 0, 'lateral_pos': -0.5, 'distance': 10}
                ],
                'right_points': [
                    {'x': 11.5, 'y': 0, 'z': 0, 'lateral_pos': 0.5, 'distance': 10},
                    {'x': 13, 'y': 0, 'z': 0, 'lateral_pos': 1, 'distance': 10}
                ]
            }
        ]

        geometry = RoadGeometry()
        generator._build_mesh_from_cross_sections(geometry, cross_sections)

        assert len(geometry.vertices) > 0
        assert len(geometry.indices) > 0
        assert len(geometry.uvs) > 0  # Should have UVs

    def test_calculate_physics_properties(self, generator):
        """Test physics properties calculation."""
        centerline = [
            {'curvature': 0.01, 'distance': 0},
            {'curvature': 0.02, 'distance': 10},
            {'curvature': 0.005, 'distance': 20}
        ]
        cross_sections = [
            {'banking_angle': 5.0},
            {'banking_angle': 10.0},
            {'banking_angle': 3.0}
        ]

        physics = generator._calculate_physics_properties(centerline, cross_sections)

        assert 'friction_coefficient' in physics
        assert 'average_curvature' in physics
        assert 'max_curvature' in physics
        assert 'average_banking_deg' in physics
        assert 'grip_level' in physics
        assert physics['friction_coefficient'] == generator.config.physics_friction
        assert physics['average_curvature'] > 0
        assert physics['grip_level'] > 0


class TestProcessRoadMeshGeneration:
    """Test the main road mesh generation processing function."""

    @pytest.fixture
    def sample_route_data(self):
        """Create sample route data for testing."""
        points = [
            RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0),
            RoutePoint(lat=45.001, lon=-100.001, elevation=1010.0, timestamp=60.0),
            RoutePoint(lat=45.002, lon=-100.002, elevation=1020.0, timestamp=120.0),
            RoutePoint(lat=45.003, lon=-100.003, elevation=1030.0, timestamp=180.0),
        ]
        return RouteData(
            points=points,
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=3000.0,
            metadata={}
        )

    @pytest.mark.asyncio
    async def test_process_road_mesh_generation_success(self, sample_route_data):
        """Test successful road mesh generation processing."""
        result = await process_road_mesh_generation(sample_route_data)

        assert result.success is True
        assert result.stage.name == "ROAD_MESH"
        assert 'geometry_stats' in result.data
        assert 'physics_properties' in result.data
        assert 'mesh_quality_score' in result.data

    @pytest.mark.asyncio
    async def test_process_road_mesh_generation_with_config(self, sample_route_data):
        """Test road mesh generation with custom config."""
        config = RoadMeshConfig(road_width_m=8.0, physics_friction=0.9)
        result = await process_road_mesh_generation(sample_route_data, None, config)

        assert result.success is True
        assert result.data['geometry_stats']['road_width_m'] == 8.0
        assert result.data['physics_properties']['friction_coefficient'] == 0.9

    @pytest.mark.asyncio
    async def test_process_road_mesh_generation_failure(self):
        """Test road mesh generation processing failure."""
        # Create invalid route data
        route_data = RouteData(
            points=[RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0)],  # Only one point
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=0.0,
            metadata={}
        )

        result = await process_road_mesh_generation(route_data)

        assert result.success is False
        assert len(result.errors) > 0
        assert "Road mesh generation failed" in result.errors[0]


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def generator(self):
        return RoadMeshGenerator(RoadMeshConfig())

    def test_empty_route(self, generator):
        """Test handling of empty route."""
        route_data = RouteData(
            points=[],
            bounding_box={'north': 45.0, 'south': 45.0, 'east': -100.0, 'west': -100.0},
            total_distance_m=0.0,
            metadata={}
        )

        with pytest.raises(ValueError):
            generator.generate_road_mesh(route_data)

    def test_single_point_route(self, generator):
        """Test handling of single point route."""
        route_data = RouteData(
            points=[RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0)],
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=0.0,
            metadata={}
        )

        with pytest.raises(ValueError, match="Route must have at least 2 points"):
            generator.generate_road_mesh(route_data)

    def test_extreme_coordinates(self, generator):
        """Test handling of extreme coordinate values."""
        # North pole
        points = [
            RoutePoint(lat=89.9, lon=0.0, elevation=1000.0, timestamp=0.0),
            RoutePoint(lat=89.8, lon=0.1, elevation=1010.0, timestamp=60.0),
        ]
        route_data = RouteData(
            points=points,
            bounding_box={'north': 90.0, 'south': 89.0, 'east': 1.0, 'west': -1.0},
            total_distance_m=1000.0,
            metadata={}
        )

        geometry, metadata = generator.generate_road_mesh(route_data)
        assert geometry is not None
        assert len(geometry.vertices) > 0

    def test_high_curvature_route(self, generator):
        """Test route with very high curvature (hairpin turns)."""
        # Create a route that makes sharp turns
        points = []
        for i in range(20):
            angle = i * 0.3  # Sharp turns
            lat = 45.0 + math.sin(angle) * 0.01
            lon = -100.0 + math.cos(angle) * 0.01
            points.append(RoutePoint(lat=lat, lon=lon, elevation=1000.0 + i * 5, timestamp=float(i * 10)))

        route_data = RouteData(
            points=points,
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=5000.0,
            metadata={}
        )

        geometry, metadata = generator.generate_road_mesh(route_data)
        assert geometry is not None
        # Should have significant banking
        physics = geometry.physics_properties
        assert physics['max_banking_deg'] > 10

    def test_long_straight_route(self, generator):
        """Test very long straight route."""
        points = []
        for i in range(100):
            lat = 45.0 + i * 0.001  # Very gradual change
            lon = -100.0  # Straight north
            points.append(RoutePoint(lat=lat, lon=lon, elevation=1000.0, timestamp=float(i * 60)))

        route_data = RouteData(
            points=points,
            bounding_box={'north': 46.0, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=100000.0,  # 100km
            metadata={}
        )

        geometry, metadata = generator.generate_road_mesh(route_data)
        assert geometry is not None
        assert len(geometry.vertices) > 0
        # Should have minimal banking on straight road
        physics = geometry.physics_properties
        assert physics['average_banking_deg'] < 1.0

    def test_terrain_sampling_edge_cases(self, generator):
        """Test terrain sampling at boundaries."""
        terrain_data = np.random.rand(10, 10).astype(np.float32)
        bbox = {'north': 50.0, 'south': 40.0, 'east': -90.0, 'west': -100.0}

        # Test at exact boundaries
        elevation = generator._sample_terrain(-100.0, 50.0, terrain_data, bbox)  # NW corner
        assert elevation is not None

        elevation = generator._sample_terrain(-90.0, 40.0, terrain_data, bbox)  # SE corner
        assert elevation is not None

        # Test just outside boundaries
        elevation = generator._sample_terrain(-100.1, 50.0, terrain_data, bbox)  # Just west
        assert elevation is None

        elevation = generator._sample_terrain(-100.0, 50.1, terrain_data, bbox)  # Just north
        assert elevation is None


class TestIntegrationScenarios:
    """Test integration scenarios with realistic data."""

    @pytest.fixture
    def generator(self):
        return RoadMeshGenerator(RoadMeshConfig())

    @pytest.mark.asyncio
    async def test_full_mesh_generation_pipeline(self, generator):
        """Test complete mesh generation pipeline."""
        # Create realistic cycling route
        points = []
        for i in range(50):
            # Simulate a winding mountain road
            t = i / 49.0
            lat = 45.0 + t * 0.1 + 0.02 * math.sin(t * 4 * math.pi)
            lon = -100.0 + t * 0.1 + 0.02 * math.cos(t * 3 * math.pi)
            elevation = 1000.0 + 200 * math.sin(t * math.pi) + 50 * t  # Rolling hills with overall climb
            points.append(RoutePoint(lat=lat, lon=lon, elevation=elevation, timestamp=float(i * 30)))

        route_data = RouteData(
            points=points,
            bounding_box={'north': 45.2, 'south': 44.8, 'east': -99.7, 'west': -100.3},
            total_distance_m=8000.0,  # ~8km route
            metadata={'sport': 'cycling', 'difficulty': 'hard'}
        )

        geometry, metadata = generator.generate_road_mesh(route_data)

        assert geometry is not None
        assert len(geometry.vertices) > 1000  # Should have substantial mesh
        assert len(geometry.indices) > 500
        assert metadata['total_length_m'] > 7000  # Should match route distance
        assert metadata['has_uvs'] is True
        assert metadata['has_normals'] is True

        # Check physics properties are reasonable
        physics = geometry.physics_properties
        assert 0.5 <= physics['grip_level'] <= 1.0
        assert physics['surface_type'] == 'asphalt'

    @pytest.mark.asyncio
    async def test_mesh_with_terrain_integration(self, generator):
        """Test mesh generation with terrain data integration."""
        # Create route
        points = [
            RoutePoint(lat=45.0, lon=-100.0, elevation=1000.0, timestamp=0.0),
            RoutePoint(lat=45.01, lon=-100.01, elevation=1010.0, timestamp=60.0),
            RoutePoint(lat=45.02, lon=-100.02, elevation=1020.0, timestamp=120.0),
        ]
        route_data = RouteData(
            points=points,
            bounding_box={'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1},
            total_distance_m=2000.0,
            metadata={}
        )

        # Create terrain that varies
        terrain_data = np.zeros((50, 50), dtype=np.float32)
        # Add some hills
        x = np.linspace(0, 1, 50)
        y = np.linspace(0, 1, 50)
        X, Y = np.meshgrid(x, y)
        terrain_data = 950 + 100 * np.sin(X * 4 * np.pi) * np.cos(Y * 4 * np.pi)

        terrain_bbox = {'north': 45.1, 'south': 44.9, 'east': -99.9, 'west': -100.1}

        geometry, metadata = generator.generate_road_mesh(route_data, terrain_data, terrain_bbox)

        assert geometry is not None
        # Road should follow terrain contours
        elevations = [v[2] for v in geometry.vertices]
        assert min(elevations) >= 950  # Should be above minimum terrain
        assert max(elevations) <= 1100  # Should be below maximum terrain

    @pytest.mark.asyncio
    async def test_performance_large_route(self, generator):
        """Test performance with large route."""
        import time

        # Create large route (500 points)
        points = []
        for i in range(500):
            t = i / 499.0
            lat = 45.0 + t * 0.5
            lon = -100.0 + 0.1 * math.sin(t * 10 * math.pi)  # Winding
            elevation = 1000.0 + 100 * math.sin(t * 5 * math.pi)
            points.append(RoutePoint(lat=lat, lon=lon, elevation=elevation, timestamp=float(i * 10)))

        route_data = RouteData(
            points=points,
            bounding_box={'north': 45.6, 'south': 44.9, 'east': -99.7, 'west': -100.3},
            total_distance_m=50000.0,
            metadata={}
        )

        start_time = time.time()
        geometry, metadata = generator.generate_road_mesh(route_data)
        end_time = time.time()

        assert geometry is not None
        assert len(geometry.vertices) > 10000  # Substantial mesh
        assert end_time - start_time < 10.0  # Should complete within 10 seconds

    @pytest.mark.asyncio
    async def test_concurrent_mesh_generation(self, generator):
        """Test generating multiple meshes concurrently."""
        routes = []
        for route_idx in range(3):
            points = []
            for i in range(20):
                lat = 45.0 + route_idx * 0.1 + i * 0.005
                lon = -100.0 + i * 0.005
                elevation = 1000.0 + route_idx * 50
                points.append(RoutePoint(lat=lat, lon=lon, elevation=elevation, timestamp=float(i * 30)))

            route_data = RouteData(
                points=points,
                bounding_box={'north': 45.2 + route_idx * 0.1, 'south': 44.8 + route_idx * 0.1,
                            'east': -99.7, 'west': -100.3},
                total_distance_m=2000.0,
                metadata={}
            )
            routes.append(route_data)

        # Generate concurrently
        import asyncio
        tasks = [generator.generate_road_mesh(route) for route in routes]
        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        for geometry, metadata in results:
            assert geometry is not None
            assert len(geometry.vertices) > 0
            assert metadata['vertex_count'] > 0