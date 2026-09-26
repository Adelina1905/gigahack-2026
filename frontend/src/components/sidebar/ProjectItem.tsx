import { useId } from "react";
import { useI18n } from "../../i18n/context";
import type { ChatSummary, ProjectSummary } from "../../types/chat";
import ChatItem from "./ChatItem";
import { actionButtonClass, dangerButtonClass, iconProps } from "./iconProps";

interface ProjectItemProps {
  project: ProjectSummary;
  chats: ChatSummary[];
  projects: ProjectSummary[];
  activeChatId: string | null;
  // The draft chat will be created in this project.
  isDraftTarget: boolean;
  isExpanded: boolean;
  onToggle: (projectId: string) => void;
  onNewChat: (projectId: string) => void;
  onRename: (project: ProjectSummary) => void;
  onDelete: (projectId: string) => void;
  onSelectChat: (chatId: string) => void;
  onRenameChat: (chatId: string, name: string) => void;
  onDeleteChat: (chatId: string) => void;
  onMoveChat: (chatId: string, projectId: string | null) => void;
  unreadAlerts?: number;
  // Opens the project's "Alerts & topics" dialog; the action is hidden without it.
  onOpenAlerts?: (project: ProjectSummary) => void;
}

function ProjectItem({
  project,
  chats,
  projects,
  activeChatId,
  isDraftTarget,
  isExpanded,
  onToggle,
  onNewChat,
  onRename,
  onDelete,
  onSelectChat,
  onRenameChat,
  onDeleteChat,
  onMoveChat,
  unreadAlerts = 0,
  onOpenAlerts,
}: ProjectItemProps) {
  const { t } = useI18n();
  const unreadId = useId();

  const handleDelete = () => {
    if (window.confirm(t.projects.confirmRemove(project.name))) onDelete(project.id);
  };

  return (
    <li data-project-id={project.id}>
      <div className="group relative">
        <button
          type="button"
          onClick={() => onToggle(project.id)}
          aria-expanded={isExpanded}
          aria-describedby={unreadAlerts > 0 ? unreadId : undefined}
          title={project.name}
          className={`flex w-full cursor-pointer items-center gap-2 rounded-sm py-2 pl-2 ${onOpenAlerts ? "pr-[7.25rem]" : "pr-[5.5rem]"} text-left text-sm font-medium transition-colors hover:bg-background-secondary ${
            isDraftTarget ? "text-primary-700" : "text-text"
          }`}
        >
          <svg
            {...iconProps}
            aria-hidden="true"
            className={`h-3 w-3 shrink-0 text-text-subtle transition-transform ${isExpanded ? "rotate-90" : ""}`}
          >
            <path d="m9 6 6 6-6 6" />
          </svg>
          <svg {...iconProps} aria-hidden="true" className="h-4 w-4 shrink-0 text-primary">
            <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
          </svg>
          <span className="truncate">{project.name}</span>
          {unreadAlerts > 0 && (
            <span
              aria-hidden="true"
              data-testid="project-alert-badge"
              className="ml-auto flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-full bg-accent px-1 text-[11px] font-bold leading-none text-primary-900"
            >
              {unreadAlerts > 99 ? "99+" : unreadAlerts}
            </span>
          )}
        </button>
        {unreadAlerts > 0 && (
          <span id={unreadId} className="sr-only">
            {t.alerts.projectUnread(unreadAlerts)}
          </span>
        )}

        <div className="absolute inset-y-0 right-1 flex items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          <button
            type="button"
            onClick={() => onNewChat(project.id)}
            aria-label={t.projects.newChatIn(project.name)}
            className={actionButtonClass}
          >
            <svg {...iconProps} className="h-3.5 w-3.5">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
          {onOpenAlerts && (
            <button
              type="button"
              onClick={() => onOpenAlerts(project)}
              aria-label={t.alerts.settings.open(project.name)}
              title={t.alerts.settings.title}
              className={actionButtonClass}
            >
              <svg {...iconProps} className="h-3.5 w-3.5">
                <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0" />
              </svg>
            </button>
          )}
          <button
            type="button"
            onClick={() => onRename(project)}
            aria-label={t.projects.rename(project.name)}
            className={actionButtonClass}
          >
            <svg {...iconProps} className="h-3.5 w-3.5">
              <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
            </svg>
          </button>
          <button
            type="button"
            onClick={handleDelete}
            aria-label={t.projects.remove(project.name)}
            className={dangerButtonClass}
          >
            <svg {...iconProps} className="h-3.5 w-3.5">
              <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V6" />
            </svg>
          </button>
        </div>
      </div>

      {isExpanded && (
        <ul aria-label={project.name} className="ml-4 flex flex-col gap-0.5 border-l border-border pl-1">
          {/* The chat being written here; the server creates it on the first message. */}
          {isDraftTarget && (
            <li
              aria-current="page"
              className="truncate rounded-r-sm border-l-[3px] border-primary bg-primary-50 py-2 pl-3 pr-3 text-sm font-semibold text-primary-700"
            >
              {t.sidebar.newChat}
            </li>
          )}
          {chats.length === 0 && !isDraftTarget ? (
            <li className="flex flex-col items-start gap-1 px-3 py-1.5">
              <span className="text-xs text-text-subtle">{t.projects.empty}</span>
              <button
                type="button"
                onClick={() => onNewChat(project.id)}
                className="flex cursor-pointer items-center gap-1 rounded-sm py-0.5 text-xs font-semibold text-primary hover:underline"
              >
                <svg {...iconProps} className="h-3.5 w-3.5" aria-hidden="true">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                {t.sidebar.newChat}
              </button>
            </li>
          ) : (
            chats.map((chat) => (
              <ChatItem
                key={chat.id}
                chat={chat}
                isActive={chat.id === activeChatId}
                projects={projects}
                onSelect={onSelectChat}
                onRename={onRenameChat}
                onDelete={onDeleteChat}
                onMove={onMoveChat}
              />
            ))
          )}
        </ul>
      )}
    </li>
  );
}

export default ProjectItem;
