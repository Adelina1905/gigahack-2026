ALTER TABLE chats
    ADD COLUMN client_id UUID;

UPDATE chats
SET client_id = gen_random_uuid()
WHERE client_id IS NULL;

ALTER TABLE chats
    ALTER COLUMN client_id SET NOT NULL;

CREATE INDEX idx_chats_client_id_created_at
    ON chats (client_id, created_at DESC);

