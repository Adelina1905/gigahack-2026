const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8081/api";

export interface Chat {
    id: string;
    name: string;
    createdAt: string;
}

export interface ChatResponse {
    id: number;
    chatId: string;
    text: string;
    createdAt: string;
}

export interface Document {
    id: number;
    title: string;
    documentLink: string;
    addedAt: string;
}

export interface LlmSource {
    title: string;
    link: string | null;
    quote: string | null;
}

export interface LlmMessageResponse {
    chatId: string;
    text: string;
    mode: "rag" | "llm";
    status: string;
    sources: LlmSource[];
    createdAt: string;
}

interface LlmMessageRequest {
    text: string;
}

interface CreateChatRequest {
    name: string;
}

interface UpdateChatRequest {
    name: string;
}

interface CreateResponseRequest {
    text: string;
}

interface CreateDocumentRequest {
    title: string;
    documentLink: string;
}

async function apiRequest<T>(
    path: string,
    options: RequestInit = {},
): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        credentials: "include",
        headers: {
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...options.headers,
        },
    });

    if (!response.ok) {
        const message = await response.text();
        throw new Error(
            message || `Request failed with status ${response.status}`,
        );
    }

    if (response.status === 204) {
        return null as T;
    }

    return response.json() as Promise<T>;
}

export function getChats(): Promise<Chat[]> {
    return apiRequest<Chat[]>("/chats");
}

export function getChat(chatId: string): Promise<Chat> {
    return apiRequest<Chat>(`/chats/${chatId}`);
}

export function createChat(name = "New chat"): Promise<Chat> {
    const request: CreateChatRequest = { name };

    return apiRequest<Chat>("/chats", {
        method: "POST",
        body: JSON.stringify(request),
    });
}

export function updateChat(chatId: string, name: string): Promise<Chat> {
    const request: UpdateChatRequest = { name };

    return apiRequest<Chat>(`/chats/${chatId}`, {
        method: "PATCH",
        body: JSON.stringify(request),
    });
}

export function deleteChat(chatId: string): Promise<void> {
    return apiRequest<void>(`/chats/${chatId}`, {
        method: "DELETE",
    });
}

export function getResponses(chatId: string): Promise<ChatResponse[]> {
    return apiRequest<ChatResponse[]>(`/chats/${chatId}/responses`);
}

export function getResponse(
    chatId: string,
    responseId: number,
): Promise<ChatResponse> {
    return apiRequest<ChatResponse>(
        `/chats/${chatId}/responses/${responseId}`,
    );
}

export function createResponse(
    chatId: string,
    text: string,
): Promise<ChatResponse> {
    const request: CreateResponseRequest = { text };

    return apiRequest<ChatResponse>(`/chats/${chatId}/responses`, {
        method: "POST",
        body: JSON.stringify(request),
    });
}

export function getDocuments(): Promise<Document[]> {
    return apiRequest<Document[]>("/documents");
}

export function getDocument(documentId: number): Promise<Document> {
    return apiRequest<Document>(`/documents/${documentId}`);
}

export function createDocument(
    title: string,
    documentLink: string,
): Promise<Document> {
    const request: CreateDocumentRequest = { title, documentLink };

    return apiRequest<Document>("/documents", {
        method: "POST",
        body: JSON.stringify(request),
    });
}


export function sendLlmMessage(
    chatId: string,
    text: string,
): Promise<LlmMessageResponse> {
    const request: LlmMessageRequest = { text };

    return apiRequest<LlmMessageResponse>(`/llm/chats/${chatId}/messages`, {
        method: "POST",
        body: JSON.stringify(request),
    });
}

export function clearLlmChat(
    chatId: string,
    options: { keepalive?: boolean } = {},
): Promise<void> {
    return apiRequest<void>(`/llm/chats/${chatId}`, {
        method: "DELETE",
        keepalive: options.keepalive,
    });
}
