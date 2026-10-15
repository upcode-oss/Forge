# Upcode Forge 0.1.0

Status: initial local implementation, not published.

Forge introduces a self-hosted Git workspace using FastAPI, SQLAlchemy, Next.js, and Docker Compose. The interface follows Upcode Sprint's design system and Harbor's README structure.

Included: a locked first-run setup wizard; SQLite/PostgreSQL/MariaDB database selection; administrator-managed accounts; public/private Git repositories; HTTP(S) clone/fetch/push with scoped personal tokens; code, branch, README, commit, and diff browsing; issues and comments; same-repository pull requests and merges; collaborators; password changes; optional encrypted SMTP configuration and test delivery.

See [TODO.md](TODO.md) for the remaining roadmap and [installation documentation](docs/installation.md) before deployment.

## Added locally

- One-time HTTPS repository imports from GitHub.com and GitLab.com, including private sources with temporary access tokens, full Git history, branches, tags, and the default branch. Failed imports roll back the database entry and partial Git repository.
- Public `/u/<username>` profiles with editable display name, bio, workplace, location, website, opt-in public email, and social links. A yearly contribution heatmap and public repository cards are accessible without signing in; private activity and account email remain private.
- Migration `0002` adds profile fields to existing accounts without changing authentication or repository data. Rebuild both application services to use the new UI and API.
