import "fake-indexeddb/auto";
import { expect, it } from "vitest";
import { loadMessages, saveMessages, moveDraft, removeChat } from "../src/db/cache";

it("persists the initial outbox before a chat exists and moves its IDs intact", async () => {
  const message = { id: "outbox", requestId: "request", chatRequestId: "chat-request",
    role: "user" as const, content: "Keep this", createdAt: 1, status: "sending" as const };
  await saveMessages("draft", [message]);
  expect(await loadMessages("draft")).toEqual([message]);
  await moveDraft("saved-chat", [message]);
  expect(await loadMessages("draft")).toBeNull();
  expect(await loadMessages("saved-chat")).toEqual([message]);
  await removeChat("saved-chat");
});
