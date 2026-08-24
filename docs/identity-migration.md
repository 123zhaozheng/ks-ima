# Local Identity Migration

Python owns browser sessions after the identity cutover. Legacy Better Auth
tables remain read-only until the final authorization/content migration.

Before a cutover, take a PostgreSQL and object-store snapshot and run
`ima migrate-legacy-identity` against a disposable copy. The command is
read-only and reports whether `public.user`, `public.account`, and
`public.session` exist. Compatible Argon2id PHC values may be imported only
after verification with the Python verifier; unknown formats are marked for a
forced reset. Legacy session tokens are never copied.

Set `IMA_SESSION_PEPPER`, `IMA_TOKEN_PEPPER`, `IMA_TOTP_ENCRYPTION_KEY`, and
`IMA_BRIDGE_TOKEN` to independent high-entropy values before production
startup. Rotate them only during a planned session invalidation event.

`ima bootstrap-admin` accepts `IMA_BOOTSTRAP_EMAIL` and
`IMA_BOOTSTRAP_PASSWORD` in sealed deployment input, or prompts locally. It
refuses to run when an active super administrator already exists and never has
an HTTP equivalent.

Rollback before old auth-table removal restores the previous Caddy/frontend
artifact and database snapshot, then invalidates Python sessions. Passwords
are not reverse-synchronised.
