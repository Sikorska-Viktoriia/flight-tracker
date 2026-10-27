package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"sync/atomic"

	amqp "github.com/rabbitmq/amqp091-go"
)

const taskQueueMessageTTLMillis = int32(60_000)

func consumeTasks(amqpURL string, handler *statsHandler, ready *atomic.Bool) error {
	connection, err := amqp.Dial(amqpURL)
	if err != nil {
		return fmt.Errorf("connect to RabbitMQ: %w", err)
	}
	defer connection.Close()

	channel, err := connection.Channel()
	if err != nil {
		return fmt.Errorf("open RabbitMQ channel: %w", err)
	}
	defer channel.Close()

	queueName := env("FETCHER_TASK_QUEUE", "flight-tracker.fetcher.tasks")
	queue, err := channel.QueueDeclare(
		queueName,
		true,
		false,
		false,
		false,
		amqp.Table{"x-message-ttl": taskQueueMessageTTLMillis},
	)
	if err != nil {
		return fmt.Errorf("declare Fetcher task queue: %w", err)
	}
	if err := channel.Qos(1, 0, false); err != nil {
		return fmt.Errorf("configure Fetcher task queue: %w", err)
	}
	if err := channel.Confirm(false); err != nil {
		return fmt.Errorf("enable RabbitMQ publisher confirms: %w", err)
	}
	confirmations := channel.NotifyPublish(make(chan amqp.Confirmation, 1))
	deliveries, err := channel.Consume(queue.Name, "", false, false, false, false, nil)
	if err != nil {
		return fmt.Errorf("consume Fetcher task queue: %w", err)
	}
	ready.Store(true)
	log.Printf("consuming snapshot requests from %s", queue.Name)
	defer ready.Store(false)

	for delivery := range deliveries {
		response := processTaskPayload(delivery.Body, handler)
		if delivery.ReplyTo != "" {
			body, marshalErr := json.Marshal(response)
			if marshalErr != nil {
				return fmt.Errorf("encode Fetcher response: %w", marshalErr)
			}
			if err := channel.PublishWithContext(
				context.Background(),
				"",
				delivery.ReplyTo,
				false,
				false,
				amqp.Publishing{
					ContentType:   "application/json",
					CorrelationId: delivery.CorrelationId,
					Body:          body,
				},
			); err != nil {
				_ = delivery.Nack(false, true)
				return fmt.Errorf("publish Fetcher response: %w", err)
			}
			confirmation := <-confirmations
			if !confirmation.Ack {
				_ = delivery.Nack(false, true)
				return errors.New("RabbitMQ did not confirm Fetcher response")
			}
		} else {
			log.Printf("discarding snapshot request without a reply queue")
		}
		if err := delivery.Ack(false); err != nil {
			return fmt.Errorf("acknowledge Fetcher task: %w", err)
		}
	}
	return errors.New("RabbitMQ task queue consumer stopped")
}
