package routes

import (
	"encoding/json"
	"fmt"
	"testing"

	"github.com/google/uuid"
)

func buildRenderPayload(points int) RouteRenderDataResponse {
	profile := make([]RenderPoint, 0, points)
	for i := 0; i < points; i++ {
		profile = append(profile, RenderPoint{
			DistanceM:  float64(i) * 5,
			ElevationM: 90 + float64(i%150)/4,
			Lat:        45.8 + float64(i)*0.00001,
			Lon:        6.8 + float64(i)*0.00001,
		})
	}

	return RouteRenderDataResponse{
		RouteID:        uuid.MustParse("550e8400-e29b-41d4-a716-446655440000"),
		DistanceM:      float64(points) * 5,
		ElevationGainM: 420.5,
		ProfilePoints:  profile,
	}
}

func benchmarkMarshalRouteRenderData(b *testing.B) {
	payload := buildRenderPayload(1800)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := json.Marshal(payload); err != nil {
			b.Fatalf("marshal failed: %v", err)
		}
	}
}

func BenchmarkMarshalRouteRenderData(b *testing.B) {
	benchmarkMarshalRouteRenderData(b)
}

func TestRouteRenderDataMarshalBudget(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping perf budget in short mode")
	}

	res := testing.Benchmark(benchmarkMarshalRouteRenderData)
	const nsPerOpBudget = int64(8_000_000) // 8ms max for a large render payload
	if res.NsPerOp() > nsPerOpBudget {
		t.Fatalf("render-data marshal budget exceeded: got %s (%d ns/op), budget %d ns/op", res, res.NsPerOp(), nsPerOpBudget)
	}

	payload := buildRenderPayload(1800)
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	const maxBytes = 700_000
	if len(raw) > maxBytes {
		t.Fatalf("render-data payload too large: got %d bytes, budget %d bytes", len(raw), maxBytes)
	}

	t.Logf("route render-data baseline: %s, payload_size=%s", res.String(), fmt.Sprintf("%dB", len(raw)))
}
