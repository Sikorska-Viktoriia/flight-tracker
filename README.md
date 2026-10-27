# Flight Tracker

Flight Tracker collects ADS-B aircraft data, stores periodic snapshots, and serves a live dashboard. Its runtime separates the Go data fetcher, FastAPI read API, collector worker, PostgreSQL, one-shot migration job, and static web frontend.

## Architecture

```text
flight-tracker/
├── database/
│   ├── init/                  # Initial restricted application role
│   └── migrations/            # Versioned PostgreSQL schema
│   ├── extensions/            # Privileged setup for pgmq and pg_cron
│   └── Dockerfile             # PostgreSQL image with optional extension support
├── configs/                   # Static PostgreSQL, Redis, SSH, and systemd configuration
├── compose/
│   └── vagrant/
│       ├── services/          # One Vagrant Compose file per container service
│       └── volumes.yml        # Shared persistent volumes
├── fetcher/                   # Go client for ADS-B.lol
├── frontend/                  # Static dashboard and Nginx reverse proxy
│   ├── assets/css/app.css     # Dashboard styles
│   ├── assets/js/app.js       # Dashboard behavior
│   └── index.html             # Page structure and content
├── history/
│   ├── app/
│   │   ├── api/               # HTTP routes and dependency wiring
│   │   ├── config/            # Validated environment settings
│   │   ├── core/              # Logging and compatibility imports
│   │   ├── db/                # Pool and migration runner
│   │   ├── factories/         # Runtime backend selection
│   │   ├── interfaces/        # Queue and cache contracts
│   │   ├── repositories/      # SQL and database mapping
│   │   ├── schemas/           # Validated request and response data
│   │   ├── services/          # RabbitMQ/Postgres queue, Redis/Postgres cache, use cases
│   │   ├── main.py            # FastAPI application factory
│   │   └── worker.py          # Standalone collector process
│   ├── tests/
│   └── Dockerfile
├── provision/
│   └── bastion/               # Restricted Bastion key provisioning
├── scripts/provision/         # Shared helpers for database and application VM provisioning
├── vagrant/nodes.rb           # VM and network definitions
├── docker-compose.yml
├── pyproject.toml
└── run-local.sh
```

The API process does not run the collector. This prevents duplicate polling when the API is restarted or scaled. Compose runs the migration job before starting the API and collector. Database changes belong in new, sequential SQL migration files; do not edit migrations already applied to a database. Applied migrations are checksum-verified.

## Data flow

The History collector requests a snapshot through the selected queue; the Fetcher consumes the task, requests aircraft data from ADS-B.lol, and publishes a correlated response back through that queue. History validates the response and is the only service that writes flight snapshots to PostgreSQL. The queue is RabbitMQ in `standalone`, a PostgreSQL SQL queue in `postgres_native`, or PGMQ in `postgres_extensions`. History and Fetcher do not exchange data over HTTP; the Fetcher's HTTP endpoint is only a health check.

```text
Browser ──HTTP──> History API ──SQL──> PostgreSQL snapshots
   │                    └────────────> selected session/cache backend
   └──map tiles────────> CARTO

History collector ──task──> selected queue ──task──> Go Fetcher ──HTTP──> ADS-B.lol
History collector <─reply── selected queue <─reply── Go Fetcher
History collector ──validated snapshot──────────────────────────────> PostgreSQL
```

By default, ADS-B requests cover a 250-nautical-mile radius around Central Europe (`51.75, 19.0`). The Fetcher converts altitude, speed, and vertical rate to meters, meters per second, and meters per second. The collector requests new data every five minutes and writes new snapshots to PostgreSQL. The browser refreshes dashboard data every 15 seconds.

The Fetcher caches its response for five minutes. If ADS-B.lol returns `429` or `420`, it waits at least 15 minutes or the supplied `Retry-After`, whichever is longer. The last cached response remains available during a rate limit. Redis stores each browser's UI theme against an opaque, HTTP-only session cookie; PostgreSQL can be selected instead for this expiring key-value data. No preference data is placed in the cookie. Session records expire after `SESSION_TTL_SEC` (30 days by default). The dashboard uses CARTO Dark Matter tiles, Leaflet, the Leaflet heat layer, and Chart.js, which require browser internet access. Cloudflare Tunnel and Cloudflare Access are not configured; the dashboard is only available through the configured local/Vagrant endpoints.

Select exactly one `STORAGE_BACKEND` mode. `standalone` (the default) uses RabbitMQ for task/reply messages and Redis for browser sessions. `postgres_native` uses a PostgreSQL TTL key-value table and a durable SQL queue claimed with `FOR UPDATE SKIP LOCKED`; `LISTEN/NOTIFY` wakes queue consumers and request/reply waiters. It requires no PostgreSQL extensions and does not start RabbitMQ or Redis. Its cache table is `UNLOGGED`, so keys are intentionally discarded after a PostgreSQL crash or restart. `postgres_extensions` uses the same PostgreSQL cache, PGMQ for durable messages, and pg_cron for periodic cleanup. Only this mode preloads pg_cron, creates either extension, and schedules cleanup. The same `STORAGE_BACKEND` setting selects the queue and cache together for the Go Fetcher, collector, API, and deployment scripts; it is a configuration choice, not a runtime fallback.

The History application's backend contract lives in `history/app/interfaces/`. Runtime settings are validated in `history/app/config/settings.py`; `history/app/factories/` chooses the backend, and each implementation has its own file in `history/app/services/`. `MessageQueue` models this application's request/reply snapshot operation rather than exposing unused generic `ack` methods.

### PostgreSQL queue/cache backends

The native queue's rows are the durable source of truth; notifications only reduce consumer and waiter latency and are safe to miss because both sides re-read the tables. The extension mode creates `pgmq` and `pg_cron` with privileged bootstrap SQL before running application migrations. The PostgreSQL entrypoint adds the pg_cron preload only for `postgres_extensions`; native and standalone database startup do not depend on it. PostgreSQL, Redis, and RabbitMQ listen on the internal Vagrant subnet; the static `configs/postgresql/pg_hba.conf` explicitly allows the VM subnet and Docker bridge networks.

The dashboard uses a dark map, selectable aircraft details, callsign/ICAO search, altitude and ADS-B category filters, emergency-squawk highlighting, flight trails, a 1-hour/24-hour aggregated traffic-density layer, sortable live aircraft rows, and a dual-series traffic/average-altitude chart. The aircraft categories are the source's ADS-B emitter categories, not a reliable cargo/business-jet classification. The timeline endpoint provides up to the latest 120 saved snapshots from the last 60 minutes for playback; playback controls step through actual saved positions at 1×/5×/10× elapsed time, not interpolated or simulated tracks. ADS-B.lol positions do not include reliable airport pairs, schedules, or model photographs, so route and schedule data are explicitly shown as unavailable rather than inferred.

## Local development

Requirements: Go 1.22+, Python 3.10+, and local PostgreSQL. RabbitMQ and Redis are required only when their PostgreSQL alternatives are disabled. Use the full Compose stack below if you prefer to run the dependencies and application in containers.

Copy `.env.example` to `.env`, set unique database, RabbitMQ, and Redis passwords, and set `DATABASE_URL` to your database connection string. For local development, set `AMQP_URL` to `amqp://flightapp:<rabbitmq-password>@127.0.0.1:5672/` and `REDIS_URL` to `redis://:<redis-password>@127.0.0.1:6379/0`. Use URL-safe, at least 16-character broker/cache passwords or URL-encode reserved characters in connection strings.

```sh
python3 -m venv history/.venv
history/.venv/bin/pip install -r history/requirements-dev.txt
```

Each command starts only one process. Run them in separate terminal windows:

```sh
./run-local.sh fetcher
./run-local.sh history
./run-local.sh collector
```

Make PostgreSQL and any selected standalone services available on the connection addresses in `.env`, then apply schema changes with `./run-local.sh migrate`. For `postgres_extensions`, use the Compose PostgreSQL image or another PostgreSQL installation with both extensions installed and pg_cron preloaded. The launcher does not install dependencies, build all services, or run readiness checks. Stop each process with `Ctrl+C`.

These services can also be started directly in the terminal without the launcher. First export `.env` using `set -a; source .env; set +a`, then run one command per terminal:

```sh
cd fetcher && go run .
history/.venv/bin/uvicorn history.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
history/.venv/bin/python -m history.app.worker
history/.venv/bin/python -m history.app.db.migrate
```

For example, override the UI port with `PORT=8003 ./run-local.sh history`.

To set up PostgreSQL on Ubuntu/Debian:

```sh
sudo apt update
sudo apt install postgresql postgresql-client python3 python3-venv
sudo systemctl enable --now postgresql
sudo -u postgres psql
```

Create a local application role and database if they do not already exist, using your own password and the same password in `DATABASE_URL`:

```sql
CREATE ROLE flightapp WITH LOGIN PASSWORD '<your-unique-password>';
CREATE DATABASE flightdb OWNER flightapp;
\q
```

### Tests and lint

```sh
history/.venv/bin/pytest
history/.venv/bin/ruff check history
cd fetcher && go test ./...
```

### API endpoints

- `/api/history?limit=25` — recent snapshots; `limit` ranges from 1 to 500.
- `/api/latest` — latest snapshot and aircraft positions.
- `/api/timeline?minutes=60&limit=120` — chronological aircraft snapshots for playback; `minutes` ranges from 1 to 120 and `limit` from 1 to 500.
- `/api/heatmap?hours=1` — aggregated traffic-density cells from the last hour; `hours` supports 1 or 24.
- `/health/live` — process liveness.
- `/health/ready` — database and selected session-store readiness (`/health` remains an alias).
- `/api/session` — read or update the current browser's theme preference.
- `/docs` — interactive API documentation.
- `http://localhost:8081/health` — Fetcher and broker health.

## Docker Compose

```sh
cp .env.example .env
docker compose --env-file .env build
scripts/docker-compose-local.sh up -d
```

`STORAGE_BACKEND=standalone` starts RabbitMQ and Redis. Set `postgres_native` or `postgres_extensions` to omit both services and use PostgreSQL for queue and cache. The custom database image includes optional extension binaries, but `postgres_native` neither preloads nor creates extensions. Build the database image with `docker compose --env-file .env build`; `postgres_extensions` initializes PGMQ/pg_cron before application migrations. Later mode changes take effect with `scripts/docker-compose-local.sh up -d` and do not rebuild. The Go Fetcher and API/collector use the PostgreSQL application role, never the PostgreSQL administrator. Open <http://localhost:8000>; the Fetcher's health endpoint is exposed at <http://localhost:8081/health>. The dashboard port is published on all host interfaces, so other devices on the same LAN can use the host's LAN IP and port 8000, subject to host firewall rules. PostgreSQL, RabbitMQ, Redis, and the backend API are not published to the host. `scripts/docker-compose-local.sh down` preserves database, broker, and cache data; `scripts/docker-compose-local.sh down -v` deletes persistent data.

## Multi-VM Vagrant setup

The minimal `Vagrantfile` loads the VM definitions from `vagrant/nodes.rb` and runs the project across five VirtualBox VMs. Bastion and the application VMs share a named VirtualBox internal network (`10.20.0.0/24`); only the Bastion has a host-facing interface by default. The optional `VAGRANT_BRIDGE` attaches the Bastion to the selected LAN interface, and separately preserves the UI's optional direct LAN access:

| VM | Private IP | Services |
|---|---|---|
| `bastion` | `10.20.0.2` private; `192.168.56.20` host-only | Restricted SSH jump host (384 MB) |
| `database` | `10.20.0.10` | PostgreSQL and, in standalone mode, RabbitMQ and Redis (768 MB) |
| `fetcher` | `10.20.0.11` | Go Fetcher (384 MB) |
| `history` | `10.20.0.12` | FastAPI, Collector, and database migrations (768 MB) |
| `ui` | `10.20.0.13` | Nginx dashboard/API reverse proxy (384 MB) |

All non-UI service ports bind to their private `10.20.0.x` addresses and are unreachable directly from the host. The Bastion exposes only SSH on its host-facing address; the UI remains directly available on host port 8080 (also optionally on the LAN). Each service VM still has Vagrant's NAT management interface, so `vagrant ssh <vm>` and provisioning remain available without opening an application port on the host. Docker Compose starts its role from `compose/vagrant/services/`; shared volume declarations live in `compose/vagrant/volumes.yml`. RabbitMQ and Redis run only with `STORAGE_BACKEND=standalone`. Compose CPU, RAM, and swap ceilings apply to application containers and are limits rather than pre-allocated memory. Redis is capped at 48 MB and evicts least-recently-used expiring session keys if it reaches that cap. Persistent Docker volumes store database, broker, and cache data; Docker rotates container logs at 10 MB, retaining up to three files per container.

Host SSH keys stay on the host. Run `./scripts/configure-host-ssh.sh` to add the SSH aliases, then connect with `ssh database`, `ssh fetcher`, `ssh history`, or `ssh ui`; these use `ProxyJump bastion`. The equivalent explicit form is `ssh -J bastion vagrant@10.20.0.10`. The dedicated `flight-jump` account has `/usr/sbin/nologin`, no agent forwarding or TTY, and authorized-key/sshd `PermitOpen` restrictions allowing TCP forwarding only to the internal VMs' SSH ports. This account cannot open an interactive Bastion session. Private keys are never copied to the Bastion; SSH authenticates to the Bastion and destination from the host. The ordinary Vagrant management user remains separate for `vagrant ssh`. For clients on the LAN, inspect the Bastion's bridged IPv4 address and run `BASTION_HOST=<bastion-LAN-IP> ./scripts/configure-host-ssh.sh`; the default host-only address is `192.168.56.20`.

The static Bastion policy is in `configs/ssh/flight-tracker-jump.conf`; only the host key is inserted into the restricted account's `authorized_keys` during provisioning. Vagrant uses one role-aware entry point, `scripts/provision-vm.sh`, while `scripts/provision/postgres-stack.sh` and `scripts/provision/application-stack.sh` contain only the role-specific stack work.

Vagrant forwards UI port 80 to host port 8080 on all host interfaces, so a phone on the same router can open `http://<host-LAN-IP>:8080`. If port 8080 is occupied, Vagrant reports the conflict. Set `VAGRANT_BRIDGE` to a host LAN interface (for example `wlp2s0`) to attach both Bastion and UI to that LAN; this makes the Bastion's SSH endpoint available there and additionally exposes UI port 80 directly on the LAN.

Prepare the Vagrant environment by creating `.env` from `.env.example` if it does not exist; otherwise, update the existing file without overwriting it. Set unique `APP_DB_PASSWORD` and `POSTGRES_PASSWORD` values and select `STORAGE_BACKEND`. For standalone mode, provide RabbitMQ and Redis passwords; PostgreSQL modes require `DATABASE_URL` set to `postgresql://flightapp:<URL-encoded-app-password>@10.20.0.10:5432/flightdb`. The database VM initializes PGMQ/pg_cron only for `postgres_extensions`; `postgres_native` applies its SQL queue/cache migrations without extensions. Then run:

```sh
vagrant up
```

The History VM syncs both `history/` and `database/`; the database VM also syncs `history/` so it can apply queue/cache migrations before the Fetcher VM starts. The `database` VM is the central log collector: a systemd timer runs every 15 minutes and gathers status from the four application VMs plus container logs from each service. This timer replaces a cron job while using the same periodic scheduling model. On first `vagrant up`, Vagrant provisions the Bastion first and the `database` VM before the logger client VMs: the database creates a dedicated Ed25519 key pair and shares only its public key with the other VMs. This key is separate from your host SSH key and is restricted on client VMs to running allowlisted status or per-service log commands; it cannot open an interactive SSH session. The logger records Compose/container health, container CPU and memory, VM memory, and disk usage to `/var/log/flight-tracker/metrics.log`. Container stdout/stderr logs from all VMs are collected on `database` into separate files under `/var/log/flight-tracker/containers/<vm>/<service>.log`. Each service has its own timestamp cursor so successful collections retrieve only newer logs; a new service starts with a 16-minute initial window. Log files are rotated daily, compressed, and retained for seven rotations.

Provision the running VMs in this order so the dependencies are available before their clients and the logger key exists before client provisioning:

```sh
vagrant ssh history -c "sudo systemctl disable --now flight-tracker-history.service flight-tracker-collector.service"
vagrant reload bastion --provision
vagrant reload database --provision
vagrant reload fetcher --provision
vagrant reload history --provision
vagrant reload ui --provision
```

After provisioning, inspect logger runs with `vagrant ssh database -c "sudo journalctl -u flight-tracker-logger.service -n 100"`, metrics with `vagrant ssh database -c "sudo tail -n 100 /var/log/flight-tracker/metrics.log"`, or a service log such as `vagrant ssh database -c "sudo tail -n 200 /var/log/flight-tracker/containers/history/history.log"`. Check the schedule with `vagrant ssh database -c "systemctl list-timers flight-tracker-logger.timer"`; run a collection immediately with `vagrant ssh database -c "sudo systemctl start flight-tracker-logger.service"`. The logger's private key stays on the database VM at `/var/lib/flight-tracker-logger/id_ed25519`; its public key is `/var/lib/flight-tracker-logger/id_ed25519.pub` and is shared to client VMs at `/opt/flight-tracker/logger/public/id_ed25519.pub`. It SSHes as `vagrant` to each VM's private address, where `authorized_keys` forces requests through `/usr/local/sbin/flight-tracker-logger-remote`. If the database VM is destroyed and recreated, reprovision the other VMs so they install its newly generated public key. Recreated client VMs may also require removing their old host key from `/var/lib/flight-tracker-logger/known_hosts` on the database VM.

When converting an existing systemd-based installation, first stop its History API and Collector as shown above so they release their PostgreSQL connections during the database restore. The database provisioning step backs up the existing `POSTGRES_DB` with `pg_dump`, starts the Docker database and restores the dump once. The backup is retained at `/var/lib/flight-tracker/postgres.dump` inside the `database` VM. Keep it until the new stack has been verified. Redis session preferences and queued RabbitMQ messages are not imported; the Redis cache and broker start with fresh Docker volumes. Switching between legacy and PostgreSQL backends does not migrate existing cache entries or in-flight requests. If provisioning fails during the database restore, keep the dump and inspect logs with `./scripts/vagrant-logs.sh database db` before retrying.

Use `./scripts/vagrant-status.sh` to check each VM's power state; on Bastion it reports SSH service and network addresses, and on application VMs it reports Compose health, container CPU/memory, VM memory, and disk usage. Use `./scripts/vagrant-logs.sh <database|fetcher|history|ui>` to show the last 100 log lines for that VM; add a service name (for example, `history collector`) to filter logs or `--follow` to stream them. Logs can also be inspected inside a VM with `sudo /opt/flight-tracker/scripts/docker-compose-vagrant.sh --profile <name> logs --timestamps --tail=100 <service>`. Open the site at `http://<host-LAN-IP>:8080` from a phone connected to the same Wi-Fi. If it does not respond, check `./scripts/vagrant-status.sh` and `./scripts/vagrant-logs.sh ui`, ensure host port 8080 is free, then run `vagrant reload ui --provision`.

Manage a VM independently with `vagrant up bastion`, `vagrant up database`, `vagrant up fetcher`, `vagrant up history`, or `vagrant up ui`. Use `vagrant halt <name>` or `vagrant reload <name>` to control one VM, and `vagrant destroy <name>` to remove it. Project folders are synced only to VMs that need them; `.env` is provisioned only to the database, Fetcher, and History VMs.

Provisioning configures the broker and cache with dedicated passwords and binds Redis to the VM network; the only browser-reachable service is the UI on port 80. PostgreSQL accepts connections from the Vagrant private subnet.

### SSH access by VM name

Vagrant provisioning installs the host's public key in the `vagrant` account on every VM. By default, it selects the first available key from `~/.ssh/id_ed25519.pub`, `~/.ssh/id_ecdsa.pub`, then `~/.ssh/id_rsa.pub`. To use a different public key, set `VAGRANT_SSH_PUBLIC_KEY` to its path when running Vagrant, for example `VAGRANT_SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" vagrant up --provision`. The matching private key stays on the host.

Configure regular SSH aliases once with:

```sh
./scripts/configure-host-ssh.sh
```

The script verifies the matching private key and adds or updates only its marked block in `~/.ssh/config`. Each VM gets a separate host-key alias, so pre-existing `known_hosts` entries for these private IP addresses are left untouched. If using a non-default private-key filename, pass it as the first argument. Connect with `ssh database`, `ssh fetcher`, `ssh history`, or `ssh ui`; `vagrant ssh <name>` remains available too.

### Recover an existing database volume when its admin role is unknown

PostgreSQL only processes `database/init/` scripts when it initializes an empty volume. Changing `POSTGRES_USER` or its password in `.env` does not add, rename, or reset roles in an existing database. If the old administrator credentials are unavailable and the logs say that `flightapp` does not exist, you can add the application role through PostgreSQL single-user mode without deleting the database volume.

First, make sure `.env` contains the application credentials below. Replace the password placeholder with a unique password and use that same password in the SQL command:

```dotenv
POSTGRES_DB=flightdb
APP_DB_USER=flightapp
APP_DB_PASSWORD=REPLACE_WITH_UNIQUE_PASSWORD
```

Stop only this Compose project's database, then back up its stopped data volume:

```sh
docker compose stop db
mkdir -p "$HOME/flight-tracker-backups"
docker run --rm --user 0:0 \
  -v flight-tracker_postgres-data:/data:ro \
  -v "$HOME/flight-tracker-backups:/backup" \
  alpine:3.20 \
  tar -czf /backup/flight-tracker-postgres-data.tar.gz -C /data .
```

The default volume name above corresponds to the Compose project name `flight-tracker`. Confirm it with `docker volume ls`; if your volume has a different name, use that exact name instead. Now start PostgreSQL in single-user mode against the same volume and create the missing application role:

```sh
docker run --rm -i --user postgres --workdir /tmp \
  --entrypoint postgres \
  -v flight-tracker_postgres-data:/var/lib/postgresql/data \
  flight-tracker-postgres \
  --single -D /var/lib/postgresql/data flightdb <<'SQL'
CREATE ROLE flightapp WITH LOGIN PASSWORD 'REPLACE_WITH_UNIQUE_PASSWORD';
GRANT CONNECT ON DATABASE flightdb TO flightapp;
GRANT USAGE, CREATE ON SCHEMA public TO flightapp;
SQL
```

This recovery does not delete the database or its volume. Start the Compose services again:

```sh
scripts/docker-compose-local.sh up -d
```

If the command reports that `flightapp` already exists, stop here and share that exact error rather than deleting the volume. For a non-default database name or credentials, make the role, password, database, and volume name in these commands match `.env`.

## Configuration

See `.env.example` for Vagrant and Compose settings. `POSTGRES_USER`/`POSTGRES_PASSWORD` are Compose database bootstrap credentials; `APP_DB_USER`/`APP_DB_PASSWORD` are the restricted application credentials. Important variables also include `STORAGE_BACKEND`, `DATABASE_URL`, `AMQP_URL`, `REDIS_URL`, `RABBITMQ_USER`/`RABBITMQ_PASSWORD`, `REDIS_PASSWORD`, `SESSION_TTL_SEC`, `POLL_INTERVAL_SEC`, `FETCHER_TIMEOUT_SEC`, `PORT`, `FETCHER_PORT`, `FLIGHT_API_URL`, and `FLIGHT_API_CACHE_SEC`. Inside Compose, services use internal DNS names; do not use `localhost` to connect between containers.
