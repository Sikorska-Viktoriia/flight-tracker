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

func consumePostgresTasks(databaseURL string, handler *statsHandler, ready *atomic.Bool) error {
	if databaseURL == "" {
		return errors.New("DATABASE_URL is required when STORAGE_BACKEND uses PostgreSQL")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		return fmt.Errorf("connect to PostgreSQL task queue: %w", err)
	}
	defer pool.Close()

	if err := pool.Ping(ctx); err != nil {
		return fmt.Errorf("check PostgreSQL task queue connection: %w", err)
	}
	if _, err := pool.Exec(ctx, "SELECT correlation_id FROM fetcher_tasks LIMIT 0"); err != nil {
		return fmt.Errorf("check PostgreSQL task queue table: %w", err)
	}
	listener, err := pgx.Connect(ctx, databaseURL)
	if err != nil {
		return fmt.Errorf("connect to PostgreSQL task notifications: %w", err)
	}
	defer listener.Close(ctx)
	if _, err := listener.Exec(ctx, "LISTEN fetcher_tasks"); err != nil {
		return fmt.Errorf("listen for PostgreSQL task notifications: %w", err)
	}
	notifications := make(chan struct{}, 1)
	listenerErrors := make(chan error, 1)
	go func() {
		for {
			if _, waitErr := listener.WaitForNotification(ctx); waitErr != nil {
				listenerErrors <- waitErr
				return
			}
			select {
			case notifications <- struct{}{}:
			default:
			}
		}
	}()

	ready.Store(true)
	log.Printf("consuming snapshot requests from PostgreSQL task queue")
	defer ready.Store(false)

	cleanupTicker := time.NewTicker(time.Minute)
	defer cleanupTicker.Stop()
	lastCleanup := time.Now()
	for {
		cleanupExpiredTasks := func() error {
			if _, err := pool.Exec(ctx, "DELETE FROM fetcher_tasks WHERE expires_at <= NOW()"); err != nil {
				return err
			}
			lastCleanup = time.Now()
			return nil
		}
		if time.Since(lastCleanup) >= time.Minute {
			if err := cleanupExpiredTasks(); err != nil {
				return fmt.Errorf("remove expired PostgreSQL queue tasks: %w", err)
			}
		}

		var correlationID string
		var payload string
		err := pool.QueryRow(ctx, `
			WITH next_task AS (
				SELECT correlation_id
				FROM fetcher_tasks
				WHERE response IS NULL
				  AND expires_at > NOW()
				  AND (claimed_at IS NULL OR claimed_at < NOW() - INTERVAL '1 minute')
				ORDER BY created_at
				LIMIT 1
				FOR UPDATE SKIP LOCKED
			)
			UPDATE fetcher_tasks AS task
			SET claimed_at = NOW()
			FROM next_task
			WHERE task.correlation_id = next_task.correlation_id
			RETURNING task.correlation_id, task.payload::text
		`).Scan(&correlationID, &payload)

		if errors.Is(err, pgx.ErrNoRows) {
			select {
			case <-notifications:
			case waitErr := <-listenerErrors:
				return fmt.Errorf("wait for PostgreSQL task notification: %w", waitErr)
			case <-cleanupTicker.C:
				if err := cleanupExpiredTasks(); err != nil {
					return fmt.Errorf("remove expired PostgreSQL queue tasks: %w", err)
				}
			}
			continue
		}
		if err != nil {
			return fmt.Errorf("claim PostgreSQL queue task: %w", err)
		}

		response := processTaskPayload([]byte(payload), handler)
		body, err := json.Marshal(response)
		if err != nil {
			return fmt.Errorf("encode Fetcher response: %w", err)
		}

		result, err := pool.Exec(ctx, `
			UPDATE fetcher_tasks
			SET response = $2::jsonb, claimed_at = NULL
			WHERE correlation_id = $1 AND expires_at > NOW()
		`, correlationID, body)
		if err != nil {
			return fmt.Errorf("publish PostgreSQL queue response: %w", err)
		}
		if result.RowsAffected() == 0 {
			log.Printf("discarding response for expired PostgreSQL queue task %s", correlationID)
		}
	}
}
