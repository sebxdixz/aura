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
    file_meta       JSONB,
    attachment_type VARCHAR(40),
    attachment_filename VARCHAR(255),
    attachment_mime_type VARCHAR(120),
    attachment_size_bytes INTEGER,
    attachment_storage_path TEXT,
    attachment_text_extracted TEXT,
    attachment_summary TEXT,
    evidence_from_attachment JSONB NOT NULL DEFAULT '[]'::jsonb,
    attachment_signals JSONB NOT NULL DEFAULT '{}'::jsonb,
    attachment_used BOOLEAN NOT NULL DEFAULT false,
    duplicate_of_incident_id VARCHAR(64),
    cluster_id TEXT,
    recurrence_count_7d INTEGER NOT NULL DEFAULT 0,
    recurrence_count_30d INTEGER NOT NULL DEFAULT 0,
    related_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    scope_assessment TEXT,
    multi_ticket_influence_reasoning TEXT,
    triage          JSONB        NOT NULL,
    ticket          JSONB        NOT NULL,
    notifications   JSONB        NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS incident_links (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    source_incident_id VARCHAR(64) NOT NULL,
    target_incident_id VARCHAR(64) NOT NULL,
    relationship_type VARCHAR(32) NOT NULL,
    similarity_score DOUBLE PRECISION NOT NULL,
    reasoning TEXT,
    shared_signals JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

-- Indexes for tenant isolation and common query patterns
CREATE INDEX IF NOT EXISTS idx_incidents_tenant_id ON incidents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status    ON incidents (status);
CREATE INDEX IF NOT EXISTS idx_incidents_created   ON incidents (created_at);
CREATE INDEX IF NOT EXISTS idx_incidents_duplicate_of ON incidents (duplicate_of_incident_id);
CREATE INDEX IF NOT EXISTS idx_incidents_cluster_id ON incidents (cluster_id);
CREATE INDEX IF NOT EXISTS idx_audit_tenant        ON audit_logs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_incident      ON audit_logs (incident_id);
CREATE INDEX IF NOT EXISTS idx_audit_stage         ON audit_logs (stage);
CREATE INDEX IF NOT EXISTS idx_code_chunks_repo    ON code_chunks (repo_name);
CREATE INDEX IF NOT EXISTS idx_code_chunks_tenant  ON code_chunks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_code_chunks_embed   ON code_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_incident_links_tenant ON incident_links (tenant_id);
CREATE INDEX IF NOT EXISTS idx_incident_links_source ON incident_links (source_incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_links_target ON incident_links (target_incident_id);
