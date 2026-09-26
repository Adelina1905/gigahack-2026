import { useState } from "react";
import { useI18n } from "../i18n/context";
import type { ChatGroup } from "../i18n/messages";
import type { ChatSummary, ProjectSummary } from "../types/chat";
import { CathedralArt } from "./brand/Landmarks";
import TitleRule from "./brand/TitleRule";
import ProjectDialog from "./ProjectDialog";
import ChatItem from "./sidebar/ChatItem";
import ProjectItem from "./sidebar/ProjectItem";
import { iconProps } from "./sidebar/iconProps";

interface SidebarProps {
  chats: ChatSummary[];
  projects: ProjectSummary[];
  activeChatId: string | null;
  // The project the open draft chat will be created in, if any.
  draftProjectId: string | null;
  isLoaded: boolean;
  onNewChat: () => void;
  onSelect: (chatId: string) => void;
  onRename: (chatId: string, name: string) => void;
  onDelete: (chatId: string) => void;
  onMoveChat: (chatId: string, projectId: string | null) => void;
  onCreateProject: (name: string) => Promise<ProjectSummary | null>;
  onRenameProject: (projectId: string, name: string) => void;
  onDeleteProject: (projectId: string) => void;
  onNewChatInProject: (projectId: string) => void;
  // Mobile drawer state; on md+ the sidebar is always visible.
  isOpen: boolean;
  onClose: () => void;
}

const DAY_MS = 24 * 60 * 60 * 1000;

const GROUPS: ChatGroup[] = ["today", "yesterday", "week", "month", "older"];

function groupOf(updatedAt: number, startOfToday: number): ChatGroup {
  if (updatedAt >= startOfToday) return "today";
  if (updatedAt >= startOfToday - DAY_MS) return "yesterday";
  if (updatedAt >= startOfToday - 7 * DAY_MS) return "week";
  if (updatedAt >= startOfToday - 30 * DAY_MS) return "month";
  return "older";
}

function groupChats(chats: ChatSummary[]) {
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const groups = new Map<ChatGroup, ChatSummary[]>();

  for (const chat of chats) {
    const label = groupOf(chat.updatedAt, startOfToday);
    groups.set(label, [...(groups.get(label) ?? []), chat]);
  }

  return GROUPS.filter((label) => groups.has(label)).map((label) => ({
    label,
    chats: groups.get(label)!,
  }));
}

// A chat whose project isn't known (not loaded yet, or gone) stays ungrouped.
function splitByProject(chats: ChatSummary[], projects: ProjectSummary[]) {
  const known = new Set(projects.map((project) => project.id));
  const byProject = new Map<string, ChatSummary[]>();
  const ungrouped: ChatSummary[] = [];

  for (const chat of chats) {
    if (chat.projectId && known.has(chat.projectId)) {
      byProject.set(chat.projectId, [...(byProject.get(chat.projectId) ?? []), chat]);
    } else {
      ungrouped.push(chat);
    }
  }
  return { byProject, ungrouped };
}

type DialogState = { mode: "create" } | { mode: "rename"; project: ProjectSummary } | null;

function Sidebar({
  chats,
  projects,
  activeChatId,
  draftProjectId,
  isLoaded,
  onNewChat,
  onSelect,
  onRename,
  onDelete,
  onMoveChat,
  onCreateProject,
  onRenameProject,
  onDeleteProject,
  onNewChatInProject,
  isOpen,
  onClose,
}: SidebarProps) {
  const { t } = useI18n();
  const { byProject, ungrouped } = splitByProject(chats, projects);
  const groups = groupChats(ungrouped);
  const [dialog, setDialog] = useState<DialogState>(null);

  // The project holding the open chat (or the draft) is always shown expanded
  // when it changes; otherwise projects open and close on click.
  const currentProjectId = activeChatId
    ? (chats.find((chat) => chat.id === activeChatId)?.projectId ?? null)
    : draftProjectId;
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(
    () => new Set(currentProjectId ? [currentProjectId] : []),
  );
  const [seenProjectId, setSeenProjectId] = useState(currentProjectId);
  if (currentProjectId !== seenProjectId) {
    setSeenProjectId(currentProjectId);
    if (currentProjectId && !expanded.has(currentProjectId)) {
      setExpanded(new Set([...expanded, currentProjectId]));
    }
  }

  const toggle = (projectId: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (!next.delete(projectId)) next.add(projectId);
      return next;
    });

  const closeDialog = () => setDialog(null);

  const submitDialog = (name: string) => {
    const current = dialog;
    setDialog(null);
    if (current?.mode === "rename") {
      onRenameProject(current.project.id, name);
      return;
    }
    void onCreateProject(name).then((project) => {
      if (project) setExpanded((open) => new Set([...open, project.id]));
    });
  };

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/30 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        aria-label={t.sidebar.label}
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col overflow-hidden border-r border-border bg-background transition-transform md:relative md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Sits behind the list, like the landmark art in the margins of chisinau.md. */}
        <CathedralArt
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-4 bottom-0 text-primary opacity-[0.1]"
        />

        <div className="relative flex items-start justify-between gap-2 px-5 pt-5">
          <div>
            <h2 className="text-[1.625rem] font-light leading-tight text-primary">{t.sidebar.title}</h2>
            <TitleRule className="mt-2.5" />
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.sidebar.close}
            className="rounded-sm p-2 text-text-muted hover:bg-background-secondary md:hidden"
          >
            <svg {...iconProps} className="h-4 w-4">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="relative px-4 pt-5 pb-2">
          <button
            type="button"
            onClick={onNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-sm bg-primary px-3 py-2.5 text-sm font-semibold text-text-inverted transition-colors hover:bg-primary-dark"
          >
            <svg {...iconProps} className="h-4 w-4">
              <path d="M12 5v14M5 12h14" />
            </svg>
            {t.sidebar.newChat}
          </button>
        </div>

        <nav className="relative flex-1 overflow-y-auto px-4 pb-4">
          <section aria-labelledby="sidebar-projects-title" className="mt-2">
            <div className="flex items-center justify-between gap-2 pb-1.5">
              <h3 id="sidebar-projects-title">
                <span className="inline-block rounded-sm border border-border-strong bg-background px-1.5 py-px text-[11px] font-medium text-text-muted">
                  {t.projects.title}
                </span>
              </h3>
              <button
                type="button"
                onClick={() => setDialog({ mode: "create" })}
                className="flex cursor-pointer items-center gap-1 rounded-sm px-1.5 py-1 text-xs font-semibold text-primary hover:bg-primary-50"
              >
                <svg {...iconProps} className="h-3.5 w-3.5" aria-hidden="true">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                {t.projects.newProject}
              </button>
            </div>

            {projects.length > 0 && (
              <ul className="flex flex-col gap-0.5">
                {projects.map((project) => (
                  <ProjectItem
                    key={project.id}
                    project={project}
                    chats={byProject.get(project.id) ?? []}
                    projects={projects}
                    activeChatId={activeChatId}
                    isDraftTarget={!activeChatId && draftProjectId === project.id}
                    isExpanded={expanded.has(project.id)}
                    onToggle={toggle}
                    onNewChat={(projectId) => {
                      setExpanded((open) => new Set([...open, projectId]));
                      onNewChatInProject(projectId);
                    }}
                    onRename={(target) => setDialog({ mode: "rename", project: target })}
                    onDelete={onDeleteProject}
                    onSelectChat={onSelect}
                    onRenameChat={onRename}
                    onDeleteChat={onDelete}
                    onMoveChat={onMoveChat}
                  />
                ))}
              </ul>
            )}
          </section>

          {chats.length === 0 ? (
            <p className="mt-4 px-1 py-2 text-sm text-text-subtle">
              {isLoaded ? t.sidebar.empty : t.sidebar.loading}
            </p>
          ) : (
            groups.map((group) => (
              <section key={group.label} className="mt-4">
                {/* Outlined like the date stamps on chisinau.md news cards. */}
                <h3 className="pb-1.5">
                  <span className="inline-block rounded-sm border border-border-strong bg-background px-1.5 py-px text-[11px] font-medium text-text-muted">
                    {t.sidebar.groups[group.label]}
                  </span>
                </h3>
                <ul className="flex flex-col gap-0.5">
                  {group.chats.map((chat) => (
                    <ChatItem
                      key={chat.id}
                      chat={chat}
                      isActive={chat.id === activeChatId}
                      projects={projects}
                      onSelect={onSelect}
                      onRename={onRename}
                      onDelete={onDelete}
                      onMove={onMoveChat}
                    />
                  ))}
                </ul>
              </section>
            ))
          )}
        </nav>
      </aside>

      {dialog && (
        <ProjectDialog
          title={dialog.mode === "rename" ? t.projects.renameTitle : t.projects.newProject}
          submitLabel={dialog.mode === "rename" ? t.projects.save : t.projects.create}
          initialName={dialog.mode === "rename" ? dialog.project.name : ""}
          onSubmit={submitDialog}
          onCancel={closeDialog}
        />
      )}
    </>
  );
}

export default Sidebar;
