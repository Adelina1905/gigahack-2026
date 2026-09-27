import { useCallback, useEffect, useRef, useState } from "react";
import AlertBell from "../components/alerts/AlertBell";
import { CityGatesArt, TriumphalArchArt } from "../components/brand/Landmarks";
import ChatWindow from "../components/ChatWindow";
import Sidebar from "../components/Sidebar";
import SiteHeader from "../components/SiteHeader";
import TrackersView from "../components/trackers/TrackersView";
import PlanNotificationToast from "../components/notifications/PlanNotificationToast";
import { useActiveChatId } from "../hooks/useActiveChatId";
import { useAlerts } from "../hooks/useAlerts";
import { useChat } from "../hooks/useChat";
import { useChats } from "../hooks/useChats";
import { useProjects } from "../hooks/useProjects";
import { useTrackers } from "../hooks/useTrackers";
import { usePlanNotifications } from "../hooks/usePlanNotifications";
import { useDemoNotificationShortcut } from "../hooks/useDemoNotificationShortcut";
import { useI18n } from "../i18n/context";
import { draftPlanFromChat, type PlanDraft } from "../trackers/planDraft";
import type { Alert } from "../types/alerts";
import type { ProjectSummary } from "../types/chat";

function Playground() {
  const { t } = useI18n();
  const [activeChatId, navigate] = useActiveChatId();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const chatList = useChats();
  const projectList = useProjects();
  const trackerList = useTrackers();
  const planNotifications = usePlanNotifications();
  const [toastIds, setToastIds] = useState<string[]>([]);
  const [workspace, setWorkspace] = useState<"chat" | "trackers">("chat");
  const [selectedTrackerId, setSelectedTrackerId] = useState<string | null>(null);
  // undefined = overview; null = generic guided setup; project = setup from that project/conversation.
  const [trackerConversationProject, setTrackerConversationProject] = useState<ProjectSummary | null | undefined>(undefined);
  // Answers guessed from the chat when setup starts from "Continue with this plan".
  const [trackerDraft, setTrackerDraft] = useState<PlanDraft | null>(null);
  const setTrackerSetup = useCallback((project: ProjectSummary | null | undefined, draft: PlanDraft | null = null) => {
    setTrackerConversationProject(project);
    setTrackerDraft(draft);
  }, []);
  // The project a chat started from the empty screen will be created in.
  const [draftProjectId, setDraftProjectId] = useState<string | null>(null);
  const alerts = useAlerts();
  // "Ask about this" sends its question once the new draft chat is open.
  const pendingAskRef = useRef<{ projectId: string | null; text: string } | null>(null);
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
      setWorkspace("chat");
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
    void chatList.remove(chatId);
    chat.discard(chatId);
    if (chatId === activeChatId) {
      setDraftProjectId(null);
      navigate(null, { replace: true });
    }
  };

  const askAboutAlert = (alert: Alert) => {
    void alerts.markRead(alert.id);
    const projectId = projectList.projects.some((project) => project.id === alert.projectId)
      ? alert.projectId
      : null;
    pendingAskRef.current = { projectId, text: t.alerts.askQuestion(alert.title) };
    if (projectId) startNewChatInProject(projectId);
    else startNewChat();
    setAskNonce((nonce) => nonce + 1);
  };

  const activeChat = chatList.chats.find((candidate) => candidate.id === activeChatId);
  const { send } = chat;

  useEffect(() => {
    const pending = pendingAskRef.current;
    if (!pending || activeChatId || draftProjectId !== pending.projectId) return;
    pendingAskRef.current = null;
    send(pending.text);
  }, [askNonce, activeChatId, draftProjectId, send]);

  const activeProjectId = activeChatId ? activeChat?.projectId : draftProjectId;
  const activeProject = projectList.projects.find((project) => project.id === activeProjectId);

  const openPlanNotification = (notificationId: string) => {
    const notification = planNotifications.notifications.find((item) => item.id === notificationId);
    if (!notification) return;
    planNotifications.markRead(notification.id);
    setToastIds((current) => current.filter((id) => id !== notification.id));
    setTrackerSetup(undefined);
    setSelectedTrackerId(notification.trackerId);
    setWorkspace("trackers");
  };

  const triggerExampleUpdate = useCallback(() => {
    const notification = planNotifications.triggerExample(trackerList.trackers);
    if (!notification) return;
    const tracker = trackerList.trackers.find((item) => item.id === notification.trackerId);
    if (tracker) trackerList.update({ ...tracker, dataThrough: notification.publishedDate });
    setToastIds((current) => [notification.id, ...current.filter((id) => id !== notification.id)].slice(0, 3));
  }, [planNotifications.triggerExample, trackerList.trackers, trackerList.update]);

  useDemoNotificationShortcut(trackerList.trackers.length > 0, triggerExampleUpdate);

  return (
    <div className="flex h-dvh flex-col bg-background">
      <SiteHeader
        onOpenMenu={() => setIsSidebarOpen(true)}
        actions={
          <AlertBell
            alerts={alerts.alerts}
            unreadTotal={alerts.unread.total}
            projects={projectList.projects}
            isLoading={alerts.isLoading}
            error={alerts.error}
            onOpen={() => void alerts.loadAlerts()}
            onMarkRead={(alertId) => void alerts.markRead(alertId)}
            onMarkAllRead={() => void alerts.markAllRead(null)}
            onNotRelevant={(alertId) => void alerts.notRelevant(alertId)}
            onAsk={askAboutAlert}
            onDismissError={alerts.dismissError}
            planNotifications={planNotifications.notifications}
            planUnreadTotal={planNotifications.unreadCount}
            onOpenPlanNotification={(notification) => openPlanNotification(notification.id)}
            onMarkPlanRead={planNotifications.markRead}
            onMarkAllPlanRead={planNotifications.markAllRead}
            onDismissPlanNotification={planNotifications.dismiss}
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
          trackerCount={trackerList.trackers.length}
          isTrackersOpen={workspace === "trackers"}
          onOpenTrackers={() => {
            setWorkspace("trackers");
            setTrackerSetup(undefined);
            setSelectedTrackerId(null);
            setIsSidebarOpen(false);
          }}
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
        />

        {workspace === "trackers" ? (
          <TrackersView
            trackers={trackerList.trackers}
            selectedId={selectedTrackerId}
            projects={projectList.projects}
            isCreating={trackerConversationProject !== undefined}
            creationProject={trackerConversationProject}
            creationDraft={trackerDraft}
            onSelect={setSelectedTrackerId}
            onBackToList={() => setSelectedTrackerId(null)}
            onStartCreate={() => setTrackerSetup(null)}
            onCancelCreate={() => setTrackerSetup(undefined)}
            onCompleteCreate={(details, project) => {
              const tracker = trackerList.create(project, details);
              setSelectedTrackerId(tracker.id);
              setTrackerSetup(undefined);
            }}
            onUpdate={trackerList.update}
            onRemove={(trackerId) => {
              trackerList.remove(trackerId);
              setSelectedTrackerId((current) => current === trackerId ? null : current);
            }}
            notifications={planNotifications.notifications}
            onOpenNotification={planNotifications.markRead}
          />
        ) : (
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
              onTrackPlan={chat.messages.length > 0 ? () => {
                setTrackerSetup(activeProject ?? null, draftPlanFromChat(chat.messages, t.trackers.suggestedTopics));
                setWorkspace("trackers");
              } : undefined}
              error={chat.error ?? chatList.error ?? projectList.error}
              onDismissError={() => {
                chat.dismissError();
                chatList.dismissError();
                projectList.dismissError();
              }}
            />
          </div>
        </div>
        )}
      </main>
      {toastIds.length > 0 && <div className="pointer-events-none fixed right-4 top-28 z-[70] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-3">
        {toastIds.map((id) => {
          const notification = planNotifications.notifications.find((item) => item.id === id);
          return notification ? <div key={id} className="pointer-events-auto"><PlanNotificationToast notification={notification}
            onOpen={() => openPlanNotification(id)}
            onClose={() => setToastIds((current) => current.filter((candidate) => candidate !== id))} /></div> : null;
        })}
      </div>}
    </div>
  );
}

export default Playground;
