package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"math"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	rateLimitCooldown  = 15 * time.Minute
	feetToMeters       = 0.3048
	feetPerMinuteToMPS = 0.00508
	knotsToMPS         = 0.514444
)

type statsHandler struct {
	client     *http.Client
	apiURL     string
	cacheTTL   time.Duration
	mu         sync.Mutex
	cached     flightStats
	cachedAt   time.Time
	retryAfter time.Time
}

func newStatsHandler(apiURL string, cacheTTL time.Duration) *statsHandler {
	return &statsHandler{
		client:   &http.Client{Timeout: 12 * time.Second},
		apiURL:   apiURL,
		cacheTTL: cacheTTL,
	}
}

func (h *statsHandler) getStats(ctx context.Context) (flightStats, string, time.Duration, error) {
	h.mu.Lock()
	defer h.mu.Unlock()

	now := time.Now()
	if !h.cachedAt.IsZero() && now.Before(h.cachedAt.Add(h.cacheTTL)) {
		return h.cached, "HIT", 0, nil
	}
	if now.Before(h.retryAfter) {
		if !h.cachedAt.IsZero() {
			return h.cached, "STALE", 0, nil
		}
		return flightStats{}, "", time.Until(h.retryAfter),
			errors.New("flight data API temporarily unavailable; retry later")
	}

	result, retryDelay, err := h.fetchStats(ctx)
	if err != nil {
		h.retryAfter = time.Now().Add(h.cacheTTL)
		if retryDelay > h.cacheTTL {
			h.retryAfter = time.Now().Add(retryDelay)
		}
		if !h.cachedAt.IsZero() {
			log.Printf(
				"flight data refresh failed; serving cached data until %s: %v",
				h.retryAfter.Format(time.RFC3339),
				err,
			)
			return h.cached, "STALE", 0, nil
		}
		return flightStats{}, "", time.Until(h.retryAfter), err
	}

	h.cached = result
	h.cachedAt = time.Now()
	h.retryAfter = time.Time{}
	return result, "MISS", 0, nil
}

func (h *statsHandler) fetchStats(ctx context.Context) (flightStats, time.Duration, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, h.apiURL, nil)
	if err != nil {
		return flightStats{}, 0, fmt.Errorf("create flight data request: %w", err)
	}
	request.Header.Set("User-Agent", "flight-tracker/1.0")

	response, err := h.client.Do(request)
	if err != nil {
		return flightStats{}, 0, fmt.Errorf("request flight data API: %w", err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		retryDelay := time.Duration(0)
		if response.StatusCode == http.StatusTooManyRequests || response.StatusCode == 420 {
			retryDelay = rateLimitCooldown
			if fromHeader := parseRetryAfter(response.Header.Get("Retry-After"), time.Now()); fromHeader > retryDelay {
				retryDelay = fromHeader
			}
		}
		return flightStats{}, retryDelay, fmt.Errorf("flight data API returned %s", response.Status)
	}

	var payload adsbResponse
	decoder := json.NewDecoder(http.MaxBytesReader(nil, response.Body, 20<<20))
	if err := decoder.Decode(&payload); err != nil {
		return flightStats{}, 0, fmt.Errorf("decode flight data API response: %w", err)
	}

	return summarizeADSB(payload), 0, nil
}

func summarizeADSB(payload adsbResponse) flightStats {
	result := flightStats{
		CollectedAt: time.Now().UTC(),
		Aircraft:    make([]aircraftPosition, 0, len(payload.Aircraft)),
	}
	if timestamp, err := payload.Now.Float64(); err == nil && timestamp > 0 {
		result.CollectedAt = time.UnixMilli(int64(timestamp)).UTC()
	}

	var speedTotal float64
	var speedCount int
	for _, plane := range payload.Aircraft {
		if string(plane.BaroAlt) == `"ground"` {
			continue
		}

		altitudeFeet, hasAltitude := numericJSON(plane.BaroAlt)
		if !hasAltitude {
			altitudeFeet, hasAltitude = numericJSON(plane.GeomAlt)
		}
		altitudeM := 0.0
		if hasAltitude {
			altitudeM = altitudeFeet * feetToMeters
			if altitudeM > result.MaxAltitudeM {
				result.MaxAltitudeM = altitudeM
				result.TopFlightCallsign = strings.TrimSpace(plane.Callsign)
			}
		}

		if plane.GroundSpeed != nil && *plane.GroundSpeed > 0 {
			speedTotal += *plane.GroundSpeed * knotsToMPS
			speedCount++
		}
		result.TotalAirborne++
		if plane.Latitude == nil || plane.Longitude == nil ||
			*plane.Latitude < -90 || *plane.Latitude > 90 ||
			*plane.Longitude < -180 || *plane.Longitude > 180 {
			continue
		}
		speedMPS := 0.0
		if plane.GroundSpeed != nil {
			speedMPS = *plane.GroundSpeed * knotsToMPS
		}
		heading := 0.0
		if plane.Track != nil {
			heading = *plane.Track
		}
		var verticalRateMPS *float64
		if plane.BaroRate != nil {
			rate := *plane.BaroRate * feetPerMinuteToMPS
			verticalRateMPS = &rate
		}
		result.Aircraft = append(result.Aircraft, aircraftPosition{
			ICAO24:          plane.ICAO24,
			Callsign:        strings.TrimSpace(plane.Callsign),
			Country:         plane.Country,
			Longitude:       *plane.Longitude,
			Latitude:        *plane.Latitude,
			AltitudeM:       altitudeM,
			SpeedMPS:        speedMPS,
			HeadingDeg:      heading,
			AircraftType:    strings.TrimSpace(plane.AircraftType),
			Category:        strings.TrimSpace(plane.Category),
			Squawk:          strings.TrimSpace(plane.Squawk),
			VerticalRateMPS: verticalRateMPS,
		})
	}
	if speedCount > 0 {
		result.AverageSpeedMPS = speedTotal / float64(speedCount)
	}
	return result
}

func numericJSON(value json.RawMessage) (float64, bool) {
	if len(value) == 0 || string(value) == "null" {
		return 0, false
	}
	var number float64
	if err := json.Unmarshal(value, &number); err != nil || math.IsNaN(number) || math.IsInf(number, 0) {
		return 0, false
	}
	return number, true
}

func parseRetryAfter(value string, now time.Time) time.Duration {
	if seconds, err := strconv.Atoi(strings.TrimSpace(value)); err == nil && seconds > 0 {
		return time.Duration(seconds) * time.Second
	}
	if retryTime, err := http.ParseTime(value); err == nil && retryTime.After(now) {
		return retryTime.Sub(now)
	}
	return 0
}
