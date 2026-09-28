# 2. Auth Session Management Strategy

Date: 2026-09-28

## Status
Accepted

## Context
We need to implement user authentication (register, login, logout) for the application. The implementation plan allows choosing between a server-side sessions table and signed JWTs stored in httpOnly cookies.

## Decision
We will use **signed JWTs stored in httpOnly cookies** for session management.
To handle revocation (e.g., logout), since JWTs are stateless, we will implement a lightweight approach: the JWT will have a relatively short expiration time. If instant revocation is strictly required in the future, we can add a token blocklist or a `token_version` column to the `users` table.

## Rationale
- **Simplicity:** Avoids introducing a new `sessions` table and a new database migration right after stabilizing the initial schema in S1.2.
- **Performance:** JWTs can be verified without a database lookup, reducing latency on every protected API request.
- **Security:** Storing the JWT in an `httpOnly`, `Secure` (in production), and `SameSite=Lax` cookie protects against XSS and CSRF attacks.

## Consequences
- **Revocation:** Logout will clear the cookie on the client side. The token itself remains technically valid until it expires, but the client will no longer send it.
- **Dependencies:** We will use the `python-jose` or similar library for JWT signing and verification. Since `cryptography` is already installed, we can also use `PyJWT`.
