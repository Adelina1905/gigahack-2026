import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useI18n } from "../../i18n/context";
import { DEFAULT_CHAT_NAME, type ChatSummary, type ProjectSummary } from "../../types/chat";
import { actionButtonClass, dangerButtonClass, iconProps } from "./iconProps";

interface ChatItemProps {
  chat: ChatSummary;
  isActive: boolean;
  projects: ProjectSummary[];
  onSelect: (chatId: string) => void;
  onRename: (chatId: string, name: string) => void;
  onDelete: (chatId: string) => void;
  onMove: (chatId: string, projectId: string | null) => void;
}

interface MoveMenuProps {
  current: string | null;
  projects: ProjectSummary[];
  onPick: (projectId: string | null) => void;
  onClose: () => void;
}

// The "move to project" choices, shown under the chat row.
function MoveMenu({ current, projects, onPick, onClose }: MoveMenuProps) {
  const { t } = useI18n();
  const menuRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    menuRef.current?.querySelector<HTMLButtonElement>("button")?.focus();

    const handlePointer = (e: PointerEvent) => {
      if (!menuRef.current?.parentElement?.contains(e.target as Node)) onClose();
    };
    document.addEventListener("pointerdown", handlePointer);
    return () => document.removeEventListener("pointerdown", handlePointer);
  }, [onClose]);

  const handleKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
    }
  };

  const options = [
    ...projects.map((project) => ({ id: project.id as string | null, label: project.name })),
    { id: null, label: t.projects.noProject },
  ];

  return (
    <ul
      ref={menuRef}
      role="menu"
      aria-label={t.projects.moveMenu}
      onKeyDown={handleKeyDown}
      className="mx-1 mt-0.5 mb-1 flex flex-col rounded-sm border border-border bg-background py-1 shadow-sm"
    >
      {options.map((option) => {
        const isCurrent = option.id === current;
        return (
          <li key={option.id ?? "none"} role="none">
            <button
              type="button"
              role="menuitemradio"
              aria-checked={isCurrent}
              onClick={() => onPick(option.id)}
              className={`flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-background-secondary ${
                isCurrent ? "font-semibold text-primary-700" : "text-text-muted"
              } ${option.id === null ? "italic" : ""}`}
            >
              <svg {...iconProps} className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
                {option.id === null ? (
                  <path d="M18 6 6 18M6 6l12 12" />
                ) : (
                  <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
                )}
              </svg>
              <span className="truncate">{option.label}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function ChatItem({ chat, isActive, projects, onSelect, onRename, onDelete, onMove }: ChatItemProps) {
  const { t } = useI18n();
  const title = chat.name === DEFAULT_CHAT_NAME ? t.sidebar.newChat : chat.name;
  const [isEditing, setIsEditing] = useState(false);
  const [isMoving, setIsMoving] = useState(false);
  const [draft, setDraft] = useState(chat.name);
  const inputRef = useRef<HTMLInputElement>(null);
  // Escape unmounts the input, which can fire a blur; don't save on that one.
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (isEditing) inputRef.current?.select();
  }, [isEditing]);

  const startEditing = () => {
    setDraft(chat.name);
    cancelledRef.current = false;
    setIsEditing(true);
  };

  const commit = () => {
    if (cancelledRef.current) return;
    setIsEditing(false);
    if (draft.trim() && draft.trim() !== chat.name) onRename(chat.id, draft);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") commit();
    if (e.key === "Escape") {
      cancelledRef.current = true;
      setIsEditing(false);
    }
  };

  const handleDelete = () => {
    if (window.confirm(t.sidebar.confirmRemove(title))) onDelete(chat.id);
  };

  const closeMenu = useCallback(() => setIsMoving(false), []);

  const pickProject = (projectId: string | null) => {
    setIsMoving(false);
    if (projectId !== chat.projectId) onMove(chat.id, projectId);
  };

  if (isEditing) {
    return (
      <li>
        <input
          ref={inputRef}
          value={draft}
          maxLength={255}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={handleKeyDown}
          aria-label={t.sidebar.chatName}
          className="w-full rounded-sm border border-primary bg-background px-3 py-2 text-sm text-text focus:outline-none"
        />
      </li>
    );
  }

  return (
    <li>
      <div className="group relative">
        <button
          type="button"
          onClick={() => onSelect(chat.id)}
          aria-current={isActive ? "page" : undefined}
          title={title}
          // The title gives way to the action buttons only while they show: always on
          // the active chat, on hover or keyboard focus for the others.
          className={`w-full cursor-pointer truncate rounded-r-sm border-l-[3px] py-2 pl-3 text-left text-sm transition-colors ${
            isActive || isMoving
              ? "pr-24"
              : "pr-3 group-focus-within:pr-24 group-hover:pr-24"
          } ${
            isActive
              ? "border-primary bg-primary-50 font-semibold text-primary-700"
              : "border-transparent text-text-muted hover:bg-background-secondary hover:text-text"
          }`}
        >
          {title}
        </button>

        <div
          className={`absolute inset-y-0 right-1 flex items-center gap-0.5 transition-opacity focus-within:opacity-100 group-hover:opacity-100 ${
            isActive || isMoving ? "opacity-100" : "opacity-0"
          }`}
        >
          <button
            type="button"
            onClick={() => setIsMoving((open) => !open)}
            aria-label={t.projects.move(title)}
            aria-haspopup="menu"
            aria-expanded={isMoving}
            className={actionButtonClass}
          >
            <svg {...iconProps} className="h-3.5 w-3.5">
              <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
              <path d="m11 11 2 2-2 2M8 13h5" />
            </svg>
          </button>
          <button
            type="button"
            onClick={startEditing}
            aria-label={t.sidebar.rename(title)}
            className={actionButtonClass}
          >
            <svg {...iconProps} className="h-3.5 w-3.5">
              <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
            </svg>
          </button>
          <button
            type="button"
            onClick={handleDelete}
            aria-label={t.sidebar.remove(title)}
            className={dangerButtonClass}
          >
            <svg {...iconProps} className="h-3.5 w-3.5">
              <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V6" />
            </svg>
          </button>
        </div>
      </div>

      {isMoving && (
        <MoveMenu
          current={chat.projectId}
          projects={projects}
          onPick={pickProject}
          onClose={closeMenu}
        />
      )}
    </li>
  );
}

export default ChatItem;
