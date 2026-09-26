import { useCallback, useState } from "react";
import { CityGatesArt, TriumphalArchArt } from "../components/brand/Landmarks";
import ChatWindow from "../components/ChatWindow";
import Sidebar from "../components/Sidebar";
import SiteHeader from "../components/SiteHeader";
import { useActiveChatId } from "../hooks/useActiveChatId";
import { useChat } from "../hooks/useChat";
import { useChats } from "../hooks/useChats";
import { useProjects } from "../hooks/useProjects";
import { useI18n } from "../i18n/context";
import { DEFAULT_CHAT_NAME } from "../types/chat";

function Playground() {
  const { t } = useI18n();
  const [activeChatId, navigate] = useActiveChatId();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const chatList = useChats();
  const projectList = useProjects();
  // The project a chat started from the empty screen will be created in.
  const [draftProjectId, setDraftProjectId] = useState<string | null>(null);

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
    void chatList.remove(chatId);
    chat.discard(chatId);
    if (chatId === activeChatId) {
      setDraftProjectId(null);
      navigate(null, { replace: true });
    }
  };

  const activeChat = chatList.chats.find((candidate) => candidate.id === activeChatId);
  const activeName = activeChat?.name;
  const breadcrumbProjectId = activeChatId ? activeChat?.projectId : draftProjectId;
  const breadcrumbProject = projectList.projects.find((project) => project.id === breadcrumbProjectId);

  return (
    <div className="flex h-dvh flex-col bg-background">
      <SiteHeader onOpenMenu={() => setIsSidebarOpen(true)} />

      <main className="flex min-h-0 flex-1">
        <Sidebar
          chats={chatList.chats}
          projects={projectList.projects}
          activeChatId={activeChatId}
          draftProjectId={draftProjectId}
          isLoaded={chatList.isLoaded}
          onNewChat={startNewChat}
          onSelect={selectChat}
          onRename={(chatId, name) => void chatList.rename(chatId, name)}
          onDelete={deleteChat}
          onMoveChat={(chatId, projectId) => void moveChat(chatId, projectId)}
          onCreateProject={createProject}
          onRenameProject={(projectId, name) => void projectList.rename(projectId, name)}
          onDeleteProject={(projectId) => void deleteProject(projectId)}
          onNewChatInProject={startNewChatInProject}
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
              {breadcrumbProject && (
                <>
                  <li className="min-w-0 max-w-[40%] shrink truncate text-primary" title={breadcrumbProject.name}>
                    {breadcrumbProject.name}
                  </li>
                  <li aria-hidden="true" className="text-text-subtle">/</li>
                </>
              )}
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
              error={chat.error ?? chatList.error ?? projectList.error}
              onDismissError={() => {
                chat.dismissError();
                chatList.dismissError();
                projectList.dismissError();
              }}
            />
          </div>
        </div>
      </main>
    </div>
  );
}

export default Playground;
