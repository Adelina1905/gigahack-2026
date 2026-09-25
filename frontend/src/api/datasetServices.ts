import type { AssistantResponse, DatasetService } from "./types.ts";

const BASE_URL: string = (import.meta as unknown as { env?: Record<string, string> }).env
  ?.VITE_API_BASE_URL || '/api';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res =await fetch(`${BASE_URL}${path}`, {
    headers: new Headers({ 'Content-Type': 'application/json' }),
    credentials: 'include',
    ...options,
  });
  if (!res.ok) {
    throw new Error(
      `Request failed: ${options.method || 'GET'} ${path} (${res.status})`
    );
  }
  if (res.status === 204) return null as T;
  return res.json() as Promise<T>;
}
const realDataService: DatasetService = {
  async createResponse(chatId) {
    return request<AssistantResponse>(`/chats/${chatId}/messages`);
  }
}

export default realDataService;