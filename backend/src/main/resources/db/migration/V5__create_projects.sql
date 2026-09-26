CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_projects_client_id_updated_at
    ON projects (client_id, updated_at DESC);

ALTER TABLE chats
    ADD COLUMN project_id UUID
        CONSTRAINT fk_chats_project
        REFERENCES projects (id)
        ON DELETE SET NULL;

CREATE INDEX idx_chats_project_id
    ON chats (project_id);
