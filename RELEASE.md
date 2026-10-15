# Upcode Forge 0.1.0

Status: initial local implementation, not published.

Forge introduces a self-hosted Git workspace using FastAPI, SQLAlchemy, Next.js, and Docker Compose. The interface follows Upcode Sprint's design system and Harbor's README structure.

Included: a locked first-run setup wizard; SQLite/PostgreSQL/MariaDB database selection; administrator-managed accounts; public/private Git repositories; HTTP(S) clone/fetch/push with scoped personal tokens; code, branch, README, commit, and diff browsing; issues and comments; same-repository pull requests and merges; collaborators; password changes; optional encrypted SMTP configuration and test delivery.

See [TODO.md](TODO.md) for the remaining roadmap and [installation documentation](docs/installation.md) before deployment.

## Added locally

- Corrected the dashboard PNG logo's aspect ratio and reduced the public profile header logo size.

- Contribution calendar years now start at account registration and continue chronologically through the current year, without a ten-year cap. The current year is selected by default, and the API rejects years outside the account's lifetime.

- Fixed a shared button rendering error that crashed public profiles and the profile editor when displaying links. Added component rendering regression tests to `make test`.

- One-time HTTPS repository imports from GitHub.com and GitLab.com, including private sources with temporary access tokens, full Git history, branches, tags, and the default branch. Failed imports roll back the database entry and partial Git repository.
- Public `/u/<username>` profiles with editable display name, bio, workplace, location, website, opt-in public email, and social links. The yearly heatmap includes public and private contributions; private activity exposes only daily/yearly counts. Public repository cards remain accessible without signing in, and account email stays private.
- Profile picture upload, preview, replacement, and removal. PNG, JPEG, and WebP inputs up to 5 MiB are normalized to a 256 × 256 PNG without metadata and stored in the account database. Pictures appear on public profiles and in the sidebar.
- Migration `0002` adds profile fields, and `0003` adds profile pictures to existing accounts. Rebuild both application services to use the new UI and API; migrations run automatically on backend startup.
