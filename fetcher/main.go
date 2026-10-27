package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
	"time"
)

const defaultFlightAPIURL = "https://api.adsb.lol/v2/lat/51.75/lon/19/dist/250"

func main() {
	port := env("PORT", "8081")
	portNumber, err := strconv.Atoi(port)
	if err != nil || portNumber < 1 || portNumber > 65535 {
		log.Fatalf("PORT must be a port number between 1 and 65535: %q", port)
	}

	apiURL := env("FLIGHT_API_URL", defaultFlightAPIURL)
	cacheSeconds, err := strconv.Atoi(env("FLIGHT_API_CACHE_SEC", "300"))
	if err != nil || cacheSeconds < 1 {
		log.Fatal("FLIGHT_API_CACHE_SEC must be a positive number of seconds")
	}

	amqpURL := env("AMQP_URL", "amqp://guest:guest@localhost:5672/")
	storageBackend := env("STORAGE_BACKEND", "standalone")
	if storageBackend != "standalone" &&
		storageBackend != "postgres_native" &&
		storageBackend != "postgres_extensions" {
		log.Fatalf("STORAGE_BACKEND must be standalone, postgres_native, or postgres_extensions")
	}

	handler := newStatsHandler(apiURL, time.Duration(cacheSeconds)*time.Second)
	var ready atomic.Bool

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		if !ready.Load() {
			http.Error(w, "fetcher is not connected to its configured task queue", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok\n"))
	})

	server := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		if err := server.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("health server failed: %v", err)
		}
	}()
	log.Printf("fetcher health endpoint listening on :%s; flight data URL: %s", port, apiURL)

	if storageBackend == "postgres_native" || storageBackend == "postgres_extensions" {
		if storageBackend == "postgres_extensions" {
			if err := consumePgmqTasks(env("DATABASE_URL", ""), handler, &ready); err != nil {
				log.Fatal(err)
			}
			return
		}
		if err := consumePostgresTasks(env("DATABASE_URL", ""), handler, &ready); err != nil {
			log.Fatal(err)
		}
		return
	}

	if err := consumeTasks(amqpURL, handler, &ready); err != nil {
		log.Fatal(err)
	}
}

func processTaskPayload(body []byte, handler *statsHandler) fetchResponse {
	var request fetchRequest
	if err := json.Unmarshal(body, &request); err != nil {
		return fetchResponse{Status: http.StatusBadRequest, Error: "invalid task payload"}
	}
	if request.Action != "fetch_snapshot" {
		return fetchResponse{Status: http.StatusBadRequest, Error: "unsupported task action"}
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	snapshot, _, retryAfter, err := handler.getStats(ctx)
	if err != nil {
		return fetchResponse{
			Status:     http.StatusServiceUnavailable,
			RetryAfter: max(1, int(retryAfter.Seconds())),
			Error:      err.Error(),
		}
	}
	return fetchResponse{Status: http.StatusOK, Snapshot: &snapshot}
}

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
