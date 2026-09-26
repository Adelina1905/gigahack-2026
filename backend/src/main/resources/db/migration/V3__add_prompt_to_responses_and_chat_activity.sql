ALTER TABLE responses
    ADD COLUMN prompt TEXT;

ALTER TABLE chats
    ADD COLUMN updated_at TIMESTAMPTZ;

UPDATE chats
SET updated_at = COALESCE(
    (SELECT MAX(r.created_at) FROM responses r WHERE r.chat_id = chats.id),
    created_at
);

ALTER TABLE chats
    ALTER COLUMN updated_at SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;

CREATE INDEX idx_chats_client_id_updated_at
    ON chats (client_id, updated_at DESC);
