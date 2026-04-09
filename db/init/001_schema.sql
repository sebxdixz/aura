-- =============================================================
-- AURA – Canonical schema  (v2 – multi-tenant with full JSONB)
-- File: db/init/001_schema.sql
-- NOTE: 01-schema.sql is removed; this is the single source of truth.
-- =============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   VARCHAR(100) PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    intake_url  VARCHAR(255) NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id     VARCHAR(64)  PRIMARY KEY,
    tenant_id       VARCHAR(100) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    reporter_email  VARCHAR(255) NOT NULL,
    description     TEXT         NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'open',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolution_notes TEXT,
    file_meta       JSONB,
    triage          JSONB        NOT NULL,
    ticket          JSONB        NOT NULL,
    notifications   JSONB        NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL    PRIMARY KEY,
    tenant_id   VARCHAR(100),
    incident_id VARCHAR(64),
    stage       VARCHAR(80)  NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS code_chunks (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   VARCHAR(100) NOT NULL,
    repo_name   VARCHAR(120) NOT NULL,
    file_path   TEXT         NOT NULL,
    chunk_index INTEGER      NOT NULL,
    content     TEXT         NOT NULL,
    embedding   vector(1536) NOT NULL,
    metadata    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, repo_name, file_path, chunk_index)
);

CREATE TABLE IF NOT EXISTS tenant_integrations (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    provider VARCHAR(30) NOT NULL,
    encrypted_config TEXT NOT NULL,
    configured_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, provider)
);

-- Indexes for tenant isolation and common query patterns
CREATE INDEX IF NOT EXISTS idx_incidents_tenant_id ON incidents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status    ON incidents (status);
CREATE INDEX IF NOT EXISTS idx_incidents_created   ON incidents (created_at);
CREATE INDEX IF NOT EXISTS idx_audit_tenant        ON audit_logs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_incident      ON audit_logs (incident_id);
CREATE INDEX IF NOT EXISTS idx_audit_stage         ON audit_logs (stage);
CREATE INDEX IF NOT EXISTS idx_code_chunks_repo    ON code_chunks (repo_name);
CREATE INDEX IF NOT EXISTS idx_code_chunks_tenant  ON code_chunks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_code_chunks_embed   ON code_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_tenant_integrations_tenant ON tenant_integrations (tenant_id);
