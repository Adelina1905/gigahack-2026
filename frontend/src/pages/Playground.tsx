import ChatWindow from "../components/ChatWindow";
import { useChat } from "../hooks/useChat";
import { useMockChat } from "../hooks/useMockChat";

// Set VITE_USE_MOCK=true to work on the UI without the backend running.
// Chosen once at module load, so the hook call order never changes.
const useChatSource: () => ReturnType<typeof useChat> =
  import.meta.env.VITE_USE_MOCK === "true"
    ? () => ({ ...useMockChat(), error: null, dismissError: () => {} })
    : useChat;

function Playground() {
  const { messages, isTyping, error, send, retry, regenerate, dismissError } =
    useChatSource();

  return (
    <main className="h-screen bg-background">
      <div className="mx-auto h-full max-w-2xl">
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
          onSend={send}
          onRetry={retry}
          onRegenerate={regenerate}
          error={error}
          onDismissError={dismissError}
        />
      </div>
    </main>
  );
}

export default Playground;
