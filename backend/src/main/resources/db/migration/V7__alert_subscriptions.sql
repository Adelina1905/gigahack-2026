-- Alerts for every conversation: settings, topics and alerts now belong to a subscription
-- whose scope is either a project or a single chat. Existing project data is kept as-is.
CREATE TABLE alert_subscriptions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id UUID NOT NULL,
    project_id UUID
        CONSTRAINT uq_alert_subscriptions_project UNIQUE
        REFERENCES projects (id) ON DELETE CASCADE,
    chat_id UUID
        CONSTRAINT uq_alert_subscriptions_chat UNIQUE
        REFERENCES chats (id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT false,
    prompted BOOLEAN NOT NULL DEFAULT false,
    topics_refreshed_at TIMESTAMPTZ,
    last_scan_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_alert_subscriptions_scope CHECK ((project_id IS NULL) <> (chat_id IS NULL))
);

CREATE INDEX idx_alert_subscriptions_enabled
    ON alert_subscriptions (id)
    WHERE enabled;

-- One subscription per project that has settings, topics or alerts.
INSERT INTO alert_subscriptions (
    client_id, project_id, enabled, prompted, topics_refreshed_at, last_scan_at, updated_at
)
SELECT p.client_id,
       p.id,
       COALESCE(s.enabled, false),
       COALESCE(s.prompted, false),
       s.topics_refreshed_at,
       s.last_scan_at,
       COALESCE(s.updated_at, now())
FROM projects p
LEFT JOIN project_alert_settings s ON s.project_id = p.id
WHERE s.project_id IS NOT NULL
   OR EXISTS (SELECT 1 FROM alert_topics t WHERE t.project_id = p.id)
   OR EXISTS (SELECT 1 FROM alerts a WHERE a.project_id = p.id)
ORDER BY p.created_at, p.id;

-- Topics
ALTER TABLE alert_topics
    ADD COLUMN subscription_id BIGINT;

UPDATE alert_topics t
SET subscription_id = s.id
FROM alert_subscriptions s
WHERE s.project_id = t.project_id;

ALTER TABLE alert_topics
    ALTER COLUMN subscription_id SET NOT NULL,
    ADD CONSTRAINT fk_alert_topics_subscription
        FOREIGN KEY (subscription_id)
        REFERENCES alert_subscriptions (id)
        ON DELETE CASCADE;

DROP INDEX idx_alert_topics_project_id;
ALTER TABLE alert_topics
    DROP COLUMN project_id;

CREATE INDEX idx_alert_topics_subscription_id
    ON alert_topics (subscription_id);

-- Alerts: project-scope alerts keep project_id; chat-scope alerts set chat_id instead.
ALTER TABLE alerts
    ADD COLUMN subscription_id BIGINT,
    ADD COLUMN chat_id UUID
        CONSTRAINT fk_alerts_chat
        REFERENCES chats (id) ON DELETE CASCADE;

UPDATE alerts a
SET subscription_id = s.id
FROM alert_subscriptions s
WHERE s.project_id = a.project_id;

ALTER TABLE alerts
    ALTER COLUMN subscription_id SET NOT NULL,
    ALTER COLUMN project_id DROP NOT NULL,
    ADD CONSTRAINT fk_alerts_subscription
        FOREIGN KEY (subscription_id)
        REFERENCES alert_subscriptions (id)
        ON DELETE CASCADE,
    ADD CONSTRAINT ck_alerts_scope
        CHECK ((project_id IS NULL) <> (chat_id IS NULL)),
    DROP CONSTRAINT uq_alerts_project_document,
    ADD CONSTRAINT uq_alerts_subscription_document UNIQUE (subscription_id, document_id);

CREATE INDEX idx_alerts_project_id
    ON alerts (project_id)
    WHERE project_id IS NOT NULL;

CREATE INDEX idx_alerts_chat_id
    ON alerts (chat_id)
    WHERE chat_id IS NOT NULL;

DROP TABLE project_alert_settings;
