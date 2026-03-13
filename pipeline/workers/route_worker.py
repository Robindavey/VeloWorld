"""
VeloWorld Route Processing Worker

Integrates the Python pipeline with the Go backend via Redis queue.
Processes uploaded route files and generates 3D simulation assets.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import tempfile
import time

import redis
from pydantic import BaseModel

# Add pipeline to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from veloworld_pipeline import RouteProcessor, PipelineResult, ProcessingStage
from stages.ingestion import process_route_ingestion
from stages.map_matching import process_map_matching
from stages.terrain import process_terrain_reconstruction
from stages.road_mesh import process_road_mesh_generation


class WorkerConfig(BaseModel):
    """Worker configuration."""
    redis_url: str = "redis://localhost:6379"
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "veloworld"
    s3_base_path: str = "uploads"
    s3_use_ssl: bool = False
    pipeline_timeout_seconds: int = 300  # 5 minutes
    worker_id: str = "worker-1"


class RouteProcessingJob(BaseModel):
    """Route processing job from Redis queue."""
    id: str
    route_id: str
    s3_key: str
    format: str
    submitted_at: str


class VeloWorldWorker:
    """Route processing worker that integrates Python pipeline with Go backend."""

    def __init__(self, config: WorkerConfig):
        self.config = config
        self.redis = redis.Redis.from_url(config.redis_url)
        self.logger = logging.getLogger(f"VeloWorldWorker-{config.worker_id}")
        self.is_running = False

        # Initialize S3 client for downloading/uploading files
        try:
            import boto3
            self.s3_client = boto3.client(
                's3',
                endpoint_url=config.s3_endpoint,
                aws_access_key_id=config.s3_access_key,
                aws_secret_access_key=config.s3_secret_key,
                use_ssl=config.s3_use_ssl
            )
        except ImportError:
            self.logger.error("boto3 not installed. Install with: pip install boto3")
            raise

    async def start(self):
        """Start the worker."""
        self.is_running = True
        self.logger.info(f"Starting worker {self.config.worker_id}")

        while self.is_running:
            try:
                job = self._dequeue_job()
                if job:
                    await self._process_job(job)
                else:
                    # No jobs available, wait a bit
                    await asyncio.sleep(1)
            except Exception as e:
                self.logger.error(f"Worker error: {e}")
                await asyncio.sleep(5)  # Back off on errors

    def stop(self):
        """Stop the worker."""
        self.is_running = False
        self.logger.info(f"Stopping worker {self.config.worker_id}")

    def _dequeue_job(self) -> Optional[RouteProcessingJob]:
        """Dequeue a job from Redis."""
        try:
            # BRPOP returns [queue_name, job_data]
            result = self.redis.brpop("route_processing_queue", timeout=1)
            if result:
                queue_name, job_data = result
                job_dict = json.loads(job_data)
                return RouteProcessingJob(**job_dict)
        except Exception as e:
            self.logger.error(f"Failed to dequeue job: {e}")
        return None

    async def _process_job(self, job: RouteProcessingJob):
        """Process a single route processing job."""
        self.logger.info(f"Processing job {job.id} for route {job.route_id}")

        # Update job status to processing
        self._update_job_status(job.id, "processing")

        try:
            # Download route file from S3
            route_file_path = await self._download_route_file(job.s3_key)
            if not route_file_path:
                raise Exception("Failed to download route file")

            # Process the route through the pipeline
            result = await self._process_route_pipeline(route_file_path, job.format)

            if result.success:
                # Upload processed assets to S3
                package_url = await self._upload_processed_assets(job.route_id, result)

                # Update database with processing results
                self._update_route_metadata(job.route_id, result, package_url)

                # Mark job as completed
                self._update_job_status(job.id, "completed")

                self.logger.info(f"Successfully processed route {job.route_id}")
            else:
                # Processing failed
                error_msg = "; ".join(result.errors)
                self._update_job_status(job.id, "failed", error_msg)
                self.logger.error(f"Failed to process route {job.route_id}: {error_msg}")

        except Exception as e:
            error_msg = str(e)
            self._update_job_status(job.id, "failed", error_msg)
            self.logger.error(f"Job {job.id} failed: {error_msg}")

        finally:
            # Clean up temporary files
            if 'route_file_path' in locals():
                try:
                    os.unlink(route_file_path)
                except:
                    pass

    async def _download_route_file(self, s3_key: str) -> Optional[str]:
        """Download route file from S3."""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".route") as tmp_file:
                tmp_path = tmp_file.name

            # Download from S3
            self.s3_client.download_file(
                self.config.s3_bucket,
                s3_key,
                tmp_path
            )

            self.logger.info(f"Downloaded route file: {s3_key}")
            return tmp_path

        except Exception as e:
            self.logger.error(f"Failed to download route file {s3_key}: {e}")
            return None

    async def _process_route_pipeline(self, file_path: str, format: str) -> PipelineResult:
        """Process route through the complete pipeline."""
        self.logger.info(f"Starting pipeline processing for {file_path}")

        try:
            # Stage 1: Route Ingestion
            ingestion_result = await process_route_ingestion(file_path, format)
            if not ingestion_result.success:
                return ingestion_result

            route_data = ingestion_result.data['route_data']

            # Stage 2: Map Matching
            matching_result = await process_map_matching(route_data)
            if not matching_result.success:
                return matching_result

            # Update route data with matched coordinates
            route_data.points = matching_result.data['matched_points']

            # Stage 3: Terrain Reconstruction
            terrain_result = await process_terrain_reconstruction(route_data)
            if not terrain_result.success:
                return terrain_result

            # Stage 4: Road Mesh Generation
            mesh_result = await process_road_mesh_generation(route_data, terrain_result)
            if not mesh_result.success:
                return mesh_result

            # Create final pipeline result
            return PipelineResult(
                stage=ProcessingStage.PACKAGING,
                success=True,
                data={
                    'route_data': route_data,
                    'terrain_data': terrain_result.data,
                    'mesh_data': mesh_result.data,
                    'processing_stats': {
                        'ingestion_time': ingestion_result.data.get('processing_time', 0),
                        'matching_time': matching_result.data.get('processing_time', 0),
                        'terrain_time': terrain_result.data.get('processing_time', 0),
                        'mesh_time': mesh_result.data.get('processing_time', 0),
                    }
                }
            )

        except Exception as e:
            return PipelineResult(
                stage=ProcessingStage.INGESTION,
                success=False,
                errors=[f"Pipeline processing failed: {str(e)}"]
            )

    async def _upload_processed_assets(self, route_id: str, result: PipelineResult) -> str:
        """Upload processed assets to S3 and return package URL."""
        try:
            # Create package structure
            package_data = {
                'route_id': route_id,
                'version': '1.0',
                'timestamp': time.time(),
                'data': result.data
            }

            # Upload as JSON package
            package_key = f"processed/{route_id}/package.json"
            self.s3_client.put_object(
                Bucket=self.config.s3_bucket,
                Key=package_key,
                Body=json.dumps(package_data, indent=2),
                ContentType='application/json'
            )

            package_url = f"{self.config.s3_endpoint}/{self.config.s3_bucket}/{package_key}"
            self.logger.info(f"Uploaded processed package: {package_url}")
            return package_url

        except Exception as e:
            self.logger.error(f"Failed to upload processed assets: {e}")
            raise

    def _update_job_status(self, job_id: str, status: str, error: str = ""):
        """Update job status in Redis."""
        try:
            job_key = f"job:{job_id}"
            self.redis.hset(job_key, "status", status)
            if error:
                self.redis.hset(job_key, "error", error)
            if status in ["completed", "failed"]:
                self.redis.hset(job_key, "completed_at", time.time())
        except Exception as e:
            self.logger.error(f"Failed to update job status: {e}")

    def _update_route_metadata(self, route_id: str, result: PipelineResult, package_url: str):
        """Update route metadata in database."""
        # Note: In a real implementation, this would update the database
        # For now, we'll just log the metadata that should be stored
        metadata = {
            'route_id': route_id,
            'distance_m': result.data['route_data'].total_distance_m,
            'processing_status': 'completed',
            'package_url': package_url,
            'quality_score': result.data.get('mesh_data', {}).get('mesh_quality_score', 0.8),
            'terrain_quality': result.data.get('terrain_data', {}).get('quality_score', 0.7),
        }
        self.logger.info(f"Route metadata: {metadata}")


async def main():
    """Main worker entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load configuration from environment
    config = WorkerConfig(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        s3_endpoint=os.getenv("S3_ENDPOINT", "http://localhost:9000"),
        s3_access_key=os.getenv("S3_ACCESS_KEY", "minioadmin"),
        s3_secret_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
        s3_bucket=os.getenv("S3_BUCKET", "veloworld"),
        s3_base_path=os.getenv("S3_BASE_PATH", "uploads"),
        s3_use_ssl=os.getenv("S3_USE_SSL", "false").lower() == "true",
        worker_id=os.getenv("WORKER_ID", "worker-1")
    )

    worker = VeloWorldWorker(config)

    def signal_handler(signum, frame):
        worker.stop()

    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await worker.start()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    asyncio.run(main())