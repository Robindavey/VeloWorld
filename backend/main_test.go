package main

import (
	"testing"
)

// TestMain is the entry point for all tests
func TestMain(m *testing.M) {
	// Setup test database and Redis if needed
	// This would typically involve:
	// 1. Starting test containers for PostgreSQL and Redis
	// 2. Running migrations
	// 3. Setting up test data

	m.Run()
}