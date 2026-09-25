import ChatWindow from "../components/ChatWindow";
import { useMockChat } from "../hooks/useMockChat";

function Playground() {
  const { messages, isTyping, send, retry, regenerate } = useMockChat();

  return (
    <main className="h-screen bg-background">
      <div className="mx-auto h-full max-w-3xl">
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
          onSend={send}
          onRetry={retry}
          onRegenerate={regenerate}
        />
      </div>
    </main>
  );
}

export default Playground;
