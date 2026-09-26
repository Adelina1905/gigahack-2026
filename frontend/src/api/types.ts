// Wire types mirroring the Spring Boot DTOs in backend/src/main/java/smart_city/backend.
// Keep field names identical to the Java records; map to UI types in ./mappers.

// Chat/dto/ChatResponse.java
export interface ChatView {
  id: string; // UUID
  name: string;
  projectId: string | null; // UUID of the project the chat is filed under
  createdAt: string; // ISO 8601
  updatedAt: string; // ISO 8601, bumped on every new or regenerated reply
}

// Project/dto/ProjectResponse.java
export interface ProjectView {
  id: string; // UUID
  name: string;
  createdAt: string; // ISO 8601
  updatedAt: string; // ISO 8601, bumped on rename and when a chat is added
  chats: ChatView[]; // ordered by updatedAt desc
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
  projectId?: string;
}

export interface ChatProjectRequest {
  projectId: string | null;
}

export interface ProjectCreateRequest {
  name: string;
}

export interface ProjectUpdateRequest {
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

// Alert/dto/AlertView.java — one matched document for one project or one chat.
// Exactly one of projectId and chatId is set.
export interface AlertView {
  id: number;
  projectId: string | null; // UUID of a project subscription
  chatId: string | null; // UUID of a chat's own subscription
  topicId: number | null; // null once the topic was deleted
  topicLabel: string; // the topic's label when the alert was created
  documentId: string;
  title: string;
  url: string | null;
  source: string | null;
  district: string | null;
  category: string | null;
  publishedDate: string | null; // YYYY-MM-DD
  excerpt: string;
  score: number;
  createdAt: string; // ISO 8601
  readAt: string | null; // ISO 8601
}

export interface AlertUnreadCountView {
  total: number;
  byProject: Record<string, number>; // project UUID -> unread alerts
  byChat: Record<string, number>; // chat UUID -> unread alerts of the chat's own subscription
}

export interface AlertTopicView {
  id: number;
  label: string;
  query: string;
  source: "AUTO" | "USER";
  minScore: number | null;
}

// One subscription: a project's or a chat's (exactly one id is set).
export interface AlertSettingsView {
  projectId: string | null; // UUID
  chatId: string | null; // UUID
  enabled: boolean;
  // True once the one-time opt-in was answered either way.
  prompted: boolean;
  topics: AlertTopicView[]; // not removed, oldest first
  lastScanAt: string | null; // ISO 8601
}

// Neither id marks every alert as read.
export interface AlertReadAllRequest {
  projectId?: string | null;
  chatId?: string | null;
}

export interface AlertReadAllView {
  updated: number;
}

export interface AlertFeedbackRequest {
  value: "NOT_RELEVANT";
}

export interface AlertSettingsUpdateRequest {
  enabled: boolean;
}

export interface AlertTopicRequest {
  label: string;
}

export interface AlertScanView {
  created: number;
  matcher: string;
}
