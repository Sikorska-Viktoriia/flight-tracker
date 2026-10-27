package main

import (
	"encoding/json"
	"math"
	"testing"
)

func TestSummarizeADSBIncludesAircraftTelemetry(t *testing.T) {
	var payload adsbResponse
	if err := json.Unmarshal([]byte(`{"ac":[{
		"hex":"abc123","flight":"FLT123 ","t":"A320","category":"A3","squawk":"7700",
		"lon":19.0,"lat":51.75,"alt_baro":30000,"baro_rate":1000,"gs":200,"track":90
	}]}`), &payload); err != nil {
		t.Fatalf("decode ADS-B sample: %v", err)
	}
	snapshot := summarizeADSB(payload)

	if len(snapshot.Aircraft) != 1 {
		t.Fatalf("got %d aircraft, want 1", len(snapshot.Aircraft))
	}
	plane := snapshot.Aircraft[0]
	if plane.AircraftType != "A320" || plane.Category != "A3" || plane.Squawk != "7700" {
		t.Fatalf("unexpected aircraft metadata: %+v", plane)
	}
	if plane.Callsign != "FLT123" {
		t.Fatalf("callsign = %q, want trimmed value", plane.Callsign)
	}
	if plane.VerticalRateMPS == nil || math.Abs(*plane.VerticalRateMPS-5.08) > 0.001 {
		t.Fatalf("vertical rate = %v, want 5.08 m/s", plane.VerticalRateMPS)
	}
}
