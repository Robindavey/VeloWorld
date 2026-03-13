"""
Road mesh generation stage implementation.

Generates 3D road geometry from matched GPS coordinates and terrain data.
"""

import asyncio
import math
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID

import numpy as np
from pydantic import BaseModel

from veloworld_pipeline import RouteData, PipelineResult, ProcessingStage


class RoadMeshConfig(BaseModel):
    """Configuration for road mesh generation."""
    road_width_m: float = 6.0  # Standard road width in meters
    lane_count: int = 2  # Number of lanes
    shoulder_width_m: float = 1.5  # Shoulder width on each side
    resolution_m: float = 1.0  # Mesh resolution along route
    banking_max_deg: float = 30.0  # Maximum road banking in degrees
    superelevation_rate: float = 0.06  # Rate of superelevation (crown)
    texture_repeat_m: float = 10.0  # Texture repeat distance
    physics_friction: float = 0.8  # Road surface friction coefficient
    generate_normals: bool = True
    generate_uvs: bool = True


class RoadGeometry:
    """Represents 3D road geometry data."""

    def __init__(self):
        self.vertices: List[Tuple[float, float, float]] = []
        self.normals: List[Tuple[float, float, float]] = []
        self.uvs: List[Tuple[float, float]] = []
        self.indices: List[Tuple[int, int, int]] = []
        self.physics_properties: Dict[str, Any] = {}

    def add_vertex(self, x: float, y: float, z: float, normal: Optional[Tuple[float, float, float]] = None,
                   uv: Optional[Tuple[float, float]] = None):
        """Add a vertex to the mesh."""
        self.vertices.append((x, y, z))
        if normal:
            self.normals.append(normal)
        if uv:
            self.uvs.append(uv)

    def add_triangle(self, i1: int, i2: int, i3: int):
        """Add a triangle to the mesh."""
        self.indices.append((i1, i2, i3))


class RoadMeshGenerator:
    """Generates 3D road mesh from route and terrain data."""

    def __init__(self, config: RoadMeshConfig):
        self.config = config

    def generate_road_mesh(self, route_data: RouteData, terrain_data: Optional[np.ndarray] = None,
                          terrain_bbox: Optional[Dict[str, float]] = None) -> Tuple[RoadGeometry, Dict[str, Any]]:
        """
        Generate 3D road mesh from route data.

        Args:
            route_data: Route data with matched coordinates
            terrain_data: Optional elevation data for terrain following
            terrain_bbox: Bounding box of terrain data

        Returns:
            Tuple of (road_geometry, metadata)
        """
        geometry = RoadGeometry()

        # Extract route points (prefer matched coordinates)
        route_points = []
        for point in route_data.points:
            if hasattr(point, 'matched_lat') and point.matched_lat is not None:
                lat, lon = point.matched_lat, point.matched_lon
            else:
                lat, lon = point.lat, point.lon
            route_points.append((lat, lon, point.elevation))

        if len(route_points) < 2:
            raise ValueError("Route must have at least 2 points")

        # Generate road centerline
        centerline = self._generate_centerline(route_points)

        # Generate road cross-sections
        cross_sections = self._generate_cross_sections(centerline, terrain_data, terrain_bbox)

        # Build mesh from cross-sections
        self._build_mesh_from_cross_sections(geometry, cross_sections)

        # Calculate physics properties
        physics_props = self._calculate_physics_properties(centerline, cross_sections)

        geometry.physics_properties = physics_props

        metadata = {
            'vertex_count': len(geometry.vertices),
            'triangle_count': len(geometry.indices),
            'total_length_m': centerline[-1]['distance'] if centerline else 0.0,
            'road_width_m': self.config.road_width_m,
            'resolution_m': self.config.resolution_m,
            'physics_friction': self.config.physics_friction,
            'has_normals': len(geometry.normals) > 0,
            'has_uvs': len(geometry.uvs) > 0
        }

        return geometry, metadata

    def _generate_centerline(self, route_points: List[Tuple[float, float, float]]) -> List[Dict[str, Any]]:
        """Generate smoothed centerline with distance and curvature information."""
        centerline = []

        for i, (lat, lon, elevation) in enumerate(route_points):
            # Convert to local coordinates (simplified - would use proper projection)
            x, y = self._latlon_to_local(lat, lon)

            point_data = {
                'x': x,
                'y': y,
                'z': elevation,
                'lat': lat,
                'lon': lon,
                'distance': 0.0,
                'curvature': 0.0,
                'heading': 0.0
            }

            if i > 0:
                prev = centerline[-1]
                distance = math.sqrt((x - prev['x'])**2 + (y - prev['y'])**2)
                point_data['distance'] = prev['distance'] + distance

                # Calculate heading
                dx = x - prev['x']
                dy = y - prev['y']
                point_data['heading'] = math.atan2(dy, dx)

            centerline.append(point_data)

        # Calculate curvature for banking
        for i in range(1, len(centerline) - 1):
            prev = centerline[i-1]
            curr = centerline[i]
            next_p = centerline[i+1]

            # Calculate curvature using three-point formula
            curvature = self._calculate_curvature(prev, curr, next_p)
            centerline[i]['curvature'] = curvature

        return centerline

    def _generate_cross_sections(self, centerline: List[Dict[str, Any]],
                               terrain_data: Optional[np.ndarray],
                               terrain_bbox: Optional[Dict[str, float]]) -> List[Dict[str, Any]]:
        """Generate cross-sections perpendicular to centerline."""
        cross_sections = []

        for i, point in enumerate(centerline):
            # Calculate road orientation
            if i < len(centerline) - 1:
                next_point = centerline[i + 1]
                heading = math.atan2(next_point['y'] - point['y'], next_point['x'] - point['x'])
            else:
                heading = point['heading']

            # Calculate banking based on curvature
            banking_angle = self._calculate_banking_angle(point['curvature'])

            # Generate cross-section points
            left_points, right_points = self._generate_cross_section_points(
                point, heading, banking_angle, terrain_data, terrain_bbox
            )

            cross_sections.append({
                'center': point,
                'left_points': left_points,
                'right_points': right_points,
                'heading': heading,
                'banking_angle': banking_angle,
                'distance': point['distance']
            })

        return cross_sections

    def _generate_cross_section_points(self, center_point: Dict[str, Any], heading: float,
                                     banking_angle: float, terrain_data: Optional[np.ndarray],
                                     terrain_bbox: Optional[Dict[str, float]]) -> Tuple[List[Dict[str, float]], List[Dict[str, float]]]:
        """Generate points for left and right road edges."""
        # Road width calculations
        total_width = self.config.road_width_m + 2 * self.config.shoulder_width_m
        half_width = total_width / 2

        # Perpendicular vectors
        perp_x = -math.sin(heading)
        perp_y = math.cos(heading)

        # Banking rotation
        bank_rad = math.radians(banking_angle)
        cos_bank = math.cos(bank_rad)
        sin_bank = math.sin(bank_rad)

        left_points = []
        right_points = []

        # Generate points across the road width
        num_points_per_side = max(2, int(total_width / self.config.resolution_m))

        for i in range(num_points_per_side + 1):
            # Position across road (-1 to 1, left to right)
            t = (i / num_points_per_side - 0.5) * 2

            # Lateral offset
            lateral_x = perp_x * t * half_width
            lateral_y = perp_y * t * half_width

            # Apply banking (rotate around centerline)
            if t != 0:  # Don't bank the centerline
                # Distance from center
                dist_from_center = abs(t) * half_width
                # Banking raises outer edges
                height_offset = dist_from_center * math.tan(bank_rad) if t > 0 else -dist_from_center * math.tan(bank_rad)
            else:
                height_offset = 0

            # Add superelevation (crown)
            crown_offset = -abs(t) * self.config.superelevation_rate * half_width

            # Base position
            x = center_point['x'] + lateral_x
            y = center_point['y'] + lateral_y
            z = center_point['z'] + height_offset + crown_offset

            # Sample terrain if available
            if terrain_data is not None and terrain_bbox is not None:
                terrain_z = self._sample_terrain(x, y, terrain_data, terrain_bbox)
                if terrain_z is not None:
                    z = max(z, terrain_z)  # Road follows terrain but doesn't go below

            point_data = {
                'x': x,
                'y': y,
                'z': z,
                'lateral_pos': t,  # -1 (left) to 1 (right)
                'distance': center_point['distance']
            }

            if t <= 0:
                left_points.append(point_data)
            else:
                right_points.append(point_data)

        return left_points, right_points

    def _build_mesh_from_cross_sections(self, geometry: RoadGeometry,
                                      cross_sections: List[Dict[str, Any]]):
        """Build triangle mesh from cross-sections."""
        vertex_offset = 0

        for i in range(len(cross_sections) - 1):
            current = cross_sections[i]
            next_cs = cross_sections[i + 1]

            # Combine left and right points
            current_points = current['left_points'] + current['right_points']
            next_points = next_cs['left_points'] + next_cs['right_points']

            # Add vertices for current cross-section
            for point in current_points:
                # Calculate normal (simplified - pointing up with banking)
                normal = (0, 0, 1)  # Simplified normal

                # Calculate UV coordinates
                u = point['distance'] / self.config.texture_repeat_m
                v = (point['lateral_pos'] + 1) / 2  # 0 to 1 across road

                geometry.add_vertex(point['x'], point['y'], point['z'], normal, (u, v))

            # Add vertices for next cross-section
            for point in next_points:
                normal = (0, 0, 1)
                u = point['distance'] / self.config.texture_repeat_m
                v = (point['lateral_pos'] + 1) / 2

                geometry.add_vertex(point['x'], point['y'], point['z'], normal, (u, v))

            # Create triangles between cross-sections
            num_points = len(current_points)
            for j in range(num_points - 1):
                # Two triangles per quad
                i1 = vertex_offset + j
                i2 = vertex_offset + j + 1
                i3 = vertex_offset + num_points + j
                i4 = vertex_offset + num_points + j + 1

                geometry.add_triangle(i1, i2, i3)
                geometry.add_triangle(i2, i4, i3)

            vertex_offset += 2 * num_points

    def _calculate_physics_properties(self, centerline: List[Dict[str, Any]],
                                    cross_sections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate physics properties for the road."""
        # Calculate average curvature for handling characteristics
        curvatures = [abs(p['curvature']) for p in centerline if 'curvature' in p]
        avg_curvature = sum(curvatures) / len(curvatures) if curvatures else 0

        # Calculate banking effectiveness
        banking_angles = [abs(cs['banking_angle']) for cs in cross_sections]
        avg_banking = sum(banking_angles) / len(banking_angles) if banking_angles else 0

        return {
            'friction_coefficient': self.config.physics_friction,
            'average_curvature': avg_curvature,
            'max_curvature': max(curvatures) if curvatures else 0,
            'average_banking_deg': avg_banking,
            'max_banking_deg': max(banking_angles) if banking_angles else 0,
            'road_width_m': self.config.road_width_m,
            'surface_type': 'asphalt',
            'grip_level': self._calculate_grip_level(avg_curvature, avg_banking)
        }

    @staticmethod
    def _latlon_to_local(lat: float, lon: float) -> Tuple[float, float]:
        """Convert lat/lon to local coordinates (simplified projection)."""
        # Simplified equirectangular projection
        R = 6371000  # Earth radius in meters
        x = lon * R * math.pi / 180 * math.cos(lat * math.pi / 180)
        y = lat * R * math.pi / 180
        return x, y

    @staticmethod
    def _calculate_curvature(p1: Dict[str, float], p2: Dict[str, float], p3: Dict[str, float]) -> float:
        """Calculate curvature using three points."""
        # Simplified curvature calculation
        # In 3D space, this would use proper circle fitting
        v1 = np.array([p2['x'] - p1['x'], p2['y'] - p1['y']])
        v2 = np.array([p3['x'] - p2['x'], p3['y'] - p2['y']])

        # Angle between vectors
        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        cos_angle = np.clip(cos_angle, -1, 1)
        angle = math.acos(cos_angle)

        # Curvature approximation (1/radius)
        if angle > 0:
            # Approximate arc length
            chord1 = np.linalg.norm(v1)
            chord2 = np.linalg.norm(v2)
            avg_chord = (chord1 + chord2) / 2
            return angle / avg_chord if avg_chord > 0 else 0
        return 0

    def _calculate_banking_angle(self, curvature: float) -> float:
        """Calculate road banking angle based on curvature."""
        if curvature == 0:
            return 0

        # Banking formula: angle = arctan(v²/(g*R)) where R = 1/curvature
        # Simplified: assume design speed and use empirical relationship
        radius = 1.0 / curvature if curvature > 0 else float('inf')

        if radius < 50:  # Tight curve
            banking = min(self.config.banking_max_deg, 30.0)
        elif radius < 200:  # Medium curve
            banking = min(self.config.banking_max_deg, 15.0)
        else:  # Gentle curve
            banking = 0.0

        return banking

    def _sample_terrain(self, x: float, y: float, terrain_data: np.ndarray,
                       bbox: Dict[str, float]) -> Optional[float]:
        """Sample elevation from terrain data."""
        # Convert local coordinates back to lat/lon (simplified)
        lat = y / (6371000 * math.pi / 180)
        lon = x / (6371000 * math.pi / 180 * math.cos(lat * math.pi / 180))

        # Check if within bbox
        if not (bbox['west'] <= lon <= bbox['east'] and bbox['south'] <= lat <= bbox['north']):
            return None

        # Convert to pixel coordinates
        x_norm = (lon - bbox['west']) / (bbox['east'] - bbox['west'])
        y_norm = 1.0 - (lat - bbox['south']) / (bbox['north'] - bbox['south'])

        height, width = terrain_data.shape
        x_pixel = int(x_norm * width)
        y_pixel = int(y_norm * height)

        # Clamp to valid range
        x_pixel = max(0, min(width - 1, x_pixel))
        y_pixel = max(0, min(height - 1, y_pixel))

        return float(terrain_data[y_pixel, x_pixel])

    def _calculate_grip_level(self, avg_curvature: float, avg_banking: float) -> float:
        """Calculate grip level based on road geometry."""
        # Grip decreases with curvature, increases with banking
        base_grip = self.config.physics_friction
        curvature_penalty = min(0.2, avg_curvature * 100)  # Penalty for tight curves
        banking_bonus = min(0.1, avg_banking / 30.0 * 0.1)  # Bonus for banking

        return max(0.1, min(1.0, base_grip - curvature_penalty + banking_bonus))


async def process_road_mesh_generation(route_data: RouteData, terrain_result: Optional[PipelineResult] = None,
                                     config: Optional[RoadMeshConfig] = None) -> PipelineResult:
    """
    Process road mesh generation for a route.

    Args:
        route_data: Route data with matched coordinates
        terrain_result: Optional terrain reconstruction result
        config: Road mesh generation configuration

    Returns:
        Pipeline result with road mesh data
    """
    if config is None:
        config = RoadMeshConfig()

    try:
        generator = RoadMeshGenerator(config)

        # Extract terrain data if available
        terrain_data = None
        terrain_bbox = None
        if terrain_result and terrain_result.success:
            # In a real implementation, we'd extract the elevation array from terrain_result
            # For now, we'll work without terrain data
            pass

        geometry, metadata = generator.generate_road_mesh(route_data, terrain_data, terrain_bbox)

        return PipelineResult(
            stage=ProcessingStage.ROAD_MESH,
            success=True,
            data={
                'geometry_stats': metadata,
                'physics_properties': geometry.physics_properties,
                'mesh_quality_score': 0.85  # Placeholder quality metric
            }
        )

    except Exception as e:
        return PipelineResult(
            stage=ProcessingStage.ROAD_MESH,
            success=False,
            errors=[f"Road mesh generation failed: {str(e)}"]
        )