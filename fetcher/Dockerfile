FROM golang:1.22-alpine AS builder

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY *.go ./

RUN CGO_ENABLED=0 go build -o /bin/fetcher .

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

COPY --from=builder /bin/fetcher /usr/local/bin/fetcher

EXPOSE 8081

ENTRYPOINT ["/usr/local/bin/fetcher"]