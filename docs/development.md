# Development & Checks

Use Python 3.11+, Node.js 22+, and Git 2.38+. All commands start at the Forge repository root.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e './upcode-forge-service[dev]'
cd upcode-forge
npm ci
cd ..
```

For backend development, export `FORGE_SECRET_KEY` and `FORGE_SETUP_TOKEN` with independently generated 32+ character secrets, set `FORGE_DATA_DIR` to an absolute writable local directory, and set `FORGE_BOOTSTRAP_ORIGIN=http://localhost:3000`. Start from `upcode-forge-service/`:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend from `upcode-forge/`:

```bash
npm run dev
```

The frontend defaults to backend `http://127.0.0.1:8000`; override `BACKEND_INTERNAL_URL` if needed. Open <http://localhost:3000/setup>. Backend API documentation is available at <http://127.0.0.1:8000/docs>.

## Checks

| Command | Purpose |
| --- | --- |
| `make test` | Backend API tests and real Git HTTP clone/push/merge integration |
| `make lint` | Ruff, ESLint, and TypeScript |
| `make build` | Next.js production build |
| `make dev` | Build and run Compose services in the foreground |
| `make compose-up` | Build and start Compose services in the background |

Tests use disposable SQLite databases and Git repositories, including an HTTP server bound to an ephemeral loopback port. They do not use the application data volume or external SMTP. SQL schema compilation covers PostgreSQL and MySQL dialects; this is separate from running integration tests against live database services. The initial implementation was also checked manually against PostgreSQL 17 and MariaDB 11 containers, including setup, migrations, SQLAlchemy writes, and encrypted configuration restore.

The initial Compose smoke test covered setup, session cookies, private clone/push through the Next.js proxy, pull request merge, and logout. Visual browser verification remains pending because no browser was connected to the implementation session.

Use `ruff format .` inside the backend and `npx prettier --write .` inside the frontend for formatting. Keep schema migrations explicit, update the release notes for user-visible changes, and retain English for project-maintained text.
