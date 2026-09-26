import type {
    ChatCreateRequest,
    ChatUpdateRequest,
    ChatView,
    DocumentCreateRequest,
    DocumentView,
    ResponseCreateRequest,
    ResponseView,
} from "./types";

const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080/api";

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
                ...(options.body ? { "Content-Type": "application/json" } : {}),
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

export function getChats(): Promise<ChatView[]> {
    return apiRequest<ChatView[]>("/chats");
}

export function getChat(chatId: string): Promise<ChatView> {
    return apiRequest<ChatView>(`/chats/${chatId}`);
}

export function createChat(name = "New chat"): Promise<ChatView> {
    const request: ChatCreateRequest = { name };

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
): Promise<ResponseView> {
    const request: ResponseCreateRequest = { text };

    return apiRequest<ResponseView>(`/chats/${chatId}/responses`, {
        method: "POST",
        body: JSON.stringify(request),
    });
}

// Re-asks the AI with the stored prompt and replaces the answer in place.
export function regenerateResponse(
    chatId: string,
    responseId: number,
): Promise<ResponseView> {
    return apiRequest<ResponseView>(
        `/chats/${chatId}/responses/${responseId}`,
        { method: "PUT" },
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
