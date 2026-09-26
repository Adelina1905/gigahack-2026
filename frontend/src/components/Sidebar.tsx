import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { ChatSummary } from "../types/chat";

interface SidebarProps {
  chats: ChatSummary[];
  activeChatId: string | null;
  isLoaded: boolean;
  onNewChat: () => void;
  onSelect: (chatId: string) => void;
  onRename: (chatId: string, name: string) => void;
  onDelete: (chatId: string) => void;
  // Mobile drawer state; on md+ the sidebar is always visible.
  isOpen: boolean;
  onClose: () => void;
}

const DAY_MS = 24 * 60 * 60 * 1000;

const GROUPS = ["Today", "Yesterday", "Previous 7 days", "Previous 30 days", "Older"] as const;

function groupOf(updatedAt: number, startOfToday: number): (typeof GROUPS)[number] {
  if (updatedAt >= startOfToday) return "Today";
  if (updatedAt >= startOfToday - DAY_MS) return "Yesterday";
  if (updatedAt >= startOfToday - 7 * DAY_MS) return "Previous 7 days";
  if (updatedAt >= startOfToday - 30 * DAY_MS) return "Previous 30 days";
  return "Older";
}

function groupChats(chats: ChatSummary[]) {
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const groups = new Map<string, ChatSummary[]>();

  for (const chat of chats) {
    const label = groupOf(chat.updatedAt, startOfToday);
    groups.set(label, [...(groups.get(label) ?? []), chat]);
  }

  return GROUPS.filter((label) => groups.has(label)).map((label) => ({
    label,
    chats: groups.get(label)!,
  }));
}

const iconProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

interface ChatItemProps {
  chat: ChatSummary;
  isActive: boolean;
  onSelect: (chatId: string) => void;
  onRename: (chatId: string, name: string) => void;
  onDelete: (chatId: string) => void;
}

function ChatItem({ chat, isActive, onSelect, onRename, onDelete }: ChatItemProps) {
  const [isEditing, setIsEditing] = useState(false);
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
    if (window.confirm(`Delete "${chat.name}"? This can't be undone.`)) onDelete(chat.id);
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
          aria-label="Chat name"
          className="w-full rounded-lg border border-border-strong bg-background px-3 py-2 text-sm text-text focus:outline-none"
        />
      </li>
    );
  }

  return (
    <li className="group relative">
      <button
        type="button"
        onClick={() => onSelect(chat.id)}
        aria-current={isActive ? "page" : undefined}
        title={chat.name}
        className={`w-full cursor-pointer truncate rounded-lg py-2 pl-3 pr-16 text-left text-sm transition-colors ${
          isActive
            ? "bg-background font-medium text-text shadow-sm"
            : "text-text-muted hover:bg-background hover:text-text"
        }`}
      >
        {chat.name}
      </button>

      <div
        className={`absolute inset-y-0 right-1 flex items-center gap-0.5 transition-opacity focus-within:opacity-100 group-hover:opacity-100 ${
          isActive ? "opacity-100" : "opacity-0"
        }`}
      >
        <button
          type="button"
          onClick={startEditing}
          aria-label={`Rename "${chat.name}"`}
          className="rounded-md cursor-pointer p-1.5 text-text-subtle hover:bg-background-secondary hover:text-text"
        >
          <svg {...iconProps} className="h-3.5 w-3.5">
            <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
        </button>
        <button
          type="button"
          onClick={handleDelete}
          aria-label={`Delete "${chat.name}"`}
          className="rounded-md cursor-pointer p-1.5 text-text-subtle hover:bg-danger-light hover:text-danger"
        >
          <svg {...iconProps} className="h-3.5 w-3.5">
            <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V6" />
          </svg>
        </button>
      </div>
    </li>
  );
}

function Sidebar({
  chats,
  activeChatId,
  isLoaded,
  onNewChat,
  onSelect,
  onRename,
  onDelete,
  isOpen,
  onClose,
}: SidebarProps) {
  const groups = groupChats(chats);

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
        aria-label="Chat history"
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-border bg-background-secondary transition-transform md:static md:w-64 md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center gap-2 p-3">
          <button
            type="button"
            onClick={onNewChat}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-text-inverted transition-colors hover:bg-primary-dark"
          >
            <svg {...iconProps} className="h-4 w-4">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New chat
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close sidebar"
            className="rounded-lg p-2 text-text-muted hover:bg-background md:hidden"
          >
            <svg {...iconProps} className="h-4 w-4">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 pb-4">
          {groups.length === 0 ? (
            <p className="px-3 py-2 text-sm text-text-subtle">
              {isLoaded ? "No chats yet." : "Loading chats…"}
            </p>
          ) : (
            groups.map((group) => (
              <section key={group.label} className="mt-3 first:mt-0">
                <h2 className="px-3 pb-1 font-inter text-xs font-semibold uppercase tracking-wide text-text-subtle">
                  {group.label}
                </h2>
                <ul className="flex flex-col gap-0.5">
                  {group.chats.map((chat) => (
                    <ChatItem
                      key={chat.id}
                      chat={chat}
                      isActive={chat.id === activeChatId}
                      onSelect={onSelect}
                      onRename={onRename}
                      onDelete={onDelete}
                    />
                  ))}
                </ul>
              </section>
            ))
          )}
        </nav>
      </aside>
    </>
  );
}

export default Sidebar;
