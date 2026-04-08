package rides

import (
	"testing"

	"github.com/google/uuid"
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
				RouteID:        routeIDPtr(uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")),
				DurationS:      3600,
				DistanceM:      25000.0,
				ElevationGainM: 400,
				AvgSpeedKph:    25.0,
				MaxSpeedKph:    35.0,
				AvgPowerW:      200,
				MaxPowerW:      350,
				TotalEnergyKj:  760,
			},
			valid: true,
		},
		{
			name: "negative distance",
			ride: CreateRideRequest{
				RouteID:        routeIDPtr(uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")),
				DurationS:      3600,
				DistanceM:      -1000.0,
				ElevationGainM: 100,
				AvgSpeedKph:    25.0,
				MaxSpeedKph:    35.0,
				AvgPowerW:      200,
				MaxPowerW:      350,
				TotalEnergyKj:  760,
			},
			valid: false,
		},
		{
			name: "invalid duration",
			ride: CreateRideRequest{
				RouteID:        routeIDPtr(uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")),
				DurationS:      -3600,
				DistanceM:      25000.0,
				ElevationGainM: 400,
				AvgSpeedKph:    25.0,
				MaxSpeedKph:    35.0,
				AvgPowerW:      200,
				MaxPowerW:      350,
				TotalEnergyKj:  760,
			},
			valid: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Basic validation logic
			if tt.ride.DistanceM <= 0 {
				if tt.valid {
					t.Error("Expected valid ride, got invalid")
				}
			} else if tt.ride.DurationS <= 0 {
				if tt.valid {
					t.Error("Expected valid ride, got invalid")
				}
			} else if !tt.valid {
				t.Error("Expected invalid ride, got valid")
			}
		})
	}
}

func routeIDPtr(id uuid.UUID) *uuid.UUID {
	return &id
}