# Architecture

## Application structure

The Next.js App Router frontend lives in `upcode-forge/`. It reuses Sprint's theme tokens, Inter and Geist Mono fonts, cards, form controls, dialog/toast components, 18rem sidebar, navigation states, and light/dark switch. Forge adds repository, code, diff, issue, and pull request views. Project-maintained text uses English, matching Sprint.

The FastAPI application lives in `upcode-forge-service/app/`:

| Module | Responsibility |
| --- | --- |
| `config.py` | Environment settings and bootstrap secrets |
| `database.py` | SQLAlchemy engines/sessions, encryption, installation storage, migrations |
| `models.py` | Instance, users, sessions/tokens, repositories, memberships, tickets, comments |
| `schemas.py` | Validated API request payloads |
| `security.py` | Argon2 passwords, hashed session/token secrets, authentication, throttling |
| `api.py` | Setup, authentication, administration, repository access, and collaboration |
| `git_service.py` | Git initialization, browsing, diffs, and merges |
| `git_http.py` | Authorized Git Smart HTTP transport |
| `main.py` | Lifespan, middleware, health, and routing |

Alembic owns database schema changes. `installation.json` contains the encrypted SQLAlchemy database URL. The encryption key derives from `FORGE_SECRET_KEY`. Setup is serialized using a filesystem lock and a singleton instance record prevents reinitializing an existing database. Run one application instance/worker against a data volume in this release.

## Authentication and access

Passwords use Argon2. Browser sessions use random secrets in HttpOnly, SameSite=Lax cookies; only SHA-256 digests are stored in SQL. Sessions expire after seven days. Deploy with `FORGE_COOKIE_SECURE=true` behind HTTPS. Mutating browser API calls require a custom request header, and supplied Origin headers must match a configured origin. CORS is disabled.

Git authenticates using HTTP Basic with a username and an expiring personal access token, separate from browser sessions and account passwords. Token scope only narrows repository rights. Revocation and account deactivation are checked on every Git request. Password changes revoke all sessions and Git tokens.

| Repository role | Permissions |
| --- | --- |
| Read | Browse, clone, fetch, read issues and pull requests |
| Write | Read plus push, create issues/pull requests, comment, close/reopen tickets |
| Maintain | Write plus merge, change settings, manage collaborators |
| Owner / instance administrator | Maintain access automatically |

Public visibility grants anonymous Git read access. Browser pages require authentication. Users without private repository access receive 404. Repository file storage uses database IDs, so user-supplied names are never filesystem paths.

## Git operations

Bare repositories are stored as `/data/repositories/<id>.git`. The transport only allows Smart HTTP discovery and upload/receive pack routes. FastAPI authorizes each request before invoking the official `git-http-backend`. Request and response pack data are spooled to temporary files to avoid loading full packs into memory; HTTP responses are streamed from the output file. Git receives no shell-interpolated commands. Hooks are not editable or exposed. Force pushes and branch deletions are rejected through repository configuration in this initial version.

Browsing resolves references to commit object IDs before reading trees/blobs. Symlinks display their Git blob content and are not followed on disk. Text files/diffs are limited to 2 MiB in the browser. Binary files and submodules are identified without attempting to execute or follow them.

Pull requests compare two branches in the same repository. Merge uses `git merge-tree --write-tree`, creates a merge commit, and updates the destination ref with the expected previous object ID. Conflicts and concurrent destination changes fail without overwriting the destination. Forks, review approvals, branch protection policies, and CI status checks are future work. Git ref updates and SQL transactions are separate storage operations; a backup must capture both stores consistently.

The frontend forwards `/api/*` and `/git/*` to the backend using runtime route handlers. Only the frontend port is published by Compose, and both application containers run as non-root users.
