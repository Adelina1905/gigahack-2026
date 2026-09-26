CREATE TABLE chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE documents (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    document_link TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE responses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_id UUID NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_responses_chat
        FOREIGN KEY (chat_id)
        REFERENCES chats (id)
        ON DELETE CASCADE
);

CREATE TABLE response_documents (
    response_id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    PRIMARY KEY (response_id, document_id),
    CONSTRAINT fk_response_documents_response
        FOREIGN KEY (response_id)
        REFERENCES responses (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_response_documents_document
        FOREIGN KEY (document_id)
        REFERENCES documents (id)
        ON DELETE CASCADE
);

CREATE INDEX idx_responses_chat_id
    ON responses (chat_id);

CREATE INDEX idx_response_documents_document_id
    ON response_documents (document_id);
