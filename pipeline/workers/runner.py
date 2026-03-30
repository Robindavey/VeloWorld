"""
VeloWorld Pipeline Worker Runner

This module implements the Redis queue listener that processes route processing jobs.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, Any, Optional
from uuid import UUID
import time
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import math
import tempfile
from pathlib import Path

import redis
import psycopg
import boto3
from fitparse import FitFile
from veloworld_pipeline import RouteProcessor, ProcessingStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PipelineWorker:
    """Redis queue-based pipeline worker."""

    def __init__(self):
        redis_url = os.getenv('REDIS_URL')
        if redis_url:
            parsed = urlparse(redis_url)
            self.redis_host = parsed.hostname or 'localhost'
            self.redis_port = parsed.port or 6379
        else:
            self.redis_host = os.getenv('REDIS_HOST', 'localhost')
            self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.redis = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            decode_responses=True
        )
        self.queue_name = 'route_processing_queue'
        self.database_url = os.getenv('DATABASE_URL', 'postgresql://veloworld:veloworld@localhost:5432/veloworld?sslmode=disable')
        self.s3_bucket = os.getenv('S3_BUCKET', 'veloworld')
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=os.getenv('S3_ENDPOINT', 'http://localhost:9000'),
            aws_access_key_id=os.getenv('S3_ACCESS_KEY', 'minioadmin'),
            aws_secret_access_key=os.getenv('S3_SECRET_KEY', 'minioadmin'),
            region_name="us-east-1",
        )
        # Initialize the pipeline processor with empty config for now
        self.processor = RouteProcessor({})

    def connect_redis(self) -> bool:
        """Test Redis connection."""
        try:
            self.redis.ping()
            logger.info("Connected to Redis")
            return True
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False

    def update_job_status(self, job_id: str, status: str, progress: Optional[Dict[str, Any]] = None):
        """Update job status in Redis."""
        try:
            job_key = f"job:{job_id}"
            status_data = {
                'status': status,
                'updated_at': time.time()
            }
            if progress:
                status_data['progress'] = progress

            self.redis.hset(job_key, mapping=status_data)
            logger.info(f"Updated job {job_id} status to {status}")
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")

    async def process_job(self, job_data: Dict[str, Any]) -> bool:
        """Process a single route processing job."""
        job_id = job_data['id']
        route_id = job_data['route_id']
        s3_key = job_data['s3_key']
        format_type = job_data['format']

        logger.info(f"Processing job {job_id} for route {route_id}")

        try:
            # Update status to running
            self.update_job_status(job_id, 'running')
            self.update_route_status(str(route_id), "processing")

            # Convert string route_id to UUID if needed
            if isinstance(route_id, str):
                route_id = UUID(route_id)

            # Process the route
            result = await self.processor.process_route(
                route_id=route_id,
                s3_key=s3_key,
                format_type=format_type
            )

            # Check if processing was successful
            if result and result.get('final_data'):
                render_data = self.generate_render_data(str(route_id), s3_key, format_type)
                self.mark_route_ready(
                    str(route_id),
                    distance_m=render_data["distance_m"],
                    elevation_gain_m=render_data["elevation_gain_m"],
                )
                self.store_render_data(str(route_id), render_data)
                self.update_job_status(job_id, 'completed', {
                    'completed_stages': result.get('completed_stages', []),
                    'completed_at': time.time()
                })
                logger.info(f"Job {job_id} completed successfully")
                return True
            else:
                error_msg = "Processing returned no results"
                self.update_route_status(str(route_id), "failed")
                self.update_job_status(job_id, 'failed', {
                    'error': error_msg,
                    'failed_at': time.time()
                })
                logger.error(f"Job {job_id} failed: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"Job {job_id} failed with exception: {e}")
            self.update_route_status(str(route_id), "failed")
            self.update_job_status(job_id, 'failed', {
                'error': str(e),
                'failed_at': time.time()
            })
            return False

    def update_route_status(self, route_id: str, status: str):
        """Persist route processing state for API clients."""
        try:
            with psycopg.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE routes SET processing_status = %s WHERE id = %s",
                        (status, route_id),
                    )
                conn.commit()
            logger.info(f"Route {route_id} status updated to {status}")
        except Exception as e:
            logger.error(f"Failed to update route status for {route_id}: {e}")

    def mark_route_ready(self, route_id: str, distance_m: float, elevation_gain_m: float):
        """Mark route as ready with baseline stats for demo rendering."""
        try:
            with psycopg.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE routes
                        SET processing_status = 'ready',
                            distance_m = %s,
                            elevation_gain_m = %s
                        WHERE id = %s
                        """,
                        (distance_m, elevation_gain_m, route_id),
                    )
                conn.commit()
            logger.info(f"Route {route_id} marked ready")
        except Exception as e:
            logger.error(f"Failed to mark route ready for {route_id}: {e}")

    def store_render_data(self, route_id: str, render_data: Dict[str, Any]):
        try:
            self.redis.set(f"route_render:{route_id}", json.dumps(render_data))
        except Exception as e:
            logger.error(f"Failed to store render data for {route_id}: {e}")

    def generate_render_data(self, route_id: str, s3_key: str, format_type: str) -> Dict[str, Any]:
        raw_bytes = self.download_route_file(s3_key)
        points = self.parse_route_points(raw_bytes, format_type)
        if len(points) < 2:
            raise ValueError("Route file did not contain enough points")

        cumulative = 0.0
        profile_points = [{
            "distance_m": 0.0,
            "elevation_m": points[0]["elevation_m"],
            "lat": points[0]["lat"],
            "lon": points[0]["lon"],
        }]
        elevation_gain = 0.0
        prev = points[0]

        for point in points[1:]:
            segment = self.haversine_distance(prev["lat"], prev["lon"], point["lat"], point["lon"])
            if segment > 1000:  # Skip obvious GPS spikes.
                prev = point
                continue
            cumulative += segment

            delta_elev = point["elevation_m"] - prev["elevation_m"]
            if delta_elev > 0:
                elevation_gain += delta_elev

            profile_points.append({
                "distance_m": cumulative,
                "elevation_m": point["elevation_m"],
                "lat": point["lat"],
                "lon": point["lon"],
            })
            prev = point

        sampled_profile = self.resample_profile(profile_points, target_points=500)
        if cumulative <= 0:
            raise ValueError("Route distance is zero after parsing")

        return {
            "route_id": route_id,
            "distance_m": cumulative,
            "elevation_gain_m": elevation_gain,
            "profile_points": sampled_profile,
        }

    def download_route_file(self, s3_key: str) -> bytes:
        response = self.s3_client.get_object(Bucket=self.s3_bucket, Key=s3_key)
        return response["Body"].read()

    def parse_route_points(self, content: bytes, format_type: str):
        fmt = format_type.lower()
        if fmt in ("gpx",):
            return self.parse_gpx_points(content)
        if fmt in ("fit", "fits"):
            return self.parse_fit_points(content)
        if fmt in ("tcx",):
            return self.parse_tcx_points(content)
        raise ValueError(f"Unsupported format for render parsing: {format_type}")

    def parse_gpx_points(self, content: bytes):
        root = ET.fromstring(content)
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        track_points = root.findall(".//gpx:trkpt", ns)
        if not track_points:
            track_points = root.findall(".//trkpt")

        points = []
        last_elevation = 100.0
        for trkpt in track_points:
            lat = trkpt.attrib.get("lat")
            lon = trkpt.attrib.get("lon")
            if lat is None or lon is None:
                continue
            ele_node = trkpt.find("gpx:ele", ns)
            if ele_node is None:
                ele_node = trkpt.find("ele")
            try:
                elevation = float(ele_node.text) if ele_node is not None and ele_node.text else last_elevation
            except ValueError:
                elevation = last_elevation
            last_elevation = elevation
            points.append({
                "lat": float(lat),
                "lon": float(lon),
                "elevation_m": elevation,
            })
        return points

    def parse_fit_points(self, content: bytes):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".fit") as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            fit_file = FitFile(str(tmp_path))
            points = []
            last_elevation = 100.0
            for record in fit_file.get_messages("record"):
                values = {field.name: field.value for field in record}
                lat_sc = values.get("position_lat")
                lon_sc = values.get("position_long")
                if lat_sc is None or lon_sc is None:
                    continue
                altitude = values.get("altitude")
                if altitude is None:
                    altitude = last_elevation
                elevation = float(altitude)
                last_elevation = elevation
                points.append({
                    "lat": float(lat_sc) * (180.0 / (2**31)),
                    "lon": float(lon_sc) * (180.0 / (2**31)),
                    "elevation_m": elevation,
                })
            return points
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def parse_tcx_points(self, content: bytes):
        root = ET.fromstring(content)
        ns = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
        points = []
        last_elevation = 100.0
        for trackpoint in root.findall(".//tcx:Trackpoint", ns):
            position = trackpoint.find("tcx:Position", ns)
            if position is None:
                continue
            lat_node = position.find("tcx:LatitudeDegrees", ns)
            lon_node = position.find("tcx:LongitudeDegrees", ns)
            if lat_node is None or lon_node is None:
                continue
            elev_node = trackpoint.find("tcx:AltitudeMeters", ns)
            try:
                elevation = float(elev_node.text) if elev_node is not None and elev_node.text else last_elevation
            except ValueError:
                elevation = last_elevation
            last_elevation = elevation
            points.append({
                "lat": float(lat_node.text),
                "lon": float(lon_node.text),
                "elevation_m": elevation,
            })
        return points

    def resample_profile(self, profile_points, target_points=500):
        if len(profile_points) <= target_points:
            return profile_points
        result = []
        last_idx = len(profile_points) - 1
        for i in range(target_points):
            idx = round(i * last_idx / (target_points - 1))
            result.append(profile_points[idx])
        return result

    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        earth_radius = 6371000.0
        lat1r = math.radians(lat1)
        lon1r = math.radians(lon1)
        lat2r = math.radians(lat2)
        lon2r = math.radians(lon2)
        dlat = lat2r - lat1r
        dlon = lon2r - lon1r
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return earth_radius * c

    async def run_worker(self):
        """Main worker loop."""
        logger.info("Starting pipeline worker...")

        if not self.connect_redis():
            logger.error("Cannot start worker without Redis connection")
            return

        logger.info("Worker started, listening for jobs...")

        while True:
            try:
                # Block for up to 30 seconds waiting for a job
                result = self.redis.blpop(self.queue_name, timeout=30)

                if result is None:
                    # Timeout, continue loop
                    continue

                queue_name, job_json = result
                logger.info(f"Received job from queue: {queue_name}")

                try:
                    job_data = json.loads(job_json)
                    await self.process_job(job_data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse job JSON: {e}")
                except Exception as e:
                    logger.error(f"Error processing job: {e}")

            except redis.ConnectionError as e:
                logger.error(f"Redis connection error: {e}")
                # Wait before retrying
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {e}")
                await asyncio.sleep(1)


async def main():
    """Main entry point."""
    worker = PipelineWorker()
    await worker.run_worker()


if __name__ == "__main__":
    asyncio.run(main())