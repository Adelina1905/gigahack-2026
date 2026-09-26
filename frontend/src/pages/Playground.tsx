import { useCallback, useState } from "react";
import { CityGatesArt, TriumphalArchArt } from "../components/brand/Landmarks";
import ChatWindow from "../components/ChatWindow";
import Sidebar from "../components/Sidebar";
import SiteHeader from "../components/SiteHeader";
import { useActiveChatId } from "../hooks/useActiveChatId";
import { useChat } from "../hooks/useChat";
import { useChats } from "../hooks/useChats";
import { useI18n } from "../i18n/context";
import { DEFAULT_CHAT_NAME } from "../types/chat";

function Playground() {
  const { t } = useI18n();
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
    <div className="flex h-dvh flex-col bg-background">
      <SiteHeader onOpenMenu={() => setIsSidebarOpen(true)} />

      <main className="flex min-h-0 flex-1">
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

        <div className="relative flex min-w-0 flex-1 flex-col bg-background-canvas">
          {/* Landmarks in the margins, like the page background of chisinau.md. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 hidden items-end justify-between px-6 text-primary opacity-[0.09] xl:flex"
          >
            <TriumphalArchArt className="h-40 2xl:h-52" />
            <CityGatesArt className="h-48 2xl:h-64" />
          </div>

          <nav aria-label={t.breadcrumb} className="relative border-b border-border bg-background/70 px-4 py-2.5">
            <ol className="mx-auto flex max-w-3xl items-center gap-2 px-4 text-sm">
              <li className="shrink-0 text-primary">{t.sidebar.title}</li>
              <li aria-hidden="true" className="text-text-subtle">/</li>
              <li aria-current="page" className="truncate text-text-muted">
                {!activeName || activeName === DEFAULT_CHAT_NAME ? t.sidebar.newChat : activeName}
              </li>
            </ol>
          </nav>

          <div className="relative mx-auto min-h-0 w-full max-w-3xl flex-1">
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
    </div>
  );
}

export default Playground;
