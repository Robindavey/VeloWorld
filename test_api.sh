#!/bin/bash

# VeloVerse API Test Script
# This script tests the VeloVerse backend API endpoints

API_BASE="http://localhost:8080"
TEST_EMAIL="test@example.com"
TEST_PASSWORD="password123"

echo "=== VeloVerse API Tests ==="
echo "Testing API at: $API_BASE"
echo

# Test 1: Health check
echo "1. Testing health check..."
curl -s -o /dev/null -w "Status: %{http_code}\n" "$API_BASE/health"
echo

# Test 2: User registration
echo "2. Testing user registration..."
REGISTER_RESPONSE=$(curl -s -X POST "$API_BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")

echo "Response: $REGISTER_RESPONSE"
TOKEN=$(echo $REGISTER_RESPONSE | grep -o '"token":"[^"]*' | cut -d'"' -f4)
echo "Token: ${TOKEN:0:20}..."
echo

# Test 3: User login
echo "3. Testing user login..."
LOGIN_RESPONSE=$(curl -s -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")

echo "Response: $LOGIN_RESPONSE"
TOKEN=$(echo $LOGIN_RESPONSE | grep -o '"token":"[^"]*' | cut -d'"' -f4)
echo "Token: ${TOKEN:0:20}..."
echo

# Test 4: Get current user
echo "4. Testing get current user..."
curl -s -H "Authorization: Bearer $TOKEN" \
  -w "Status: %{http_code}\n" \
  "$API_BASE/auth/me"
echo

# Test 5: List routes (should be empty initially)
echo "5. Testing list routes..."
curl -s -H "Authorization: Bearer $TOKEN" \
  -w "Status: %{http_code}\n" \
  "$API_BASE/routes"
echo

# Test 6: Create a test GPX file for upload
echo "6. Creating test GPX file..."
cat > test_route.gpx << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="VeloVerse Test">
  <trk>
    <name>Test Route</name>
    <trkseg>
      <trkpt lat="40.7128" lon="-74.0060">
        <ele>10.0</ele>
      </trkpt>
      <trkpt lat="40.7138" lon="-74.0070">
        <ele>15.0</ele>
      </trkpt>
      <trkpt lat="40.7148" lon="-74.0080">
        <ele>20.0</ele>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
EOF

# Test 7: Upload route
echo "7. Testing route upload..."
UPLOAD_RESPONSE=$(curl -s -X POST "$API_BASE/routes/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "name=Test Route" \
  -F "description=A test cycling route" \
  -F "gpxFile=@test_route.gpx")

echo "Response: $UPLOAD_RESPONSE"
ROUTE_ID=$(echo $UPLOAD_RESPONSE | grep -o '"id":"[^"]*' | cut -d'"' -f4)
echo "Route ID: $ROUTE_ID"
echo

# Test 8: List routes again (should have one route)
echo "8. Testing list routes after upload..."
curl -s -H "Authorization: Bearer $TOKEN" \
  -w "Status: %{http_code}\n" \
  "$API_BASE/routes"
echo

# Test 9: Get specific route
if [ ! -z "$ROUTE_ID" ]; then
  echo "9. Testing get specific route..."
  curl -s -H "Authorization: Bearer $TOKEN" \
    -w "Status: %{http_code}\n" \
    "$API_BASE/routes/$ROUTE_ID"
  echo
fi

# Test 10: Create a ride
if [ ! -z "$ROUTE_ID" ]; then
  echo "10. Testing ride creation..."
  RIDE_RESPONSE=$(curl -s -X POST "$API_BASE/rides" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"routeId\": \"$ROUTE_ID\",
      \"startTime\": \"2024-01-01T10:00:00Z\",
      \"endTime\": \"2024-01-01T11:00:00Z\",
      \"distance\": 15000,
      \"duration\": 3600,
      \"avgSpeed\": 15.0,
      \"maxSpeed\": 25.0,
      \"avgHeartRate\": 140,
      \"maxHeartRate\": 160,
      \"avgPower\": 180,
      \"maxPower\": 280,
      \"calories\": 400
    }")

  echo "Response: $RIDE_RESPONSE"
  RIDE_ID=$(echo $RIDE_RESPONSE | grep -o '"id":"[^"]*' | cut -d'"' -f4)
  echo "Ride ID: $RIDE_ID"
  echo
fi

# Test 11: List rides
echo "11. Testing list rides..."
curl -s -H "Authorization: Bearer $TOKEN" \
  -w "Status: %{http_code}\n" \
  "$API_BASE/rides"
echo

# Test 12: Get specific ride
if [ ! -z "$RIDE_ID" ]; then
  echo "12. Testing get specific ride..."
  curl -s -H "Authorization: Bearer $TOKEN" \
    -w "Status: %{http_code}\n" \
    "$API_BASE/rides/$RIDE_ID"
  echo
fi

# Cleanup
rm -f test_route.gpx

echo "=== Tests completed ==="
echo "Note: Some tests may fail if the backend is not running or database is not set up."
echo "Make sure to run 'make docker-up' first to start the services."