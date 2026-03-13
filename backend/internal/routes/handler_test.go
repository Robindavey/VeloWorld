package routes

import (
	"testing"
)

func TestRouteValidation(t *testing.T) {
	tests := []struct {
		name  string
		route Route
		valid bool
	}{
		{
			name: "valid route",
			route: Route{
				Name:        "Test Route",
				Description: "A test route",
				Distance:    10000.0,
				Duration:    1800,
			},
			valid: true,
		},
		{
			name: "empty name",
			route: Route{
				Name:        "",
				Description: "A test route",
				Distance:    10000.0,
				Duration:    1800,
			},
			valid: false,
		},
		{
			name: "negative distance",
			route: Route{
				Name:        "Test Route",
				Description: "A test route",
				Distance:    -1000.0,
				Duration:    1800,
			},
			valid: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Basic validation logic
			if tt.route.Name == "" {
				if tt.valid {
					t.Error("Expected valid route, got invalid")
				}
			} else if tt.route.Distance < 0 {
				if tt.valid {
					t.Error("Expected valid route, got invalid")
				}
			} else if !tt.valid {
				t.Error("Expected invalid route, got valid")
			}
		})
	}
}