# Upcode Forge 0.1.0

Status: initial local implementation, not published.

Forge introduces a self-hosted Git workspace using FastAPI, SQLAlchemy, Next.js, and Docker Compose. The interface follows Upcode Sprint's design system and Harbor's README structure.

Included: a locked first-run setup wizard; SQLite/PostgreSQL/MariaDB database selection; administrator-managed accounts; public/private Git repositories; HTTP(S) clone/fetch/push with scoped personal tokens; code, branch, README, commit, and diff browsing; issues and comments; same-repository pull requests and merges; collaborators; password changes; optional encrypted SMTP configuration and test delivery.

See [TODO.md](TODO.md) for the remaining roadmap and [installation documentation](docs/installation.md) before deployment.

## Added locally

- Security fixes: recheck HTTP Git authorization after reading request bodies, impose a body deadline, and prevent SQLite repository ID reuse with migration `0013`. Delayed requests can no longer reuse revoked tokens or access replacement repositories. Existing IDs and repository files are preserved.
- Isolate login throttling by account behind the frontend proxy, and bound anonymous profile Git scans to preserve API worker capacity.
- Require Pillow 13.0+ and cryptography 50.0.2+, limit uploaded EXIF metadata to 64 KiB, and update the affected minimatch 10 dependency to 11.0.1+. The remaining npm advisory propagation through minimatch 3 is broader than the [upstream advisory's affected 10.2.6 implementation](https://github.com/isaacs/minimatch/security/advisories/GHSA-g3hv-75wg-m249); the older callable API is retained for ESLint plugin compatibility. Pillow's [EXIF parsing advisory](https://github.com/python-pillow/Pillow/security/advisories/GHSA-g4qv-2jxx-769h) applies directly to image normalization.

- MCP remains disabled by default on new and upgraded installations. Administrators explicitly enable it under **Instance & System → MCP access**. Disabling it hides profile key management and blocks new keys and all existing MCP credentials immediately. Migration `0012` persists the default-off flag.

- Personal MCP keys and a Streamable HTTP MCP endpoint, with code, repository, issue and pull-request tools. Key scopes cannot exceed the creator's current permissions; repository and private-organization checks run for every operation as the key owner. Keys expire, can be revoked, and are invalidated by password/2FA enrollment changes. Migration `0011` preserves existing data. See [MCP access](docs/mcp.md).

- Optional authenticator-based two-factor authentication under **Profile & Access Tokens**: locally generated QR codes, confirmed setup, ten single-use recovery codes, and password-plus-code checks for disabling or replacing recovery codes. Password-only login issues no session for enabled accounts. Factor changes revoke other browser sessions; Git tokens and SSH keys stay independent. Migration `0010` preserves existing accounts with 2FA disabled by default. See the [2FA guide](docs/two-factor-authentication.md).

- Sprint instance pairing is deferred to a later release; its settings and API endpoints have been removed.

- Backend images normalize application and Alembic file permissions before switching to the unprivileged `forge` user. Builds from checkouts with restrictive file modes (such as a `077` host umask) can now start, run setup, and migrate the database without granting the application write access to its code.

- Optional database containers no longer require passwords during Compose configuration when their profile is disabled. SQLite and external database deployments need only the Forge application secrets; configure database container passwords when enabling the matching PostgreSQL or MariaDB profile.

- Optional public account registration at `/register`, controlled by the instance administrator under **Instance & System → Allow public registration**. Registration is disabled by default, creates regular active accounts, uses the existing password rules and request protection, limits attempts, and signs new users in. Migration `0007` preserves existing installations with registration disabled.

- Anonymous browsing of public repositories, including files, README, branches, commits, issues, pull requests, and comments. Public repository discovery lives at `/explore/repositories`; repository links keep their `/repositories/<id>` URLs. Shared navigation connects repositories, user profiles, organization profiles, sign-in, and registration. Private repositories and repositories in private organizations remain restricted, and write operations still require authenticated permissions.

- Repository deletion from repository settings, including organization repositories with inherited Maintain access. Deletion requires typing the full owner/repository name and removes Git history, issues, pull requests, comments, and collaborator grants. Git files are restored if the database transaction fails.

- Refined organization repository lists with compact rows, repository counts, branch details, and expandable HTTPS/SSH clone controls. Repository pages now use spaced breadcrumbs and a linked owner heading, with visibility icons for public and private repositories.

- Organization-owned repositories with owner selection in create/import dialogs, repository lists and clone controls on organization profiles, and inherited organization roles. Owner and Maintainer can create and manage repositories; Reader inherits read access. Private organization visibility applies to API, HTTP Git, SSH Git, discovery, and activity classification. Organization clone paths use `organizations/<slug>/<repository>.git` to distinguish existing users with the same name. Migration `0006` preserves existing repository IDs and relationships while adding organization ownership. Organizations containing repositories are protected from deletion.

- Organizations with private/public visibility, pictures, contact email, social links, and Owner/Maintainer/Reader roles. Public search lives at `/explore`, organization profiles at `/o/<slug>`, and management under **Organizations**. Private organizations, membership badges, and pictures are visible only to members. The last active Owner cannot be removed or demoted. Migration `0005` creates organization tables automatically on startup.

- Git SSH access on port 2222, account public key management with fingerprints, last-used timestamps and read-only/read/write scopes, plus HTTPS/SSH clone selection. Persistent Ed25519 host keys and migration `0004` support existing installations. The listener permits only Git operations and applies existing repository permissions on every command.

- Corrected the dashboard PNG logo's aspect ratio and reduced the public profile header logo size.

- Contribution calendar years now start at account registration and continue chronologically through the current year, without a ten-year cap. The current year is selected by default, and the API rejects years outside the account's lifetime.

- Fixed a shared button rendering error that crashed public profiles and the profile editor when displaying links. Added component rendering regression tests to `make test`.

- One-time HTTPS repository imports from GitHub.com and GitLab.com, including private sources with temporary access tokens, full Git history, branches, tags, and the default branch. Failed imports roll back the database entry and partial Git repository.
- Public `/u/<username>` profiles with editable display name, bio, workplace, location, website, opt-in public email, and social links. The yearly heatmap includes public and private contributions; private activity exposes only daily/yearly counts. Public repository cards remain accessible without signing in, and account email stays private.
- Profile picture upload, preview, replacement, and removal. PNG, JPEG, and WebP inputs up to 5 MiB are normalized to a 256 × 256 PNG without metadata and stored in the account database. Pictures appear on public profiles and in the sidebar.
- Migration `0002` adds profile fields, and `0003` adds profile pictures to existing accounts. Rebuild both application services to use the new UI and API; migrations run automatically on backend startup.
