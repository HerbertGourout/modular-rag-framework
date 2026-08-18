-- ADR-0011 (PostgreSQL migrations, connection pooling, and audit retention).
-- Codex review HIGH-001 (second post-implementation pass): the first version
-- of this migration defined `expires_at` as
-- `GENERATED ALWAYS AS ("timestamp" + make_interval(days => retention_days)) STORED`.
-- PostgreSQL rejects that outright: generated-column expressions must be
-- IMMUTABLE, but `timestamptz + interval` is declared STABLE in PostgreSQL's
-- own catalog (`timestamptz_pl_interval`) — its result can depend on the
-- session's TimeZone setting and DST transitions when the interval carries
-- day/month components, which `make_interval(days => ...)` always does.
-- Verified independently against postgresql.org's own mailing list
-- discussion of this exact error before rewriting, not guessed.
--
-- Rewritten as a plain (non-generated) column instead, backfilled once here
-- via a regular UPDATE — the IMMUTABLE restriction applies only to
-- GENERATED ALWAYS AS expressions and index expressions, never to ordinary
-- DML, so this one-time backfill can use the same STABLE arithmetic safely.
-- Going forward, `PostgresAuditSink.record()` computes `expires_at` in
-- Python (`event.timestamp + timedelta(days=event.retention_days)`, both
-- UTC-based per `AuditEvent.timestamp`'s own default, so there is no
-- DST/timezone ambiguity to begin with) and passes it as an explicit INSERT
-- value — sidestepping the whole IMMUTABLE-classification question rather
-- than fighting it with an `AT TIME ZONE` cast (which trades one STABLE
-- function, `timestamptz_pl_interval`, for another, `timezone(text,
-- timestamptz)` — text-zone-name timezone conversion is STABLE too).
ALTER TABLE audit_events ADD COLUMN expires_at TIMESTAMPTZ;
UPDATE audit_events
    SET expires_at = "timestamp" + make_interval(days => retention_days)
    WHERE expires_at IS NULL;
ALTER TABLE audit_events ALTER COLUMN expires_at SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_events_expires_at ON audit_events (expires_at);
