import ChatWindow from "../components/ChatWindow";
import { useChat } from "../hooks/useChat";

function Playground() {
  const { messages, isTyping, send, retry } = useChat();

  return (
    <main className="h-screen bg-background">
      <div className="mx-auto h-full max-w-2xl">
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
          onSend={send}
          onRetry={retry}
        />
      </div>
    </main>
  );
}

export default Playground;
