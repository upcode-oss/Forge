# Upcode Forge - Self-Hosted Git Collaboration

<p align="center">
  <img src="upcode-forge/public/logo.png" alt="Upcode Forge Logo" width="400">
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js](https://img.shields.io/badge/Next.js-16.x-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)

A self-hosted Git collaboration platform with repository hosting, code browsing, issues, and pull requests. Upcode Forge keeps your code on your infrastructure with a FastAPI and SQLAlchemy backend, a Next.js frontend, and the shared design language of Upcode Harbor and Upcode Sprint.

## 🚀 Features

- 📦 **Git Repository Hosting** - Create public and private bare Git repositories; clone, fetch, and push over HTTP(S)
- 🔐 **SSH Git Access** - Register SSH public keys, choose read-only or read/write scope, and clone, fetch, or push through a Git-only SSH service
- 📥 **Repository Imports** - Import GitHub.com and GitLab.com repositories, including Git history, branches, and tags; optional tokens support private sources
- 👤 **Public Profiles** - Upload a profile picture and share your bio, workplace, location, public email, website, social links, public repositories, and a yearly calendar including anonymized private contributions
- 🏢 **Organizations** - Create public or private organizations with profile pictures, contact email, social links, and Owner/Maintainer/Reader memberships; discover public teams through search and see organization pictures on member profiles
- 🌿 **Code & History** - Branch selection, directory navigation, text previews, Markdown READMEs, commit history, and diffs
- 🐛 **Issues** - Track work with descriptions, comments, and open/closed states
- 🔀 **Pull Requests** - Compare branches, discuss changes, and merge without conflicts
- 👥 **Users & Permissions** - Instance administrators and repository read, write, and maintain access
- 🔑 **Access Tokens** - Expiring read/write Git tokens, shown once and individually revocable
- ⚙️ **Setup Wizard** - Instance identity, public URL, default branch, database, and first administrator
- 🗄️ **Database Support** - SQLAlchemy with SQLite, PostgreSQL, or MariaDB/MySQL and Alembic migrations
- ✉️ **SMTP Configuration** - Encrypted credentials and test email delivery in administration
- 🎨 **Shared Upcode UI** - Sprint theme variables, fonts, sidebar layout, cards, forms, and responsive light/dark mode

Version 0.1.0 is an initial implementation. Git LFS, forks, CI runners, automated email notifications, and branch protection rules are tracked in [TODO.md](TODO.md).

## Local quality gates

After installing the development dependencies:

```bash
make test
make lint
make build
```

The checks cover setup authorization, sessions, repository permissions, issues, tokens, database schema compilation, and real Git clone/push/merge operations, followed by Ruff, ESLint, TypeScript, and the frontend production build. See [Development & Checks](docs/development.md).

## 📋 Prerequisites

- **Docker & Docker Compose**: For the container-based installation
- **Git client**: To clone and push repositories
- **Python**: 3.11+ for local backend development
- **Node.js**: 22+ for local frontend development
- **Git server executable**: Git 2.38+ for local backend development; included in the backend image

## ⚡ Installation

### Quick Installation

Run from the Forge repository root:

```bash
cp .env.example .env

# Generate two different secrets, then paste them into .env:
openssl rand -hex 32  # FORGE_SECRET_KEY
openssl rand -hex 32  # FORGE_SETUP_TOKEN

docker compose up --build -d
```

Open <http://localhost:3000/setup>. Use `FORGE_SETUP_TOKEN` to authorize installation, select a database, and create your administrator. SQLite works immediately without another database service. Sign in, create a repository, and generate a Git token under **Profile & Access Tokens**.

Use your Forge username and the token as the password when Git prompts for credentials. Your account password does not authenticate Git requests.

See [Installation & Deployment](docs/installation.md) for optional database profiles, remote access, HTTPS, persistent storage, and backups.

### Project Layout

```text
Forge/
├── upcode-forge-service/ # FastAPI, SQLAlchemy, Alembic, Git services, and tests
├── upcode-forge/         # Next.js frontend with the shared Upcode design
├── docs/                # Installation, architecture, and development guides
├── releases/            # Version-specific release notes
├── README.md            # Project overview
├── TODO.md              # Open work
├── RELEASE.md           # Current release notes
├── LICENSE              # MIT license
├── .env.example         # Environment configuration template
├── docker-compose.yml   # Application and optional database services
└── Makefile             # Development and quality commands
```

### Documentation

- [Documentation index](docs/README.md)
- [Architecture](docs/architecture.md)
- [Development & Checks](docs/development.md)
- [Open work](TODO.md)
- [Current release notes](RELEASE.md)
- [Release history](releases/README.md)

## 💝 Support

Want to support the project? Here are some ways to help:

### ⭐ GitHub Star

Give the project a star on [GitHub](https://github.com/upcode-oss/Forge) - it helps others discover it!

### 🐛 Issues & Feedback

- Report bugs via [GitHub Issues](https://github.com/upcode-oss/Forge/issues)
- Share feature requests and suggestions
- Help improve the documentation

### 🤝 Contribute

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit your changes: `git commit -am 'Add feature'`
4. Push to the branch: `git push origin feature-name`
5. Create a Pull Request

### 💰 Sponsoring

Support development financially:

- [GitHub Sponsors](https://github.com/sponsors/upcode-at)

### 📢 Spread the Word

- Share the project on social media
- Write a blog post about it
- Recommend it to friends and colleagues

Every contribution helps make Upcode Forge better! 🙏

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Contact & Community

- **GitHub**: [upcode-oss/Forge](https://github.com/upcode-oss/Forge)
- **Issues**: [Bug Reports & Feature Requests](https://github.com/upcode-oss/Forge/issues)
- **Discussions**: [GitHub Discussions](https://github.com/upcode-oss/Forge/discussions)

---

**Upcode Forge** - Your code. Your infrastructure. 🚀
