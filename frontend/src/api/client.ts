const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080/api";

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

interface CreateChatRequest {
    name: string;
}

interface UpdateChatRequest {
    name: string;
}

interface CreateResponseRequest {
    text: string;
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

