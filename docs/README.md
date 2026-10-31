# Upcode Forge – Documentation

| Document | Description |
| --- | --- |
| [Installation & Deployment](installation.md) | Compose, setup, databases, HTTPS, and persistence |
| [Architecture](architecture.md) | Application layers, Git transport, authentication, and permissions |
| [Development & Checks](development.md) | Local development and verification |
| [Personal MCP access](mcp.md) | Scoped personal keys, MCP tools, and permission boundaries |
| [Two-factor authentication](two-factor-authentication.md) | Authenticator setup, sign-in, recovery, and security |

- [Project overview](../README.md)
- [Open work](../TODO.md)
- [Current release notes](../RELEASE.md)
- [Release history](../releases/README.md)

The backend exposes OpenAPI documentation at `/docs` on its internal port 8000. It is not published to the host by the supplied Compose configuration. Browser API calls use `/api/v1` through the frontend.
