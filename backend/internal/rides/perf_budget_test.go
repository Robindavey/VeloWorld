package rides

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func sampleCreateRideJSON() string {
	routeID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	req := CreateRideRequest{
		RouteID:        &routeID,
		DurationS:      3600,
		DistanceM:      25000,
		ElevationGainM: 390,
		AvgPowerW:      220,
		AvgSpeedKph:    24.7,
		MaxPowerW:      780,
		MaxSpeedKph:    63.1,
		TotalEnergyKj:  792,
	}
	raw, _ := json.Marshal(req)
	return string(raw)
}

func benchmarkDecodeCreateRideRequest(b *testing.B) {
	raw := sampleCreateRideJSON()
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var req CreateRideRequest
		if err := json.NewDecoder(strings.NewReader(raw)).Decode(&req); err != nil {
			b.Fatalf("decode failed: %v", err)
		}
	}
}

func BenchmarkDecodeCreateRideRequest(b *testing.B) {
	benchmarkDecodeCreateRideRequest(b)
}

func TestCreateRideDecodeBudget(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping perf budget in short mode")
	}

	res := testing.Benchmark(benchmarkDecodeCreateRideRequest)
	const nsPerOpBudget = int64(600_000) // 0.6ms max for API request decode
	if res.NsPerOp() > nsPerOpBudget {
		t.Fatalf("create-ride decode budget exceeded: got %s (%d ns/op), budget %d ns/op", res, res.NsPerOp(), nsPerOpBudget)
	}
}
