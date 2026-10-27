package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"sync/atomic"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const pgmqTaskQueue = "flight_tracker_tasks"

func consumePgmqTasks(databaseURL string, handler *statsHandler, ready *atomic.Bool) error {
	if databaseURL == "" {
		return errors.New("DATABASE_URL is required when STORAGE_BACKEND=postgres_extensions")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		return fmt.Errorf("connect to pgmq: %w", err)
	}
	defer pool.Close()

	if err := pool.Ping(ctx); err != nil {
		return fmt.Errorf("check pgmq connection: %w", err)
	}
	if _, err := pool.Exec(ctx, "SELECT * FROM pgmq.read($1, 30, 1) LIMIT 0", pgmqTaskQueue); err != nil {
		return fmt.Errorf("check pgmq task queue: %w", err)
	}

	ready.Store(true)
	log.Printf("consuming snapshot requests from pgmq queue %s", pgmqTaskQueue)
	defer ready.Store(false)

	for {
		var messageID int64
		var message string
		err := pool.QueryRow(ctx, `
			SELECT msg_id, message::text
			FROM pgmq.read($1, 30, 1)
			LIMIT 1
		`, pgmqTaskQueue).Scan(&messageID, &message)
		if errors.Is(err, pgx.ErrNoRows) {
			time.Sleep(250 * time.Millisecond)
			continue
		}
		if err != nil {
			return fmt.Errorf("read pgmq task: %w", err)
		}

		var task struct {
			CorrelationID string `json:"correlation_id"`
		}
		if err := json.Unmarshal([]byte(message), &task); err != nil {
			return fmt.Errorf("decode pgmq task: %w", err)
		}
		if task.CorrelationID == "" {
			return errors.New("pgmq task is missing correlation_id")
		}

		response, err := json.Marshal(processTaskPayload([]byte(message), handler))
		if err != nil {
			return fmt.Errorf("encode Fetcher response: %w", err)
		}
		_, err = pool.Exec(ctx, `
			INSERT INTO fetcher_responses (correlation_id, response, expires_at)
			VALUES ($1, $2::jsonb, NOW() + INTERVAL '60 seconds')
			ON CONFLICT (correlation_id) DO UPDATE
			SET response = EXCLUDED.response, expires_at = EXCLUDED.expires_at
		`, task.CorrelationID, response)
		if err != nil {
			return fmt.Errorf("publish pgmq task response: %w", err)
		}
		if _, err := pool.Exec(ctx, "SELECT pgmq.archive($1::text, $2::bigint)", pgmqTaskQueue, messageID); err != nil {
			return fmt.Errorf("archive pgmq task: %w", err)
		}
	}
}
