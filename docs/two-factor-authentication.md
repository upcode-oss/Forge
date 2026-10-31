# Two-factor authentication

Two-factor authentication (2FA) is optional for each account. Open **Profile & Access Tokens → Two-factor authentication**
and select **Enable two-factor authentication**.

1. Enter your current account password.
2. Scan the QR code with a TOTP-compatible authenticator app, or enter the manual
   setup key. The QR code is generated locally; no secret is sent to another service.
3. Enter the app's current six-digit code within ten minutes to enable 2FA.
4. Download or securely save the ten recovery codes before leaving the page.
   They are displayed only once.

At your next sign-in, enter your password, then a current authenticator code or an
unused recovery code. No authenticated session or access token is issued after
the password step alone. App codes use 30-second steps and are accepted with one
step of clock tolerance in either direction. A successfully used app code cannot
be used again; wait for the next code if needed. Keep the server and phone clocks
synchronized.

Each recovery code works once. **Replace recovery codes** creates a new set and
invalidates every old code. Replacing codes or disabling 2FA requires your current
password and an app code or unused recovery code. These changes, including enabling
2FA, sign out other browser sessions and renew the current browser session.

Five invalid second-factor attempts lock verification for the account for five
minutes, across login and factor-management requests. The counter is stored in the
database, so new clients, workers, and restarts do not bypass the lock. Existing
login and management request rate limits also apply.

2FA protects browser sign-in. Git over HTTP(S) continues to use personal access
tokens; SSH continues to use registered public keys. Enabling or changing 2FA does
not revoke Git tokens or SSH keys. Manage them separately in your profile.

## Storage and upgrades

Migration `0010` adds nullable encrypted authenticator secrets, an expiring
pending setup, a last-used time step, hashed recovery codes, and persistent attempt
tracking. Existing accounts remain able to sign in without 2FA until they enable it.
Preserve `FORGE_SECRET_KEY` together with database backups: it encrypts both pending
and active authenticator secrets. Recovery codes contain 80 random bits each and
are stored only as SHA-256 hashes.

Account updates are serialized with a guarded database write before factors are
checked or changed. This covers SQLite as well as PostgreSQL and MySQL and prevents
simultaneous reuse of an app or recovery code. API authentication responses are
marked `Cache-Control: no-store`.

## API

All management routes require an authenticated account and apply only to that
account. Authenticator secrets and recovery hashes are absent from account and
status responses.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/auth/2fa` | Enabled state and remaining recovery-code count |
| POST | `/api/v1/auth/2fa/setup` | Start or replace a pending setup using `password` |
| POST | `/api/v1/auth/2fa/enable` | Confirm setup using `password` and an app `code` |
| POST | `/api/v1/auth/2fa/recovery-codes` | Replace recovery codes using `password` and `code` |
| POST | `/api/v1/auth/2fa/disable` | Disable 2FA using `password` and `code` |

`POST /api/v1/auth/login` accepts an optional `two_factor_code`. For enabled
accounts, a correct password without a code returns
`{"two_factor_required": true}` without authentication cookies or tokens. Submit
the original credentials again with the second-factor code to finish signing in.

## References

The implementation uses [PyOTP](https://pyauth.github.io/pyotp/) and follows
[RFC 6238](https://www.rfc-editor.org/rfc/rfc6238) for TOTP and the
[OWASP MFA guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
for factor changes and recovery codes.
