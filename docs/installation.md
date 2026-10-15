# Installation & Deployment

## First start

Copy `.env.example` to `.env`. Generate two independent values with `openssl rand -hex 32` and use them for `FORGE_SECRET_KEY` and `FORGE_SETUP_TOKEN`. The backend rejects placeholder or short application secrets.

```bash
docker compose up --build -d
docker compose ps
```

Open <http://localhost:3000/setup>. Configure the instance name, public origin, default branch, database, and administrator. Use the setup token from `.env`. The first administrator password must contain at least 12 characters. The setup locks after installation. Subsequent users are created by administrators; public registration is disabled.

Sign in and create a repository. Generate a token under **Profile & Access Tokens**, then use your username and token as Git's HTTP credentials. Public repositories allow anonymous clone/fetch. All pushes require a write token and repository write or maintain access. The web application currently requires sign-in even for public repository browsing.

## Database selection

SQLite is the default and stores its database at `/data/forge.db` inside `forge_data`.

For PostgreSQL, replace `POSTGRES_PASSWORD` in `.env`, then run:

```bash
docker compose --profile postgres up --build -d
```

Choose PostgreSQL in setup: host `postgres`, port `5432`, database/user `forge` (or the values from `.env`), and the configured password.

For MariaDB, replace `MARIADB_PASSWORD` and `MARIADB_ROOT_PASSWORD`, then run:

```bash
docker compose --profile mariadb up --build -d
```

Choose MariaDB/MySQL: host `mariadb`, port `3306`, and the database name, user, and password from `.env`. Wait for the database container to become healthy before submitting setup. External servers are also supported. Database creation is the operator's responsibility; setup creates the schema using Alembic.

The selected connection is encrypted in `/data/installation.json`. Preserve `FORGE_SECRET_KEY` for future restarts and restores. Changing database engines after setup requires an explicit data migration; changing Compose profiles does not migrate data.

## Remote access and HTTPS

For remote access, set `FORGE_PUBLIC_URL=https://forge.example.com`, set `FORGE_COOKIE_SECURE=true`, and use the same origin in the setup wizard. For an existing installation, update **Organization & System → Public URL** from the currently configured origin before switching domains. Set `FORGE_BIND_ADDRESS` to the interface on which the frontend should listen. The default binds to loopback only; this permits a host reverse proxy without exposing a plain HTTP listener publicly.

Terminate HTTPS at a reverse proxy and forward `/`, `/api/`, and `/git/` to the frontend service on port 3000. Preserve the Authorization header, support streamed request bodies, and allow suitable request sizes/timeouts for Git pushes (the backend default is 100 MiB per request and 120 seconds per Git transport operation). `FORGE_MAX_GIT_BODY_MB` changes the body limit. The backend port and database ports remain internal to Compose.

Example host nginx location inside an HTTPS virtual host:

```nginx
location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_request_buffering off;
    proxy_read_timeout 180s;
    client_max_body_size 100m;
}
```

The backend runs one worker. Authentication throttling is in memory and based on the connecting address. Behind the frontend proxy, the limit is shared by clients: ten login attempts per five minutes. Distributed rate limiting and trusted proxy client addresses are future work.

## SMTP

Under **Organization & System**, configure an optional SMTP host, port, TLS/STARTTLS, credentials, and sender address. Save, then send a test email to your own account. SMTP passwords are encrypted and never returned by the API. Leaving the password field blank retains a saved password; clearing the host disables SMTP. Automated notifications and password reset email workflows are not yet implemented.

## Persistence and backups

| Volume | Contents |
| --- | --- |
| `forge_data` | Encrypted installation configuration, SQLite database, bare repositories |
| `postgres_data` | Optional PostgreSQL database |
| `mariadb_data` | Optional MariaDB database |

Back up `.env` and `forge_data`, including `installation.json` and `/data/repositories`. For an external or optional database, include a consistent database dump. Stop application writes while creating a consistent backup across the database and Git repository files. Store secrets and backups securely. `docker compose down` retains volumes; adding `--volumes` deletes them.

To update, back up first, read the release notes, and run `docker compose up --build -d`, retaining the selected database profile. Startup applies pending Alembic migrations. Application rollback alone does not undo database migrations.
