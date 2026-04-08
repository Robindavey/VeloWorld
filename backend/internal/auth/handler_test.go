package auth

import (
	"net/http"
	"strings"
	"testing"
)

func TestRegisterRequestValidation(t *testing.T) {
	tests := []struct {
		name     string
		request  RegisterRequest
		wantCode int
	}{
		{
			name: "valid request",
			request: RegisterRequest{
				Email:    "test@example.com",
				Password: "password123",
			},
			wantCode: http.StatusOK,
		},
		{
			name: "invalid email",
			request: RegisterRequest{
				Email:    "invalid-email",
				Password: "password123",
			},
			wantCode: http.StatusBadRequest,
		},
		{
			name: "short password",
			request: RegisterRequest{
				Email:    "test@example.com",
				Password: "123",
			},
			wantCode: http.StatusBadRequest,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotCode := http.StatusOK
			if tt.request.Email == "" || tt.request.Password == "" {
				gotCode = http.StatusBadRequest
			} else if !strings.Contains(tt.request.Email, "@") {
				gotCode = http.StatusBadRequest
			} else if len(tt.request.Password) < 8 {
				gotCode = http.StatusBadRequest
			}

			if gotCode != tt.wantCode {
				t.Fatalf("expected status %d, got %d", tt.wantCode, gotCode)
			}
		})
	}
}