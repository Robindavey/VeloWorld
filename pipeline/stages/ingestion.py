"""
Route ingestion and parsing stage.

Handles parsing of GPX, FIT, and TCX files into normalized route data.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

import fitparse
import numpy as np
from pydantic import ValidationError

from veloverse_pipeline import RouteData, RoutePoint, PipelineResult, ProcessingStage


class RouteParser:
    """Parser for various GPS route file formats."""

    @staticmethod
    def parse_file(file_path: Path, route_id: UUID) -> RouteData:
        """
        Parse a route file and return normalized RouteData.

        Args:
            file_path: Path to the route file
            route_id: Unique identifier for the route

        Returns:
            Normalized route data

        Raises:
            ValueError: If file format is unsupported or parsing fails
        """
        suffix = file_path.suffix.lower()

        if suffix == '.gpx':
            return GPXParser.parse(file_path, route_id)
        elif suffix == '.fit':
            return FITParser.parse(file_path, route_id)
        elif suffix == '.tcx':
            return TCXParser.parse(file_path, route_id)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

    @staticmethod
    def validate_route(points: List[RoutePoint]) -> Tuple[bool, List[str]]:
        """
        Validate route data for quality and plausibility.

        Args:
            points: List of route points

        Returns:
            Tuple of (is_valid, warnings_list)
        """
        warnings = []

        # Check minimum point count
        if len(points) < 100:
            warnings.append(f"Low point count: {len(points)} (recommended: >100)")

        # Check for geographic plausibility (no teleportation)
        max_jump_distance = 0
        for i in range(1, len(points)):
            prev, curr = points[i-1], points[i]
            distance = haversine_distance(prev.lat, prev.lon, curr.lat, curr.lon)
            max_jump_distance = max(max_jump_distance, distance)

            # Flag suspicious jumps (>500m between consecutive points)
            if distance > 500:
                warnings.append(f"Large GPS jump at point {i}: {distance:.1f}m")

        # Check coordinate bounds
        lats = [p.lat for p in points]
        lons = [p.lon for p in points]

        if min(lats) < -90 or max(lats) > 90:
            raise ValueError("Invalid latitude values")
        if min(lons) < -180 or max(lons) > 180:
            raise ValueError("Invalid longitude values")

        # Calculate total distance
        total_distance = 0
        for i in range(1, len(points)):
            prev, curr = points[i-1], points[i]
            total_distance += haversine_distance(prev.lat, prev.lon, curr.lat, curr.lon)

        # Check minimum route length
        if total_distance < 500:  # 500m minimum
            raise ValueError(f"Route too short: {total_distance:.1f}m (minimum: 500m)")

        # Calculate bounding box
        bounding_box = {
            'north': max(lats),
            'south': min(lats),
            'east': max(lons),
            'west': min(lons)
        }

        return len(warnings) == 0, warnings + [f"Total distance: {total_distance:.1f}m"]


class GPXParser:
    """GPX file parser."""

    @staticmethod
    def parse(file_path: Path, route_id: UUID) -> RouteData:
        """Parse GPX file into RouteData."""
        tree = ET.parse(file_path)
        root = tree.getroot()

        # GPX namespace handling
        ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}

        points = []
        for trkpt in root.findall('.//gpx:trkpt', ns):
            lat = float(trkpt.get('lat'))
            lon = float(trkpt.get('lon'))

            # Extract elevation if available
            ele_elem = trkpt.find('gpx:ele', ns)
            elevation = float(ele_elem.text) if ele_elem is not None else None

            # Extract timestamp if available
            time_elem = trkpt.find('gpx:time', ns)
            timestamp = time_elem.text if time_elem is not None else None

            points.append(RoutePoint(
                lat=lat,
                lon=lon,
                timestamp=timestamp,
                raw_elevation=elevation
            ))

        # Validate and create RouteData
        is_valid, warnings = RouteParser.validate_route(points)

        return RouteData(
            route_id=route_id,
            source_format='gpx',
            points=points,
            total_distance_m=calculate_total_distance(points),
            point_count=len(points),
            bounding_box=calculate_bounding_box(points),
            quality_warnings=warnings
        )


class FITParser:
    """FIT file parser using fitparse library."""

    @staticmethod
    def parse(file_path: Path, route_id: UUID) -> RouteData:
        """Parse FIT file into RouteData."""
        fitfile = fitparse.FitFile(str(file_path))

        points = []
        for record in fitfile.get_messages('record'):
            lat = lon = timestamp = elevation = None

            for field in record:
                if field.name == 'position_lat':
                    lat = field.value * (180.0 / 2**31)  # Convert from semicircles
                elif field.name == 'position_long':
                    lon = field.value * (180.0 / 2**31)  # Convert from semicircles
                elif field.name == 'timestamp':
                    timestamp = field.value.isoformat() if field.value else None
                elif field.name == 'altitude':
                    elevation = field.value

            if lat is not None and lon is not None:
                points.append(RoutePoint(
                    lat=lat,
                    lon=lon,
                    timestamp=timestamp,
                    raw_elevation=elevation
                ))

        # Validate and create RouteData
        is_valid, warnings = RouteParser.validate_route(points)

        return RouteData(
            route_id=route_id,
            source_format='fit',
            points=points,
            total_distance_m=calculate_total_distance(points),
            point_count=len(points),
            bounding_box=calculate_bounding_box(points),
            quality_warnings=warnings
        )


class TCXParser:
    """TCX (Training Center XML) file parser."""

    @staticmethod
    def parse(file_path: Path, route_id: UUID) -> RouteData:
        """Parse TCX file into RouteData."""
        tree = ET.parse(file_path)
        root = tree.getroot()

        # TCX namespace handling
        ns = {'tcx': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'}

        points = []
        for trackpoint in root.findall('.//tcx:Trackpoint', ns):
            # Extract position
            position = trackpoint.find('tcx:Position', ns)
            if position is not None:
                lat_elem = position.find('tcx:LatitudeDegrees', ns)
                lon_elem = position.find('tcx:LongitudeDegrees', ns)

                if lat_elem is not None and lon_elem is not None:
                    lat = float(lat_elem.text)
                    lon = float(lon_elem.text)

                    # Extract elevation
                    alt_elem = trackpoint.find('tcx:AltitudeMeters', ns)
                    elevation = float(alt_elem.text) if alt_elem is not None else None

                    # Extract timestamp
                    time_elem = trackpoint.find('tcx:Time', ns)
                    timestamp = time_elem.text if time_elem is not None else None

                    points.append(RoutePoint(
                        lat=lat,
                        lon=lon,
                        timestamp=timestamp,
                        raw_elevation=elevation
                    ))

        # Validate and create RouteData
        is_valid, warnings = RouteParser.validate_route(points)

        return RouteData(
            route_id=route_id,
            source_format='tcx',
            points=points,
            total_distance_m=calculate_total_distance(points),
            point_count=len(points),
            bounding_box=calculate_bounding_box(points),
            quality_warnings=warnings
        )


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate haversine distance between two points in meters."""
    R = 6371000  # Earth's radius in meters

    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_rad, lon2_rad = np.radians(lat2), np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = np.sin(dlat/2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

    return R * c


def calculate_total_distance(points: List[RoutePoint]) -> float:
    """Calculate total distance of a route in meters."""
    if len(points) < 2:
        return 0.0

    total_distance = 0.0
    for i in range(1, len(points)):
        prev, curr = points[i-1], points[i]
        total_distance += haversine_distance(prev.lat, prev.lon, curr.lat, curr.lon)

    return total_distance


def calculate_bounding_box(points: List[RoutePoint]) -> dict:
    """Calculate bounding box for route points."""
    if not points:
        return {'north': 0, 'south': 0, 'east': 0, 'west': 0}

    lats = [p.lat for p in points]
    lons = [p.lon for p in points]

    return {
        'north': max(lats),
        'south': min(lats),
        'east': max(lons),
        'west': min(lons)
    }