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
    ChatUpdateRequest,
    ChatView,
    DocumentCreateRequest,
    DocumentView,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    ProjectView,
    ResponseCreateRequest,
    ResponseRegenerateRequest,
    ResponseView,
    TranscriptionView,
} from "./types";
import { DEFAULT_CHAT_NAME } from "../types/chat";

const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ?? "/api";

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

export function updateChat(chatId: string, name: string): Promise<ChatView> {
    const request: ChatUpdateRequest = { name };

    return apiRequest<ChatView>(`/chats/${chatId}`, {
        method: "PATCH",
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

export function transcribeAudio(audio: Blob, extension: string): Promise<TranscriptionView> {
    const form = new FormData();
    form.append("audio", audio, `recording.${extension}`);
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
    unreadOnly?: boolean;
    limit?: number;
}

// Newest first; alerts marked "not relevant" are never listed.
export function getAlerts(query: AlertListQuery = {}): Promise<AlertView[]> {
    const params = new URLSearchParams();
    if (query.projectId) params.set("projectId", query.projectId);
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

// null marks the alerts of every project as read.
export function markAllAlertsRead(projectId: string | null = null): Promise<AlertReadAllView> {
    const request: AlertReadAllRequest = { projectId };
    return apiRequest<AlertReadAllView>("/alerts/read-all", {
        method: "POST",
        body: JSON.stringify(request),
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

export function getAlertSettings(projectId: string): Promise<AlertSettingsView> {
    return apiRequest<AlertSettingsView>(`/projects/${projectId}/alert-settings`);
}

// Also records that the opt-in was answered; turning alerts on runs a first scan.
export function updateAlertSettings(projectId: string, enabled: boolean): Promise<AlertSettingsView> {
    const request: AlertSettingsUpdateRequest = { enabled };
    return apiRequest<AlertSettingsView>(`/projects/${projectId}/alert-settings`, {
        method: "PUT",
        body: JSON.stringify(request),
    });
}

// Extracts topics from all of the project's questions.
export function refreshAlertTopics(projectId: string): Promise<AlertSettingsView> {
    return apiRequest<AlertSettingsView>(`/projects/${projectId}/alert-topics/refresh`, {
        method: "POST",
    });
}

export function createAlertTopic(projectId: string, label: string): Promise<AlertTopicView> {
    const request: AlertTopicRequest = { label };
    return apiRequest<AlertTopicView>(`/projects/${projectId}/alert-topics`, {
        method: "POST",
        body: JSON.stringify(request),
    });
}

export function updateAlertTopic(projectId: string, topicId: number, label: string): Promise<AlertTopicView> {
    const request: AlertTopicRequest = { label };
    return apiRequest<AlertTopicView>(`/projects/${projectId}/alert-topics/${topicId}`, {
        method: "PATCH",
        body: JSON.stringify(request),
    });
}

export function deleteAlertTopic(projectId: string, topicId: number): Promise<void> {
    return apiRequest<void>(`/projects/${projectId}/alert-topics/${topicId}`, {
        method: "DELETE",
    });
}

// Looks for new matching documents now, even while alerts are off.
export function scanProjectAlerts(projectId: string): Promise<AlertScanView> {
    return apiRequest<AlertScanView>(`/projects/${projectId}/alerts/scan`, { method: "POST" });
}
