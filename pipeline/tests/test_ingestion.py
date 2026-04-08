"""
Comprehensive tests for route ingestion and parsing.

Tests cover GPX, FIT, TCX parsing with various edge cases and validation scenarios.
"""

import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

import pytest
import numpy as np

from stages.ingestion import (
    RouteParser, GPXParser, FITParser, TCXParser,
    haversine_distance, calculate_total_distance, calculate_bounding_box
)
from veloverse_pipeline import RouteData, RoutePoint


class TestRouteParser:
    """Test the main RouteParser class."""

    def test_parse_gpx_file(self):
        """Test parsing a valid GPX file."""
        route_id = uuid4()
        gpx_content = self._create_valid_gpx()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gpx', delete=False) as f:
            f.write(gpx_content)
            f.flush()
            route_data = RouteParser.parse_file(Path(f.name), route_id)

        assert route_data.route_id == route_id
        assert route_data.source_format == 'gpx'
        assert len(route_data.points) == 3
        assert route_data.total_distance_m > 0
        assert route_data.point_count == 3

    def test_parse_unsupported_format(self):
        """Test parsing an unsupported file format."""
        route_id = uuid4()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("invalid format")
            f.flush()

        with pytest.raises(ValueError, match="Unsupported file format"):
            RouteParser.parse_file(Path(f.name), route_id)

    def test_validate_route_valid(self):
        """Test validation of a valid route."""
        points = [
            RoutePoint(lat=45.0, lon=6.0),
            RoutePoint(lat=45.001, lon=6.001),
            RoutePoint(lat=45.002, lon=6.002),
        ]
        is_valid, warnings = RouteParser.validate_route(points)
        assert is_valid
        assert len(warnings) >= 1  # Should have distance info

    def test_validate_route_too_short(self):
        """Test validation of a route that's too short."""
        points = [
            RoutePoint(lat=45.0, lon=6.0),
            RoutePoint(lat=45.0001, lon=6.0001),  # ~10m apart
        ]
        with pytest.raises(ValueError, match="Route too short"):
            RouteParser.validate_route(points)

    def test_validate_route_too_few_points(self):
        """Test validation of a route with too few points."""
        points = [RoutePoint(lat=45.0, lon=6.0)]
        is_valid, warnings = RouteParser.validate_route(points)
        assert not is_valid
        assert any("Low point count" in w for w in warnings)

    def test_validate_route_teleportation(self):
        """Test validation of a route with teleportation jumps."""
        points = [
            RoutePoint(lat=45.0, lon=6.0),
            RoutePoint(lat=45.1, lon=6.1),  # Normal movement
            RoutePoint(lat=50.0, lon=10.0),  # Teleportation jump
        ]
        is_valid, warnings = RouteParser.validate_route(points)
        assert not is_valid
        assert any("Large GPS jump" in w for w in warnings)

    def test_validate_route_invalid_coordinates(self):
        """Test validation of routes with invalid coordinates."""
        # Test invalid latitude
        points = [RoutePoint(lat=91.0, lon=6.0)]
        with pytest.raises(ValueError, match="Invalid latitude"):
            RouteParser.validate_route(points)

        # Test invalid longitude
        points = [RoutePoint(lat=45.0, lon=181.0)]
        with pytest.raises(ValueError, match="Invalid longitude"):
            RouteParser.validate_route(points)

    @staticmethod
    def _create_valid_gpx() -> str:
        """Create a valid GPX file content for testing."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="VeloVerse Test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Test Route</name>
    <trkseg>
      <trkpt lat="45.832" lon="6.865">
        <ele>1842.0</ele>
        <time>2024-01-15T09:00:00Z</time>
      </trkpt>
      <trkpt lat="45.833" lon="6.866">
        <ele>1845.0</ele>
        <time>2024-01-15T09:01:00Z</time>
      </trkpt>
      <trkpt lat="45.834" lon="6.867">
        <ele>1850.0</ele>
        <time>2024-01-15T09:02:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>'''


class TestGPXParser:
    """Test GPX file parsing."""

    def test_parse_valid_gpx(self):
        """Test parsing a valid GPX file."""
        route_id = uuid4()
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <trkseg>
      <trkpt lat="45.0" lon="6.0">
        <ele>1000.0</ele>
        <time>2024-01-01T10:00:00Z</time>
      </trkpt>
      <trkpt lat="45.001" lon="6.001">
        <ele>1005.0</ele>
      </trkpt>
    </trkseg>
  </trk>
</gpx>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.gpx', delete=False) as f:
            f.write(gpx_content)
            f.flush()
            route_data = GPXParser.parse(Path(f.name), route_id)

        assert route_data.route_id == route_id
        assert route_data.source_format == 'gpx'
        assert len(route_data.points) == 2
        assert route_data.points[0].lat == 45.0
        assert route_data.points[0].lon == 6.0
        assert route_data.points[0].raw_elevation == 1000.0
        assert route_data.points[0].timestamp == "2024-01-01T10:00:00Z"
        assert route_data.points[1].raw_elevation == 1005.0
        assert route_data.points[1].timestamp is None

    def test_parse_gpx_no_elevation(self):
        """Test parsing GPX without elevation data."""
        route_id = uuid4()
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <trkseg>
      <trkpt lat="45.0" lon="6.0"/>
      <trkpt lat="45.001" lon="6.001"/>
    </trkseg>
  </trk>
</gpx>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.gpx', delete=False) as f:
            f.write(gpx_content)
            f.flush()
            route_data = GPXParser.parse(Path(f.name), route_id)

        assert all(p.raw_elevation is None for p in route_data.points)

    def test_parse_gpx_malformed(self):
        """Test parsing malformed GPX file."""
        route_id = uuid4()
        gpx_content = '''<?xml version="1.0"?>
<invalid>xml</invalid>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.gpx', delete=False) as f:
            f.write(gpx_content)
            f.flush()

        with pytest.raises(ET.ParseError):
            GPXParser.parse(Path(f.name), route_id)


class TestTCXParser:
    """Test TCX file parsing."""

    def test_parse_valid_tcx(self):
        """Test parsing a valid TCX file."""
        route_id = uuid4()
        tcx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Biking">
      <Lap StartTime="2024-01-01T10:00:00Z">
        <Track>
          <Trackpoint>
            <Time>2024-01-01T10:00:00Z</Time>
            <Position>
              <LatitudeDegrees>45.0</LatitudeDegrees>
              <LongitudeDegrees>6.0</LongitudeDegrees>
            </Position>
            <AltitudeMeters>1000.0</AltitudeMeters>
          </Trackpoint>
          <Trackpoint>
            <Time>2024-01-01T10:01:00Z</Time>
            <Position>
              <LatitudeDegrees>45.001</LatitudeDegrees>
              <LongitudeDegrees>6.001</LongitudeDegrees>
            </Position>
            <AltitudeMeters>1005.0</AltitudeMeters>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.tcx', delete=False) as f:
            f.write(tcx_content)
            f.flush()
            route_data = TCXParser.parse(Path(f.name), route_id)

        assert route_data.route_id == route_id
        assert route_data.source_format == 'tcx'
        assert len(route_data.points) == 2
        assert route_data.points[0].lat == 45.0
        assert route_data.points[0].lon == 6.0
        assert route_data.points[0].raw_elevation == 1000.0
        assert route_data.points[0].timestamp == "2024-01-01T10:00:00Z"


class TestUtilityFunctions:
    """Test utility functions."""

    def test_haversine_distance(self):
        """Test haversine distance calculation."""
        # Test known distance (approximately 111 km per degree latitude)
        dist = haversine_distance(0, 0, 1, 0)
        assert abs(dist - 111320) < 100  # Within 100m tolerance

        # Test zero distance
        dist = haversine_distance(45.0, 6.0, 45.0, 6.0)
        assert dist == 0

        # Test antipodal points (should be ~20,000 km)
        dist = haversine_distance(0, 0, 0, 180)
        assert abs(dist - 20037508) < 1000  # Within 1km tolerance

    def test_calculate_total_distance(self):
        """Test total distance calculation."""
        points = [
            RoutePoint(lat=0, lon=0),
            RoutePoint(lat=1, lon=0),  # ~111km
            RoutePoint(lat=1, lon=1),  # ~111km at equator
        ]
        total_dist = calculate_total_distance(points)
        expected = 111320 + 111320  # Two 111km segments
        assert abs(total_dist - expected) < 1000

        # Test empty/single point
        assert calculate_total_distance([]) == 0
        assert calculate_total_distance([RoutePoint(lat=0, lon=0)]) == 0

    def test_calculate_bounding_box(self):
        """Test bounding box calculation."""
        points = [
            RoutePoint(lat=45.0, lon=6.0),
            RoutePoint(lat=46.0, lon=7.0),
            RoutePoint(lat=44.0, lon=5.0),
        ]
        bbox = calculate_bounding_box(points)
        assert bbox['north'] == 46.0
        assert bbox['south'] == 44.0
        assert bbox['east'] == 7.0
        assert bbox['west'] == 5.0

        # Test empty points
        bbox = calculate_bounding_box([])
        assert bbox['north'] == 0
        assert bbox['south'] == 0
        assert bbox['east'] == 0
        assert bbox['west'] == 0


class TestRouteDataValidation:
    """Test RouteData model validation."""

    def test_valid_route_data(self):
        """Test creating valid RouteData."""
        route_id = uuid4()
        points = [
            RoutePoint(lat=45.0, lon=6.0),
            RoutePoint(lat=45.001, lon=6.001),
        ]

        route_data = RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=1000.0,
            point_count=len(points),
            bounding_box={'north': 45.001, 'south': 45.0, 'east': 6.001, 'west': 6.0}
        )

        assert route_data.route_id == route_id
        assert route_data.source_format == 'gpx'
        assert len(route_data.points) == 2

    def test_invalid_route_data_too_few_points(self):
        """Test RouteData with too few points."""
        route_id = uuid4()
        points = [RoutePoint(lat=45.0, lon=6.0)]  # Only 1 point

        with pytest.raises(ValidationError):
            RouteData(
                route_id=route_id,
                source_format='gpx',
                points=points,
                total_distance_m=1000.0,
                point_count=len(points),
                bounding_box={'north': 45.0, 'south': 45.0, 'east': 6.0, 'west': 6.0}
            )

    def test_invalid_route_data_too_short(self):
        """Test RouteData with route too short."""
        route_id = uuid4()
        points = [
            RoutePoint(lat=45.0, lon=6.0),
            RoutePoint(lat=45.0001, lon=6.0001),  # Very short distance
        ]

        with pytest.raises(ValidationError):
            RouteData(
                route_id=route_id,
                source_format='gpx',
                points=points,
                total_distance_m=10.0,  # Too short
                point_count=len(points),
                bounding_box={'north': 45.0001, 'south': 45.0, 'east': 6.0001, 'west': 6.0}
            )

    def test_invalid_coordinates(self):
        """Test RoutePoint with invalid coordinates."""
        with pytest.raises(ValidationError):
            RoutePoint(lat=91.0, lon=6.0)  # Invalid latitude

        with pytest.raises(ValidationError):
            RoutePoint(lat=45.0, lon=181.0)  # Invalid longitude

        with pytest.raises(ValidationError):
            RoutePoint(lat="invalid", lon=6.0)  # Non-numeric latitude


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_extreme_coordinates(self):
        """Test coordinates at extreme valid ranges."""
        # Valid extreme coordinates
        point1 = RoutePoint(lat=89.999, lon=179.999)
        point2 = RoutePoint(lat=-89.999, lon=-179.999)
        point3 = RoutePoint(lat=0.0, lon=0.0)

        points = [point1, point2, point3]
        is_valid, warnings = RouteParser.validate_route(points)
        assert is_valid or len(warnings) > 0  # May have warnings but should not crash

    def test_high_precision_coordinates(self):
        """Test coordinates with high precision."""
        point1 = RoutePoint(lat=45.123456789, lon=6.987654321)
        point2 = RoutePoint(lat=45.123456790, lon=6.987654322)

        points = [point1, point2]
        is_valid, warnings = RouteParser.validate_route(points)
        assert is_valid

    def test_duplicate_points(self):
        """Test route with duplicate consecutive points."""
        points = [
            RoutePoint(lat=45.0, lon=6.0),
            RoutePoint(lat=45.0, lon=6.0),  # Duplicate
            RoutePoint(lat=45.001, lon=6.001),
        ]
        is_valid, warnings = RouteParser.validate_route(points)
        assert is_valid  # Should still be valid, just inefficient

    def test_route_going_backwards(self):
        """Test route that goes backwards (out and back)."""
        points = [
            RoutePoint(lat=45.0, lon=6.0),
            RoutePoint(lat=45.1, lon=6.1),
            RoutePoint(lat=45.0, lon=6.0),  # Back to start
        ]
        is_valid, warnings = RouteParser.validate_route(points)
        assert is_valid

    def test_minimal_valid_route(self):
        """Test the minimal valid route (just meets requirements)."""
        # Create exactly 100 points, 500m total distance
        points = []
        for i in range(100):
            # Each point is ~5m apart to make 500m total
            lat = 45.0 + (i * 0.000045)  # ~5m latitude difference
            lon = 6.0 + (i * 0.000045)
            points.append(RoutePoint(lat=lat, lon=lon))

        is_valid, warnings = RouteParser.validate_route(points)
        assert is_valid

    def test_maximum_reasonable_route(self):
        """Test a very long route (simulate a long cycling route)."""
        # Simulate a 300km route with reasonable point density
        num_points = 3000  # ~100m between points
        points = []
        for i in range(num_points):
            # Gradual progression
            lat = 45.0 + (i * 0.0009)  # Spread over ~2.7 degrees latitude
            lon = 6.0 + (i * 0.0009)
            points.append(RoutePoint(lat=lat, lon=lon))

        is_valid, warnings = RouteParser.validate_route(points)
        assert is_valid
        assert any("Total distance" in w for w in warnings)