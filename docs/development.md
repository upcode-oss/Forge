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
| `make test` | Backend API tests, real Git HTTP clone/push/merge integration, and frontend component rendering regressions |
| `make lint` | Ruff, ESLint, and TypeScript |
| `make build` | Next.js production build |
| `make dev` | Build and run Compose services in the foreground |
| `make compose-up` | Build and start Compose services in the background |

Tests use disposable SQLite databases and Git repositories, including an HTTP server bound to an ephemeral loopback port. They do not use the application data volume or external SMTP. SQL schema compilation covers PostgreSQL and MySQL dialects; this is separate from running integration tests against live database services. The initial implementation was also checked manually against PostgreSQL 17 and MariaDB 11 containers, including setup, migrations, SQLAlchemy writes, and encrypted configuration restore.

SSH tests validate key parsing and OpenSSH fingerprints, account/key/repository permissions, revocation on existing connections, command and path restrictions, pack streaming, a real Git push through the command handler, size limits, and timeouts. `tests/test_ssh_network.py` additionally runs a real OpenSSH clone/push against AsyncSSH, checks the pinned server host key, rejects a shell command, and checks revocation. That test requires the installed backend dependencies, OpenSSH `ssh`/`ssh-keygen` clients, and permission to bind loopback. Unit/API fixtures leave the SSH listener disabled even if it is enabled in your shell environment.

Organization tests cover creation by regular users, unique URL names, public search and pagination, private profile/member/avatar access, profile membership badges, the role matrix, membership revocation, image normalization, deactivation, deletion, and simultaneous Owner departures. Frontend rendering tests cover organization forms, role-specific member controls, and public organization profiles.
Organization repository tests additionally cover inherited roles, independent user/organization namespaces, creator attribution, parent privacy, scope restrictions, membership revocation, imports, real Git HTTP fetch/push pack exchange, and SSH pack streaming. Migration regression tests upgrade a populated pre-organization-repository database and verify existing IDs, relationships, ownership constraints and restored SQLite foreign-key enforcement.

The initial Compose smoke test covered setup, session cookies, private clone/push through the Next.js proxy, pull request merge, and logout. Visual browser verification remains pending because no browser was connected to the implementation session.

Use `ruff format .` inside the backend and `npx prettier --write .` inside the frontend for formatting. Keep schema migrations explicit, update the release notes for user-visible changes, and retain English for project-maintained text.
