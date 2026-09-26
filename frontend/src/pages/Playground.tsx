import { useCallback, useState } from "react";
import ChatWindow from "../components/ChatWindow";
import Sidebar from "../components/Sidebar";
import { useActiveChatId } from "../hooks/useActiveChatId";
import { useChat } from "../hooks/useChat";
import { useChats } from "../hooks/useChats";

function Playground() {
  const [activeChatId, navigate] = useActiveChatId();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const chatList = useChats();

  const chat = useChat(activeChatId, {
    onChatCreated: (created, isActive) => {
      chatList.upsert(created);
      // Replace, so Back doesn't return to the empty "new chat" screen.
      if (isActive) navigate(created.id, { replace: true });
    },
    onReply: (chatId) => void chatList.refresh(chatId),
    onChatMissing: (chatId) => {
      chatList.forget(chatId);
      chat.discard(chatId);
      if (chatId === activeChatId) navigate(null, { replace: true });
    },
  });

  const openChat = useCallback(
    (chatId: string | null) => {
      if (chatId !== activeChatId) navigate(chatId);
      setIsSidebarOpen(false);
    },
    [activeChatId, navigate],
  );

  const startNewChat = () => {
    chat.resetDraft();
    openChat(null);
  };

  const deleteChat = (chatId: string) => {
    void chatList.remove(chatId);
    chat.discard(chatId);
    if (chatId === activeChatId) navigate(null, { replace: true });
  };

  const activeName = chatList.chats.find((candidate) => candidate.id === activeChatId)?.name;

  return (
    <main className="flex h-screen bg-background">
      <Sidebar
        chats={chatList.chats}
        activeChatId={activeChatId}
        isLoaded={chatList.isLoaded}
        onNewChat={startNewChat}
        onSelect={openChat}
        onRename={(chatId, name) => void chatList.rename(chatId, name)}
        onDelete={deleteChat}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-border px-3 py-2 md:hidden">
          <button
            type="button"
            onClick={() => setIsSidebarOpen(true)}
            aria-label="Open chat history"
            className="rounded-lg p-2 text-text-muted hover:bg-background-secondary"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="truncate text-sm font-medium text-text">{activeName ?? "New chat"}</span>
        </header>

        <div className="mx-auto min-h-0 w-full max-w-2xl flex-1">
          <ChatWindow
            chatId={activeChatId}
            messages={chat.messages}
            isTyping={chat.isTyping}
            isLoading={chat.isLoading}
            onSend={chat.send}
            onRetry={chat.retry}
            onRegenerate={chat.regenerate}
            error={chat.error ?? chatList.error}
            onDismissError={() => {
              chat.dismissError();
              chatList.dismissError();
            }}
          />
        </div>
      </div>
    </main>
  );
}

export default Playground;
