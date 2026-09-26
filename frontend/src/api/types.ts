// Wire types mirroring the Spring Boot DTOs in backend/src/main/java/smart_city/backend.
// Keep field names identical to the Java records; map to UI types in ./mappers.

// Chat/dto/ChatResponse.java
export interface ChatView {
  id: string; // UUID
  name: string;
  createdAt: string; // ISO 8601
  updatedAt: string; // ISO 8601, bumped on every new or regenerated reply
}

// Document/dto/DocumentView.java
export interface DocumentView {
  id: number;
  title: string;
  documentLink: string;
  addedAt: string; // ISO 8601
}

// Response/dto/ResponseView.java
export interface ResponseView {
  id: number;
  chatId: string;
  // The user message this response answers; null for rows stored before V3.
  prompt: string | null;
  text: string | null;
  createdAt: string; // ISO 8601
  documents?: DocumentView[];
  requestId?: string | null;
  generationStatus?: "PENDING" | "COMPLETED" | "FAILED";
  generationVersion?: number;
  errorCode?: string | null;
  aiReply?: {
    mode: "rag" | "llm" | "demo";
    status: string;
    answer: string;
    citations: Array<{
      title: string | null;
      url: string | null;
      exactQuote: string | null;
      documentId: string | null;
    }>;
    clarificationChoices: Array<{ documentId: string; label: string }> | null;
  } | null;
}

export interface ChatCreateRequest {
  name?: string;
  requestId?: string;
}

export interface ChatUpdateRequest {
  name: string;
}

export interface ResponseCreateRequest {
  text: string;
  requestId?: string;
}

export interface ResponseRegenerateRequest {
  requestId: string;
  expectedGenerationVersion: number;
}

export interface TranscriptionView {
    text: string;
    language?: string | null;
    durationSeconds?: number | null;
}

export interface DocumentCreateRequest {
  title: string;
  documentLink: string;
}
