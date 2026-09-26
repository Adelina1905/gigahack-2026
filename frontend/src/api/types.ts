// Wire types mirroring the Spring Boot DTOs in backend/src/main/java/smart_city/backend.
// Keep field names identical to the Java records; map to UI types in ./mappers.

// Chat/dto/ChatResponse.java
export interface ChatView {
  id: string; // UUID
  name: string;
  createdAt: string; // ISO 8601
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
  text: string;
  createdAt: string; // ISO 8601
  // Not sent by the backend yet; populated once response_documents is exposed.
  documents?: DocumentView[];
}

export interface ChatCreateRequest {
  name?: string;
}

export interface ChatUpdateRequest {
  name: string;
}

export interface ResponseCreateRequest {
  text: string;
}

export interface DocumentCreateRequest {
  title: string;
  documentLink: string;
}
