package main

import (
	"encoding/json"
	"time"
)

type adsbResponse struct {
	Now      json.Number    `json:"now"`
	Aircraft []adsbAircraft `json:"ac"`
}

type adsbAircraft struct {
	ICAO24       string          `json:"hex"`
	Callsign     string          `json:"flight"`
	Country      string          `json:"r"`
	AircraftType string          `json:"t"`
	Category     string          `json:"category"`
	Squawk       string          `json:"squawk"`
	Longitude    *float64        `json:"lon"`
	Latitude     *float64        `json:"lat"`
	BaroAlt      json.RawMessage `json:"alt_baro"`
	GeomAlt      json.RawMessage `json:"alt_geom"`
	BaroRate     *float64        `json:"baro_rate"`
	GroundSpeed  *float64        `json:"gs"`
	Track        *float64        `json:"track"`
}

type aircraftPosition struct {
	ICAO24          string   `json:"icao24"`
	Callsign        string   `json:"callsign"`
	Country         string   `json:"country"`
	Longitude       float64  `json:"longitude"`
	Latitude        float64  `json:"latitude"`
	AltitudeM       float64  `json:"altitude_m"`
	SpeedMPS        float64  `json:"speed_mps"`
	HeadingDeg      float64  `json:"heading_deg"`
	AircraftType    string   `json:"aircraft_type"`
	Category        string   `json:"category"`
	Squawk          string   `json:"squawk"`
	VerticalRateMPS *float64 `json:"vertical_rate_mps"`
}

type flightStats struct {
	CollectedAt       time.Time          `json:"collected_at"`
	TotalAirborne     int                `json:"total_airborne"`
	AverageSpeedMPS   float64            `json:"average_speed_mps"`
	MaxAltitudeM      float64            `json:"max_altitude_m"`
	TopFlightCallsign string             `json:"top_flight_callsign"`
	Aircraft          []aircraftPosition `json:"aircraft"`
}

type fetchRequest struct {
	Action string `json:"action"`
}

type fetchResponse struct {
	Status     int          `json:"status"`
	RetryAfter int          `json:"retry_after,omitempty"`
	Snapshot   *flightStats `json:"snapshot,omitempty"`
	Error      string       `json:"error,omitempty"`
}
