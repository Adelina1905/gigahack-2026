const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080/api";

async function apiRequest(path, options = {}) {
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
        return null;
    }

    return response.json();
}

export function getChats() {
    return apiRequest("/chats");
}

export function getChat(chatId) {
    return apiRequest(`/chats/${chatId}`);
}

export function createChat(name = "New chat") {
    return apiRequest("/chats", {
        method: "POST",
        body: JSON.stringify({ name }),
    });
}

export function updateChat(chatId, name) {
    return apiRequest(`/chats/${chatId}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
    });
}

export function deleteChat(chatId) {
    return apiRequest(`/chats/${chatId}`, {
        method: "DELETE",
    });
}
