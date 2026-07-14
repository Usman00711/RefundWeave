# RefundWeave deployment runbook

The production stack is designed for a small Linux virtual machine with Docker Compose
and a public domain. Caddy is the only public service. It provisions and renews HTTPS
certificates automatically, while the API and MySQL remain on private Docker networks.

## 1. Publish a version

1. Push the completed changes and confirm the GitHub `CI` workflow is green.
2. Create a GitHub release with a semantic tag such as `v1.0.0`.
3. The `Publish containers` workflow publishes these images to GHCR:
   - `ghcr.io/usman00711/refundweave-api:1.0.0`
   - `ghcr.io/usman00711/refundweave-web:1.0.0`
4. Make both packages public from the repository's **Packages** settings, or authenticate
   Docker on the server before pulling private packages.

Manual workflow runs publish only a commit-SHA tag. Releases additionally publish the
semantic version and update `latest` when the release is not a prerelease.

## 2. Prepare a server

Use a Linux server with Docker Engine, the Compose plugin, ports 80/443 open, and a DNS
`A`/`AAAA` record for the chosen domain pointing to the server.

Copy these files to one directory on the server:

- `compose.production.yaml`
- `deploy/Caddyfile`
- `.env.production.example`

Create the production environment file and restrict it to the server owner:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Generate two different URL-safe database passwords, add the OpenRouter key, set the
real domain, and pin both image variables to the release version. Never commit
`.env.production`.

## 3. Start and validate

```bash
docker compose --env-file .env.production -f compose.production.yaml pull
docker compose --env-file .env.production -f compose.production.yaml up -d
docker compose --env-file .env.production -f compose.production.yaml ps
```

Migrations run before the idempotent demo-data seed, then the API, web server, and HTTPS
proxy start in health order. Validate from another machine:

```bash
curl --fail https://YOUR_DOMAIN/health
curl --fail https://YOUR_DOMAIN/api/v1/health
```

The portal is available at `https://YOUR_DOMAIN` and API documentation at
`https://YOUR_DOMAIN/api/docs`.

## 4. Upgrade or roll back

Set both image variables in `.env.production` to the same new or previous version, then:

```bash
docker compose --env-file .env.production -f compose.production.yaml pull
docker compose --env-file .env.production -f compose.production.yaml up -d
```

Database migrations are forward-only during normal startup. Take a backup before an
upgrade that changes the schema.

## 5. Backup and operations

Create a database backup without exposing MySQL publicly:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec -T mysql \
  sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction refundweave' \
  > refundweave-backup.sql
```

Inspect status and logs:

```bash
docker compose --env-file .env.production -f compose.production.yaml ps
docker compose --env-file .env.production -f compose.production.yaml logs -f --tail=200 proxy web api
```

Start the optional Prometheus and Grafana profile:

```bash
docker compose --env-file .env.production -f compose.production.yaml \
  --profile monitoring up -d prometheus grafana
```

Both monitoring ports bind to the server's loopback interface. Access Grafana securely
from your computer without opening port 3000 in the firewall:

```bash
ssh -L 3000:127.0.0.1:3000 YOUR_SERVER
```

Then open `http://localhost:3000`. The Prometheus data source and RefundWeave dashboard
are provisioned automatically from the version-controlled files under `monitoring/`.

Stop containers while preserving database and certificate volumes:

```bash
docker compose --env-file .env.production -f compose.production.yaml down
```

Do not add `--volumes` unless the database and HTTPS state are intentionally being
deleted and a verified backup exists.

## Public-edge security

The Caddy and Nginx layers set a Content Security Policy and browser hardening headers.
The API also rate-limits chat requests per forwarded client address. Keep FastAPI private
behind the configured proxy chain; that is what makes `TRUST_PROXY_HEADERS=true` safe.
Tune `CHAT_RATE_LIMIT_REQUESTS` and `CHAT_RATE_LIMIT_WINDOW_SECONDS` in
`.env.production` if the public demonstration needs a different quota.
