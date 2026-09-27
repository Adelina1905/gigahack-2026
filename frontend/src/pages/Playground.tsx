import { useCallback, useEffect, useRef, useState } from "react";
import AlertBell from "../components/alerts/AlertBell";
import AlertsDialog from "../components/alerts/AlertsDialog";
import ChatAlertPrompt, { ChatAlertNotice } from "../components/alerts/ChatAlertPrompt";
import { CityGatesArt, TriumphalArchArt } from "../components/brand/Landmarks";
import ChatWindow from "../components/ChatWindow";
import Sidebar from "../components/Sidebar";
import SiteHeader from "../components/SiteHeader";
import { useActiveChatId } from "../hooks/useActiveChatId";
import { useAlertOfferPreference } from "../hooks/useAlertOfferPreference";
import { alertScopeForChat, useAlertOptIn } from "../hooks/useAlertOptIn";
import { useAlerts } from "../hooks/useAlerts";
import { useChat } from "../hooks/useChat";
import { useChats } from "../hooks/useChats";
import { useProjects } from "../hooks/useProjects";
import { useI18n } from "../i18n/context";
import type { Alert, AlertScope } from "../types/alerts";
import { DEFAULT_CHAT_NAME } from "../types/chat";

function Playground() {
  const { t } = useI18n();
  const [activeChatId, navigate] = useActiveChatId();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const chatList = useChats();
  const projectList = useProjects();
  // The project a chat started from the empty screen will be created in.
  const [draftProjectId, setDraftProjectId] = useState<string | null>(null);
  const alerts = useAlerts();
  const [offerAlerts, setOfferAlerts] = useAlertOfferPreference();
  const optIn = useAlertOptIn(undefined, { enabled: offerAlerts, onEnabled: () => void alerts.refreshUnread() });
  // The subscription whose "Alerts & topics" dialog is open.
  const [alertsTarget, setAlertsTarget] = useState<{ scope: AlertScope; title: string } | null>(null);
  // "Ask about this" sends its question once the target chat is open: the
  // alert's own conversation, or a new draft chat (in the alert's project).
  const pendingAskRef = useRef<
    { chatId: string; text: string } | { chatId: null; projectId: string | null; text: string } | null
  >(null);
  const [askNonce, setAskNonce] = useState(0);

  const chat = useChat(activeChatId, {
    draftProjectId,
    onChatCreated: (created, isActive) => {
      chatList.upsert(created);
      if (created.projectId) projectList.touch(created.projectId);
      // Replace, so Back doesn't return to the empty "new chat" screen.
      if (isActive) {
        setDraftProjectId(null);
        navigate(created.id, { replace: true });
      }
    },
    onReply: (chatId) => void chatList.refresh(chatId),
    onChatMissing: (chatId) => {
      chatList.forget(chatId);
      chat.discard(chatId);
      if (chatId === activeChatId) {
        setDraftProjectId(null);
        navigate(null, { replace: true });
      }
    },
  });

  const openChat = useCallback(
    (chatId: string | null) => {
      if (chatId !== activeChatId) navigate(chatId);
      setIsSidebarOpen(false);
    },
    [activeChatId, navigate],
  );

  const selectChat = (chatId: string) => {
    setDraftProjectId(null);
    openChat(chatId);
  };

  const startNewChat = () => {
    setDraftProjectId(null);
    chat.resetDraft();
    openChat(null);
  };

  const startNewChatInProject = (projectId: string) => {
    setDraftProjectId(projectId);
    chat.resetDraft();
    openChat(null);
  };

  // A new project opens straight into its first chat, which the sidebar lists
  // under the project until the first message creates it on the server.
  const createProject = async (name: string) => {
    const project = await projectList.create(name);
    if (project) startNewChatInProject(project.id);
    return project;
  };

  const moveChat = async (chatId: string, projectId: string | null) => {
    if ((await chatList.moveToProject(chatId, projectId)) && projectId) projectList.touch(projectId);
  };

  const deleteProject = async (projectId: string) => {
    if (draftProjectId === projectId) setDraftProjectId(null);
    const detached = chatList.detachProject(projectId);
    if (!(await projectList.remove(projectId))) chatList.reattachProject(projectId, detached);
  };

  const deleteChat = (chatId: string) => {
    // The chat's own alerts go with it.
    void chatList.remove(chatId).then(() => alerts.refreshUnread());
    chat.discard(chatId);
    if (chatId === activeChatId) {
      setDraftProjectId(null);
      navigate(null, { replace: true });
    }
  };

  const askAboutAlert = (alert: Alert) => {
    void alerts.markRead(alert.id);
    const text = t.alerts.askQuestion(alert.title);
    if (alert.chatId && chatList.chats.some((candidate) => candidate.id === alert.chatId)) {
      pendingAskRef.current = { chatId: alert.chatId, text };
      setDraftProjectId(null);
      openChat(alert.chatId);
      setAskNonce((nonce) => nonce + 1);
      return;
    }
    const projectId = projectList.projects.some((project) => project.id === alert.projectId)
      ? alert.projectId
      : null;
    pendingAskRef.current = { chatId: null, projectId, text };
    if (projectId) startNewChatInProject(projectId);
    else startNewChat();
    setAskNonce((nonce) => nonce + 1);
  };

  const activeChat = chatList.chats.find((candidate) => candidate.id === activeChatId);
  const { send, isLoading: isChatLoading, isTyping } = chat;

  useEffect(() => {
    const pending = pendingAskRef.current;
    if (!pending) return;
    if (pending.chatId !== null) {
      // Waits for the conversation to load and finish any answer in progress.
      if (activeChatId !== pending.chatId || isChatLoading || isTyping) return;
    } else if (activeChatId || draftProjectId !== pending.projectId) {
      return;
    }
    pendingAskRef.current = null;
    send(pending.text);
  }, [askNonce, activeChatId, draftProjectId, send, isChatLoading, isTyping]);

  // The first answer in a chat may offer alerts: for its project when it is
  // in one, otherwise for the chat itself (useAlertOptIn asks the server, and
  // only once per project or chat).
  const hasAnswer = chat.messages.some(
    (message) => message.role === "assistant" && message.generationStatus === "COMPLETED" && message.content.trim(),
  );
  const promptScope = activeChat ? alertScopeForChat(activeChat) : null;
  const promptKind = promptScope?.kind;
  const promptId = promptScope?.id;
  const { consider } = optIn;
  useEffect(() => {
    if (!activeChatId || !promptKind || !promptId || !hasAnswer || !offerAlerts) return;
    void consider({ kind: promptKind, id: promptId }, activeChatId);
  }, [activeChatId, promptKind, promptId, hasAnswer, offerAlerts, consider]);

  const chatTitle = (name: string) => (name === DEFAULT_CHAT_NAME ? t.sidebar.newChat : name);
  const offer = optIn.offer?.chatId === activeChatId ? optIn.offer : null;
  const notice = optIn.notice?.chatId === activeChatId ? optIn.notice : null;
  const alertPrompt = offer ? (
    <ChatAlertPrompt
      scopeKind={offer.scope.kind}
      topics={offer.topics.map((topic) => topic.label)}
      isSaving={optIn.isSaving}
      error={optIn.error}
      onEnable={optIn.enable}
      onDecline={optIn.decline}
    />
  ) : notice ? (
    <ChatAlertNotice message={notice.kind === "enabled" ? t.alerts.prompt.enabled : t.errors.alertsUnavailable} />
  ) : null;



  return (
    <div className="flex h-dvh flex-col bg-background">
      <SiteHeader
        onOpenMenu={() => setIsSidebarOpen(true)}
        actions={
          <AlertBell
            alerts={alerts.alerts}
            unreadTotal={alerts.unread.total}
            projects={projectList.projects}
            chats={chatList.chats}
            offerAlerts={offerAlerts}
            onOfferAlertsChange={setOfferAlerts}
            isLoading={alerts.isLoading}
            error={alerts.error}
            onOpen={() => void alerts.loadAlerts()}
            onMarkRead={(alertId) => void alerts.markRead(alertId)}
            onMarkAllRead={() => void alerts.markAllRead(null)}
            onNotRelevant={(alertId) => void alerts.notRelevant(alertId)}
            onAsk={askAboutAlert}
            onDismissError={alerts.dismissError}
          />
        }
      />

      <main className="flex min-h-0 flex-1">
        <Sidebar
          chats={chatList.chats}
          projects={projectList.projects}
          activeChatId={activeChatId}
          draftProjectId={draftProjectId}
          isLoaded={chatList.isLoaded}
          onNewChat={startNewChat}
          onSelect={selectChat}
          onDelete={deleteChat}
          onMoveChat={(chatId, projectId) => void moveChat(chatId, projectId)}
          onCreateProject={createProject}
          onRenameProject={(projectId, name) => void projectList.rename(projectId, name)}
          onDeleteProject={(projectId) => void deleteProject(projectId)}
          onNewChatInProject={startNewChatInProject}
          unreadAlertsByProject={alerts.unread.byProject}
          onOpenProjectAlerts={(project) => {
            setAlertsTarget({ scope: { kind: "project", id: project.id }, title: project.name });
            setIsSidebarOpen(false);
          }}
          unreadAlertsByChat={alerts.unread.byChat}
          onOpenChatAlerts={(target) => {
            setAlertsTarget({ scope: { kind: "chat", id: target.id }, title: chatTitle(target.name) });
            setIsSidebarOpen(false);
          }}
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
        />

        <div data-chat-main className="relative flex min-w-0 flex-1 flex-col bg-background-canvas transition-[margin] duration-200">
          {/* Landmarks in the margins, like the page background of chisinau.md. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 hidden items-end justify-between px-6 text-primary opacity-[0.09] xl:flex"
          >
            <TriumphalArchArt className="h-40 2xl:h-52" />
            <CityGatesArt className="h-48 2xl:h-64" />
          </div>

          <div className="relative mx-auto min-h-0 w-full max-w-3xl flex-1">
            <ChatWindow
              chatId={activeChatId}
              messages={chat.messages}
              isTyping={chat.isTyping}
              isLoading={chat.isLoading}
              hasChats={chatList.chats.length > 0 ? true : chatList.isLoaded ? false : null}
              onSend={chat.send}
              onRetry={chat.retry}
              onRegenerate={chat.regenerate}
              error={chat.error ?? chatList.error ?? projectList.error}
              onDismissError={() => {
                chat.dismissError();
                chatList.dismissError();
                projectList.dismissError();
              }}
              alertPrompt={alertPrompt}
            />
          </div>
        </div>
      </main>

      {alertsTarget && (
        <AlertsDialog
          key={`${alertsTarget.scope.kind}:${alertsTarget.scope.id}`}
          scope={alertsTarget.scope}
          title={alertsTarget.title}
          onClose={() => setAlertsTarget(null)}
          onAlertsChanged={() => void alerts.refreshUnread()}
        />
      )}
    </div>
  );
}

export default Playground;
