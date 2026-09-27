import type {
    AlertFeedbackRequest,
    AlertReadAllRequest,
    AlertReadAllView,
    AlertScanView,
    AlertSettingsUpdateRequest,
    AlertSettingsView,
    AlertTopicRequest,
    AlertTopicView,
    AlertUnreadCountView,
    AlertView,
    ChatCreateRequest,
    ChatProjectRequest,
    ChatView,
    DocumentCreateRequest,
    DocumentView,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    ProjectView,
    ResponseCreateRequest,
    ResponseRegenerateRequest,
    ResponseView,
    SourcePreviewView,
    TranscriptionView,
} from "./types";
import { DEFAULT_CHAT_NAME } from "../types/chat";

const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ?? "/api";

export function getSourceOpenUrl(documentId: string, versionId?: string | null): string {
    const params = new URLSearchParams();
    if (versionId) params.set("versionId", versionId);
    const search = params.toString();
    return `${API_BASE_URL}/sources/${encodeURIComponent(documentId)}/open${search ? `?${search}` : ""}`;
}

// status is 0 when the request never reached the server (offline, CORS, backend down).
export class ApiError extends Error {
    readonly status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

// Spring's default error body is { status, error, message, path, ... }.
async function readErrorMessage(response: Response): Promise<string> {
    const fallback = `Request failed with status ${response.status}`;
    const body = await response.text().catch(() => "");
    if (!body) return fallback;

    try {
        const json = JSON.parse(body) as { message?: string; error?: string };
        return json.message || json.error || fallback;
    } catch {
        return body;
    }
}

async function apiRequest<T>(
    path: string,
    options: RequestInit = {},
): Promise<T> {
    let response: Response;

    try {
        response = await fetch(`${API_BASE_URL}${path}`, {
            ...options,
            credentials: "include",
            headers: {
                ...(options.body && !(options.body instanceof FormData)
                    ? { "Content-Type": "application/json" }
                    : {}),
                ...options.headers,
            },
        });
    } catch (error) {
        throw new ApiError(
            error instanceof Error ? error.message : "Network error",
            0,
        );
    }

    if (!response.ok) {
        throw new ApiError(await readErrorMessage(response), response.status);
    }

    if (response.status === 204) {
        return null as T;
    }

    return response.json() as Promise<T>;
}

async function apiBlobRequest(path: string, options: RequestInit): Promise<Blob> {
    let response: Response;
    try {
        response = await fetch(`${API_BASE_URL}${path}`, {
            ...options,
            credentials: "include",
            headers: { ...options.headers },
        });
    } catch (error) {
        throw new ApiError(error instanceof Error ? error.message : "Network error", 0);
    }
    if (!response.ok) throw new ApiError(await readErrorMessage(response), response.status);
    return response.blob();
}

export function getChats(): Promise<ChatView[]> {
    return apiRequest<ChatView[]>("/chats");
}

export function getChat(chatId: string): Promise<ChatView> {
    return apiRequest<ChatView>(`/chats/${chatId}`);
}

export function createChat(
    name = DEFAULT_CHAT_NAME,
    requestId?: string,
    projectId?: string | null,
): Promise<ChatView> {
    const request: ChatCreateRequest = { name, requestId, projectId: projectId ?? undefined };

    return apiRequest<ChatView>("/chats", {
        method: "POST",
        body: JSON.stringify(request),
    });
}

export function deleteChat(chatId: string): Promise<void> {
    return apiRequest<void>(`/chats/${chatId}`, {
        method: "DELETE",
    });
}

// null takes the chat out of its project.
export function setChatProject(chatId: string, projectId: string | null): Promise<ChatView> {
    const request: ChatProjectRequest = { projectId };

    return apiRequest<ChatView>(`/chats/${chatId}/project`, {
        method: "PUT",
        body: JSON.stringify(request),
    });
}

export function getProjects(): Promise<ProjectView[]> {
    return apiRequest<ProjectView[]>("/projects");
}

export function createProject(name: string): Promise<ProjectView> {
    const request: ProjectCreateRequest = { name };

    return apiRequest<ProjectView>("/projects", {
        method: "POST",
        body: JSON.stringify(request),
    });
}

export function updateProject(projectId: string, name: string): Promise<ProjectView> {
    const request: ProjectUpdateRequest = { name };

    return apiRequest<ProjectView>(`/projects/${projectId}`, {
        method: "PATCH",
        body: JSON.stringify(request),
    });
}

// The project's chats are kept and move back to the ungrouped list.
export function deleteProject(projectId: string): Promise<void> {
    return apiRequest<void>(`/projects/${projectId}`, {
        method: "DELETE",
    });
}

export function getResponses(chatId: string): Promise<ResponseView[]> {
    return apiRequest<ResponseView[]>(`/chats/${chatId}/responses`);
}

export function getResponse(
    chatId: string,
    responseId: number,
): Promise<ResponseView> {
    return apiRequest<ResponseView>(
        `/chats/${chatId}/responses/${responseId}`,
    );
}

export function createResponse(
    chatId: string,
    text: string,
    requestId?: string,
): Promise<ResponseView> {
    const request: ResponseCreateRequest = { text, requestId };

    return apiRequest<ResponseView>(`/chats/${chatId}/responses`, {
        method: "POST",
        body: JSON.stringify(request),
    });
}

// Re-asks the AI with the stored prompt and replaces the answer in place.
export function regenerateResponse(
    chatId: string,
    responseId: number,
    request: ResponseRegenerateRequest,
): Promise<ResponseView> {
    return apiRequest<ResponseView>(
        `/chats/${chatId}/responses/${responseId}`,
        { method: "PUT", body: JSON.stringify(request) },
    );
}

export function getDocuments(): Promise<DocumentView[]> {
    return apiRequest<DocumentView[]>("/documents");
}

export function getDocument(documentId: number): Promise<DocumentView> {
    return apiRequest<DocumentView>(`/documents/${documentId}`);
}

export function createDocument(
    title: string,
    documentLink: string,
): Promise<DocumentView> {
    const request: DocumentCreateRequest = { title, documentLink };

    return apiRequest<DocumentView>("/documents", {
        method: "POST",
        body: JSON.stringify(request),
    });
}

export function getSourcePreview(
    documentId: string,
    options: { versionId?: string | null; focusEvidenceId?: string | null; start?: number; limit?: number; signal?: AbortSignal } = {},
): Promise<SourcePreviewView> {
    const params = new URLSearchParams();
    if (options.versionId) params.set("versionId", options.versionId);
    if (options.focusEvidenceId) params.set("focusEvidenceId", options.focusEvidenceId);
    if (options.start !== undefined) params.set("start", String(options.start));
    params.set("limit", String(options.limit ?? 40));
    return apiRequest<SourcePreviewView>(
        `/sources/${encodeURIComponent(documentId)}/preview?${params}`,
        { signal: options.signal },
    );
}

// language is the UI language when the recording is sent; the speech-to-text
// service uses it as a hint instead of guessing between Romanian and Russian.
export function transcribeAudio(audio: Blob, extension: string, language?: string): Promise<TranscriptionView> {
    const form = new FormData();
    form.append("audio", audio, `recording.${extension}`);
    if (language) form.append("language", language);
    return apiRequest<TranscriptionView>("/voice/transcriptions", {
        method: "POST",
        body: form,
    });
}

export function getResponseSpeech(chatId: string, responseId: number): Promise<Blob> {
    return apiBlobRequest(`/chats/${chatId}/responses/${responseId}/speech`, {
        method: "POST",
        headers: { Accept: "audio/mpeg" },
    });
}

export interface AlertListQuery {
    projectId?: string | null;
    chatId?: string | null;
    unreadOnly?: boolean;
    limit?: number;
}

// Newest first; alerts marked "not relevant" are never listed.
export function getAlerts(query: AlertListQuery = {}): Promise<AlertView[]> {
    const params = new URLSearchParams();
    if (query.projectId) params.set("projectId", query.projectId);
    if (query.chatId) params.set("chatId", query.chatId);
    if (query.unreadOnly) params.set("unreadOnly", "true");
    if (query.limit) params.set("limit", String(query.limit));
    const search = params.toString();
    return apiRequest<AlertView[]>(`/alerts${search ? `?${search}` : ""}`);
}

export function getAlertUnreadCount(): Promise<AlertUnreadCountView> {
    return apiRequest<AlertUnreadCountView>("/alerts/unread-count");
}

export function markAlertRead(alertId: number): Promise<AlertView> {
    return apiRequest<AlertView>(`/alerts/${alertId}/read`, { method: "POST" });
}

// One project's or one chat's alerts; neither marks every alert as read.
export function markAllAlertsRead(request: AlertReadAllRequest = {}): Promise<AlertReadAllView> {
    const body: AlertReadAllRequest = { projectId: request.projectId ?? null, chatId: request.chatId ?? null };
    return apiRequest<AlertReadAllView>("/alerts/read-all", {
        method: "POST",
        body: JSON.stringify(body),
    });
}

// Dismisses the alert for good and makes its topic stricter.
export function markAlertNotRelevant(alertId: number): Promise<void> {
    const request: AlertFeedbackRequest = { value: "NOT_RELEVANT" };
    return apiRequest<void>(`/alerts/${alertId}/feedback`, {
        method: "POST",
        body: JSON.stringify(request),
    });
}

// A project's subscription lives under /projects/{id}, a chat's own one under
// /chats/{id}; both have the same endpoints and behaviour.
const projectBase = (projectId: string) => `/projects/${projectId}`;
const chatBase = (chatId: string) => `/chats/${chatId}`;

function getSettingsAt(base: string): Promise<AlertSettingsView> {
    return apiRequest<AlertSettingsView>(`${base}/alert-settings`);
}

function updateSettingsAt(base: string, enabled: boolean): Promise<AlertSettingsView> {
    const request: AlertSettingsUpdateRequest = { enabled };
    return apiRequest<AlertSettingsView>(`${base}/alert-settings`, {
        method: "PUT",
        body: JSON.stringify(request),
    });
}

function refreshTopicsAt(base: string): Promise<AlertSettingsView> {
    return apiRequest<AlertSettingsView>(`${base}/alert-topics/refresh`, { method: "POST" });
}

function createTopicAt(base: string, label: string): Promise<AlertTopicView> {
    const request: AlertTopicRequest = { label };
    return apiRequest<AlertTopicView>(`${base}/alert-topics`, {
        method: "POST",
        body: JSON.stringify(request),
    });
}

function updateTopicAt(base: string, topicId: number, label: string): Promise<AlertTopicView> {
    const request: AlertTopicRequest = { label };
    return apiRequest<AlertTopicView>(`${base}/alert-topics/${topicId}`, {
        method: "PATCH",
        body: JSON.stringify(request),
    });
}

function deleteTopicAt(base: string, topicId: number): Promise<void> {
    return apiRequest<void>(`${base}/alert-topics/${topicId}`, { method: "DELETE" });
}

function scanAt(base: string): Promise<AlertScanView> {
    return apiRequest<AlertScanView>(`${base}/alerts/scan`, { method: "POST" });
}

export function getAlertSettings(projectId: string): Promise<AlertSettingsView> {
    return getSettingsAt(projectBase(projectId));
}

// Also records that the opt-in was answered; turning alerts on runs a first scan.
export function updateAlertSettings(projectId: string, enabled: boolean): Promise<AlertSettingsView> {
    return updateSettingsAt(projectBase(projectId), enabled);
}

// Extracts topics from all of the project's questions.
export function refreshAlertTopics(projectId: string): Promise<AlertSettingsView> {
    return refreshTopicsAt(projectBase(projectId));
}

export function createAlertTopic(projectId: string, label: string): Promise<AlertTopicView> {
    return createTopicAt(projectBase(projectId), label);
}

export function updateAlertTopic(projectId: string, topicId: number, label: string): Promise<AlertTopicView> {
    return updateTopicAt(projectBase(projectId), topicId, label);
}

export function deleteAlertTopic(projectId: string, topicId: number): Promise<void> {
    return deleteTopicAt(projectBase(projectId), topicId);
}

// Looks for new matching documents now, even while alerts are off.
export function scanProjectAlerts(projectId: string): Promise<AlertScanView> {
    return scanAt(projectBase(projectId));
}

export function getChatAlertSettings(chatId: string): Promise<AlertSettingsView> {
    return getSettingsAt(chatBase(chatId));
}

export function updateChatAlertSettings(chatId: string, enabled: boolean): Promise<AlertSettingsView> {
    return updateSettingsAt(chatBase(chatId), enabled);
}

// Extracts topics from the chat's own questions.
export function refreshChatAlertTopics(chatId: string): Promise<AlertSettingsView> {
    return refreshTopicsAt(chatBase(chatId));
}

export function createChatAlertTopic(chatId: string, label: string): Promise<AlertTopicView> {
    return createTopicAt(chatBase(chatId), label);
}

export function updateChatAlertTopic(chatId: string, topicId: number, label: string): Promise<AlertTopicView> {
    return updateTopicAt(chatBase(chatId), topicId, label);
}

export function deleteChatAlertTopic(chatId: string, topicId: number): Promise<void> {
    return deleteTopicAt(chatBase(chatId), topicId);
}

export function scanChatAlerts(chatId: string): Promise<AlertScanView> {
    return scanAt(chatBase(chatId));
}
