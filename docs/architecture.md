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
| `api.py` | Setup, authentication, optional registration, administration, repository access, and collaboration |
| `organizations.py` | Organization profiles, discovery, private visibility, avatars, and role-based memberships |
| `organization_access.py`, `repository_access.py` | Shared organization and repository access checks, inherited roles, and Git namespace resolution |
| `git_service.py` | Git initialization, browsing, diffs, and merges |
| `git_http.py` | Authorized Git Smart HTTP transport |
| `ssh_support.py`, `ssh_keys.py` | Public key validation, fingerprints, host keys, key management, and SSH clone URLs |
| `git_ssh.py`, `ssh_server.py` | Per-command Git authorization, binary pack streaming, and the AsyncSSH listener |
| `main.py` | Lifespan, middleware, health, and routing |

Alembic owns database schema changes. `installation.json` contains the encrypted SQLAlchemy database URL. The encryption key derives from `FORGE_SECRET_KEY`. Setup is serialized using a filesystem lock and a singleton instance record prevents reinitializing an existing database. Run one application instance/worker against a data volume in this release.

## Authentication and access

Passwords use Argon2. Browser sessions use random secrets in HttpOnly, SameSite=Lax cookies; only SHA-256 digests are stored in SQL. Sessions expire after seven days. Deploy with `FORGE_COOKIE_SECURE=true` behind HTTPS. Mutating browser API calls require a custom request header, and supplied Origin headers must match a configured origin. CORS is disabled.

Git authenticates using HTTP Basic with a username and an expiring personal access token, separate from browser sessions and account passwords. Token scope only narrows repository rights. Revocation and account deactivation are checked on every Git request. Password changes revoke all sessions and Git tokens.

Git SSH uses [AsyncSSH](https://asyncssh.readthedocs.io/en/latest/api.html) in the backend process, with a persistent Ed25519 host key and public-key-only authentication as `git`. The cryptography library validates and canonicalizes uploaded OpenSSH public keys; SHA-256 fingerprints are unique across accounts. Read-only keys further narrow account permissions. Every command rechecks the key id, account id, fingerprint, current account state, key scope, and repository permissions. This prevents an old authenticated connection from acquiring a different identity if a deleted SQL key id is reused. Password, keyboard-interactive, host-based and GSS authentication, shells, PTYs, file transfer, and all forwarding are disabled. A command-free connection prints an authentication greeting and exits.

The SSH command parser accepts only `git-upload-pack` or `git-receive-pack` with an `owner/name.git` or `organizations/slug/name.git` path. Database ids determine the actual repository path. Git starts without a shell, with server-controlled arguments and an environment that does not inherit client-provided configuration. Pack streams use bounded chunks and backpressure; oversized input, timeout, disconnect, and cancellation stop the Git process group. Listener shutdown closes active SSH connections before database disposal. Keys are stored in SQL; the private host key is stored only in the persistent data volume.

| Repository role | Permissions |
| --- | --- |
| Read | Browse, clone, fetch, read issues and pull requests |
| Write | Read plus push, create issues/pull requests, comment, close/reopen tickets |
| Maintain | Write plus merge, change settings, manage collaborators, delete repositories |
| Owner / instance administrator | Maintain access automatically |

Public visibility grants anonymous Git and browser read access. Repository pages at `/repositories/<id>` use the workspace shell for signed-in users and public navigation for visitors. Repository files, README, branches, commits/diffs, issues, pull requests/diffs, and comments use optional authentication while mutations and collaborator listings still require authentication and repository permissions. `/repositories?scope=public` lists only effectively public repositories even for signed-in administrators. Discovery at `/explore/repositories`, public user profiles, public organization profiles, and organization search work without an account. Users without private repository access receive 404. Repository file storage uses database IDs, so user-supplied names are never filesystem paths.

Instance metadata, including the registration state, is public; SMTP and administrator account management remain protected. Only instance administrators can update the persisted `registration_enabled` setting. Migration `0007` defaults it to false on existing installations. `/auth/register` checks the setting on every request, validates the same username, email, and password rules as administrator-created accounts, rate limits attempts, always creates a regular active account, and starts a session with the existing HttpOnly cookie settings. Disabling registration does not revoke existing accounts or sessions.

Repository settings include permanent deletion with a full owner/repository name confirmation. The DELETE API requires Maintain access and removes comments, issues/pull requests, collaborator grants, and the repository in one SQL transaction. Git storage is first renamed to a unique retired directory and restored if the transaction fails, then removed after commit. Filesystem cleanup failures after commit are logged for administrator cleanup; retired directories are never served or reused for new repositories.

## Organizations

Every active account can create an organization at **Organizations → New organization**. The creator becomes Owner. URL names are unique, permanent, and separate from user names; organization profiles use `/o/<slug>`. Owners and Maintainers add existing accounts by their Forge username. Membership is managed explicitly; there is no automatic public enrollment.

| Organization role | Permissions |
| --- | --- |
| Reader | View the organization and its members; leave the organization |
| Maintainer | Reader access plus edit the name, description, contact email, social links and picture; add/remove Readers |
| Owner | Maintainer access plus change visibility, assign any role, remove members, and delete the organization |

The last active Owner cannot leave, be removed, or be demoted. Membership mutations lock the organization row on PostgreSQL/MySQL and are also serialized within the supported single-worker deployment for SQLite. Deactivated accounts cannot be added and do not appear in the member list.

Public organizations are searchable by name, URL name and description under `/explore`; results are paginated. Members see all their own organizations, including private ones, under `/organizations`. Private organization profiles, member lists, and avatar URLs return 404 to outsiders, including instance administrators without membership. All these API responses disable caching. Member profiles show organization avatar links, filtered by the viewer's access; anonymous visitors see only public organizations. Organization contact details follow the same visibility setting. Picture uploads reuse the account image limits and normalization (PNG/JPEG/WebP, 5 MiB, 16 million pixels, normalized to 256 × 256 PNG without metadata).

Organizations can own repositories. Owners and Maintainers can create, import, and manage organization repositories; Readers inherit read access. The strongest of inherited and explicit repository grants applies. Organization roles grant no access to members' personal repositories. The owner selector in repository creation/import lists the account and all organizations where it has Owner or Maintainer access. Organization pages list accessible repositories with HTTPS/SSH clone controls.

Organization Git paths use `/git/organizations/<slug>/<name>.git` over HTTP and `organizations/<slug>/<name>.git` over SSH. Personal paths stay unchanged; an existing user and organization can have identical names without collisions. SQL enforces exactly one user or organization owner, and names are unique within that owner's namespace. Creation is attributed to the initiating account for contribution activity, while repositories are listed on their owning organization's profile.

A private organization requires membership for all repository access, including explicit repository grants and instance administrators. New repositories in private organizations must be private. If a public organization becomes private, its existing public repositories are effectively private until the organization is public again; contribution counts are reclassified as private as well. Git HTTP challenges unauthenticated requests to both private and unknown organization namespaces identically so Git clients can prompt for credentials. Authenticated outsiders receive 404. Removing membership or changing roles applies to subsequent API, HTTP and SSH commands. Organizations containing repositories cannot be deleted, preserving their Git data and relationships.

Migration `0006` preserves existing repository IDs, ownership, collaborators, issues, comments and SSH keys. SQLite batch migrations temporarily suspend foreign-key enforcement on the migration connection, validate all references before commit, and restore enforcement before returning the connection to the pool. PostgreSQL/MySQL use their native table alterations.

## Git operations

Bare repositories are stored as `/data/repositories/<id>.git`. The transport only allows Smart HTTP discovery and upload/receive pack routes. FastAPI authorizes each request before invoking the official `git-http-backend`. Request and response pack data are spooled to temporary files to avoid loading full packs into memory; HTTP responses are streamed from the output file. Git receives no shell-interpolated commands. Hooks are not editable or exposed. Force pushes and branch deletions are rejected through repository configuration in this initial version.

Browsing resolves references to commit object IDs before reading trees/blobs. Symlinks display their Git blob content and are not followed on disk. Text files/diffs are limited to 2 MiB in the browser. Binary files and submodules are identified without attempting to execute or follow them.

Pull requests compare two branches in the same repository. Merge uses `git merge-tree --write-tree`, creates a merge commit, and updates the destination ref with the expected previous object ID. Conflicts and concurrent destination changes fail without overwriting the destination. Forks, review approvals, branch protection policies, and CI status checks are future work. Git ref updates and SQL transactions are separate storage operations; a backup must capture both stores consistently.

The frontend forwards `/api/*` and `/git/*` to the backend using runtime route handlers. Compose publishes the frontend HTTP port and the backend Git SSH port, each on loopback by default. Both application containers run as non-root users; SSH requires no system login accounts or root daemon.
