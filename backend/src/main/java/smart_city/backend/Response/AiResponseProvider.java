package smart_city.backend.Response;

import org.springframework.stereotype.Service;

import smart_city.backend.Llm.LlmGateway;
import smart_city.backend.Llm.LlmProperties;
import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.Llm.dto.LlmTurn;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Service
public class AiResponseProvider {

    private final LlmGateway llmGateway;
    private final int maxHistory;

    public AiResponseProvider(
            LlmGateway llmGateway,
            LlmProperties properties
    ) {
        this.llmGateway = llmGateway;
        this.maxHistory = properties.maxHistory();
    }

    public LlmReply generateResponse(
            UUID chatId,
            String userInput,
            List<LlmTurn> history
    ) {
        return llmGateway.chat(chatId, userInput, history);
    }

    // Turns the stored responses before a prompt (oldest first) into the
    // conversation the LLM sees, keeping only the most recent turns.
    public List<LlmTurn> historyFrom(List<ChatResponseMessage> earlier) {
        List<LlmTurn> history = new ArrayList<>();

        for (ChatResponseMessage response : earlier) {
            // Rows stored before prompts were kept can't form a full turn.
            if (response.getPrompt() == null || response.getPrompt().isBlank()) {
                continue;
            }
            history.add(LlmTurn.user(response.getPrompt()));
            history.add(LlmTurn.assistant(response.getText()));
        }

        int from = Math.max(0, history.size() - maxHistory);
        // Never start the window on an assistant message.
        if (from < history.size() && "assistant".equals(history.get(from).role())) {
            from++;
        }
        return List.copyOf(history.subList(from, history.size()));
    }
}
