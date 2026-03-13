package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type JobQueue struct {
	redis *redis.Client
}

type RouteProcessingJob struct {
	ID          uuid.UUID `json:"id"`
	RouteID     uuid.UUID `json:"route_id"`
	S3Key       string    `json:"s3_key"`
	Format      string    `json:"format"`
	SubmittedAt time.Time `json:"submitted_at"`
}

func NewJobQueue(redis *redis.Client) *JobQueue {
	return &JobQueue{redis: redis}
}

func (q *JobQueue) EnqueueRouteProcessing(ctx context.Context, routeID uuid.UUID, s3Key, format string) error {
	job := RouteProcessingJob{
		ID:          uuid.New(),
		RouteID:     routeID,
		S3Key:       s3Key,
		Format:      format,
		SubmittedAt: time.Now(),
	}

	jobData, err := json.Marshal(job)
	if err != nil {
		return fmt.Errorf("failed to marshal job: %w", err)
	}

	// Add to queue
	err = q.redis.LPush(ctx, "route_processing_queue", jobData).Err()
	if err != nil {
		return fmt.Errorf("failed to enqueue job: %w", err)
	}

	// Store job metadata
	jobKey := fmt.Sprintf("job:%s", job.ID.String())
	err = q.redis.HSet(ctx, jobKey, map[string]interface{}{
		"route_id":     routeID.String(),
		"s3_key":       s3Key,
		"format":       format,
		"status":       "queued",
		"submitted_at": job.SubmittedAt.Unix(),
	}).Err()
	if err != nil {
		return fmt.Errorf("failed to store job metadata: %w", err)
	}

	return nil
}

func (q *JobQueue) DequeueRouteProcessing(ctx context.Context) (*RouteProcessingJob, error) {
	// Pop job from queue
	result, err := q.redis.BRPop(ctx, time.Second*30, "route_processing_queue").Result()
	if err != nil {
		if err == redis.Nil {
			return nil, nil // No jobs available
		}
		return nil, fmt.Errorf("failed to dequeue job: %w", err)
	}

	var job RouteProcessingJob
	err = json.Unmarshal([]byte(result[1]), &job)
	if err != nil {
		return nil, fmt.Errorf("failed to unmarshal job: %w", err)
	}

	// Update job status
	jobKey := fmt.Sprintf("job:%s", job.ID.String())
	err = q.redis.HSet(ctx, jobKey, "status", "processing").Err()
	if err != nil {
		return nil, fmt.Errorf("failed to update job status: %w", err)
	}

	return &job, nil
}

func (q *JobQueue) MarkJobCompleted(ctx context.Context, jobID uuid.UUID) error {
	jobKey := fmt.Sprintf("job:%s", jobID.String())
	return q.redis.HSet(ctx, jobKey, "status", "completed").Err()
}

func (q *JobQueue) MarkJobFailed(ctx context.Context, jobID uuid.UUID, errorMsg string) error {
	jobKey := fmt.Sprintf("job:%s", jobID.String())
	return q.redis.HMSet(ctx, jobKey, map[string]interface{}{
		"status":    "failed",
		"error":     errorMsg,
		"failed_at": time.Now().Unix(),
	}).Err()
}

func (q *JobQueue) GetJobStatus(ctx context.Context, jobID uuid.UUID) (map[string]string, error) {
	jobKey := fmt.Sprintf("job:%s", jobID.String())
	result, err := q.redis.HGetAll(ctx, jobKey).Result()
	if err != nil {
		return nil, fmt.Errorf("failed to get job status: %w", err)
	}
	return result, nil
}