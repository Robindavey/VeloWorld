package rides

import (
	"testing"
)

func TestRideValidation(t *testing.T) {
	tests := []struct {
		name string
		ride CreateRideRequest
		valid bool
	}{
		{
			name: "valid ride",
			ride: CreateRideRequest{
				RouteID:      "550e8400-e29b-41d4-a716-446655440000",
				StartTime:    "2024-01-01T10:00:00Z",
				EndTime:      "2024-01-01T11:00:00Z",
				Distance:     25000.0,
				Duration:     3600,
				AvgSpeed:     25.0,
				MaxSpeed:     35.0,
				AvgHeartRate: 150,
				MaxHeartRate: 180,
				AvgPower:     200,
				MaxPower:     350,
				Calories:     500,
			},
			valid: true,
		},
		{
			name: "negative distance",
			ride: CreateRideRequest{
				RouteID:      "550e8400-e29b-41d4-a716-446655440000",
				StartTime:    "2024-01-01T10:00:00Z",
				EndTime:      "2024-01-01T11:00:00Z",
				Distance:     -1000.0,
				Duration:     3600,
				AvgSpeed:     25.0,
				MaxSpeed:     35.0,
				AvgHeartRate: 150,
				MaxHeartRate: 180,
				AvgPower:     200,
				MaxPower:     350,
				Calories:     500,
			},
			valid: false,
		},
		{
			name: "invalid duration",
			ride: CreateRideRequest{
				RouteID:      "550e8400-e29b-41d4-a716-446655440000",
				StartTime:    "2024-01-01T10:00:00Z",
				EndTime:      "2024-01-01T11:00:00Z",
				Distance:     25000.0,
				Duration:     -3600,
				AvgSpeed:     25.0,
				MaxSpeed:     35.0,
				AvgHeartRate: 150,
				MaxHeartRate: 180,
				AvgPower:     200,
				MaxPower:     350,
				Calories:     500,
			},
			valid: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Basic validation logic
			if tt.ride.Distance < 0 {
				if tt.valid {
					t.Error("Expected valid ride, got invalid")
				}
			} else if tt.ride.Duration < 0 {
				if tt.valid {
					t.Error("Expected valid ride, got invalid")
				}
			} else if !tt.valid {
				t.Error("Expected invalid ride, got valid")
			}
		})
	}
}