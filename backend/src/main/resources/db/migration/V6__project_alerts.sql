CREATE TABLE project_alert_settings (
    project_id UUID PRIMARY KEY
        REFERENCES projects (id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT false,
    prompted BOOLEAN NOT NULL DEFAULT false,
    topics_refreshed_at TIMESTAMPTZ,
    last_scan_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_project_alert_settings_enabled
    ON project_alert_settings (project_id)
    WHERE enabled;

-- Removed AUTO topics stay (removed = true) so a refresh never re-creates them.
CREATE TABLE alert_topics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id UUID NOT NULL
        REFERENCES projects (id) ON DELETE CASCADE,
    label VARCHAR(80) NOT NULL,
    query VARCHAR(300) NOT NULL,
    source VARCHAR(8) NOT NULL
        CONSTRAINT ck_alert_topics_source CHECK (source IN ('AUTO', 'USER')),
    removed BOOLEAN NOT NULL DEFAULT false,
    min_score DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_alert_topics_project_id
    ON alert_topics (project_id);

-- Dismissed alerts stay so their document is never alerted again for the project.
CREATE TABLE alerts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id UUID NOT NULL,
    project_id UUID NOT NULL
        REFERENCES projects (id) ON DELETE CASCADE,
    topic_id BIGINT
        REFERENCES alert_topics (id) ON DELETE SET NULL,
    topic_label VARCHAR(80) NOT NULL,
    document_id VARCHAR(128) NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    source VARCHAR(128),
    district VARCHAR(128),
    category VARCHAR(128),
    published_date DATE,
    excerpt TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    feedback VARCHAR(16)
        CONSTRAINT ck_alerts_feedback CHECK (feedback IN ('NOT_RELEVANT')),
    CONSTRAINT uq_alerts_project_document UNIQUE (project_id, document_id)
);

CREATE INDEX idx_alerts_client_id_created_at
    ON alerts (client_id, created_at DESC);
