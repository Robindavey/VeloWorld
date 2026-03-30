package storage

import (
	"bytes"
	"fmt"
	"io"
	"path/filepath"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/credentials"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/google/uuid"
)

type S3Storage struct {
	client   *s3.S3
	bucket   string
	basePath string
}

type Config struct {
	Endpoint  string
	AccessKey string
	SecretKey string
	Bucket    string
	BasePath  string
	UseSSL    bool
}

func NewS3Storage(config Config) (*S3Storage, error) {
	sess, err := session.NewSession(&aws.Config{
		Region:           aws.String("us-east-1"), // Default region for MinIO
		Endpoint:         aws.String(config.Endpoint),
		Credentials:      credentials.NewStaticCredentials(config.AccessKey, config.SecretKey, ""),
		S3ForcePathStyle: aws.Bool(true), // Required for MinIO
		DisableSSL:       aws.Bool(!config.UseSSL),
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create AWS session: %w", err)
	}

	client := s3.New(sess)

	// Ensure the bucket exists (MinIO does not auto-create buckets)
	_, err = client.HeadBucket(&s3.HeadBucketInput{Bucket: aws.String(config.Bucket)})
	if err != nil {
		_, err = client.CreateBucket(&s3.CreateBucketInput{Bucket: aws.String(config.Bucket)})
		if err != nil {
			return nil, fmt.Errorf("failed to create bucket %s: %w", config.Bucket, err)
		}
	}

	return &S3Storage{
		client:   client,
		bucket:   config.Bucket,
		basePath: config.BasePath,
	}, nil
}

func (s *S3Storage) UploadRouteFile(routeID uuid.UUID, filename string, content []byte) (string, error) {
	// Generate unique filename with route ID
	ext := filepath.Ext(filename)
	key := fmt.Sprintf("%s/routes/%s%s", s.basePath, routeID.String(), ext)

	_, err := s.client.PutObject(&s3.PutObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
		Body:   bytes.NewReader(content),
		ACL:    aws.String("private"),
		Metadata: map[string]*string{
			"route-id": aws.String(routeID.String()),
			"filename": aws.String(filename),
		},
	})
	if err != nil {
		return "", fmt.Errorf("failed to upload file to S3: %w", err)
	}

	return key, nil
}

func (s *S3Storage) DownloadRouteFile(key string) ([]byte, error) {
	resp, err := s.client.GetObject(&s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, fmt.Errorf("failed to download file from S3: %w", err)
	}
	defer resp.Body.Close()

	content, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read file content: %w", err)
	}

	return content, nil
}

func (s *S3Storage) DeleteRouteFile(key string) error {
	_, err := s.client.DeleteObject(&s3.DeleteObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return fmt.Errorf("failed to delete file from S3: %w", err)
	}

	return nil
}

func (s *S3Storage) GetRouteFileURL(key string, expires int64) (string, error) {
	req, _ := s.client.GetObjectRequest(&s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})

	url, err := req.Presign(time.Duration(expires) * time.Second)
	if err != nil {
		return "", fmt.Errorf("failed to generate presigned URL: %w", err)
	}

	return url, nil
}
