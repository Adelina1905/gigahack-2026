ALTER TABLE chats ADD COLUMN request_id UUID;
ALTER TABLE chats ADD COLUMN creation_name VARCHAR(255);
CREATE UNIQUE INDEX uq_chats_client_request ON chats (client_id, request_id)
    WHERE request_id IS NOT NULL;

ALTER TABLE responses
    ALTER COLUMN text DROP NOT NULL,
    ADD COLUMN request_id UUID NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN generation_status VARCHAR(16) NOT NULL DEFAULT 'COMPLETED',
    ADD COLUMN generation_version INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN generation_request_id UUID,
    ADD COLUMN generation_started_at TIMESTAMPTZ,
    ADD COLUMN generation_expires_at TIMESTAMPTZ,
    ADD COLUMN error_code VARCHAR(64),
    ADD COLUMN ai_reply JSONB,
    ADD CONSTRAINT ck_response_generation_status
        CHECK (generation_status IN ('PENDING', 'COMPLETED', 'FAILED'));

CREATE UNIQUE INDEX uq_responses_chat_request ON responses (chat_id, request_id);
CREATE UNIQUE INDEX uq_responses_pending_chat ON responses (chat_id)
    WHERE generation_status = 'PENDING';
CREATE INDEX idx_responses_expired_generation ON responses (generation_expires_at)
    WHERE generation_status = 'PENDING';
