package smart_city.backend.Response;

import org.springframework.stereotype.Service;

import smart_city.backend.Llm.LlmGateway;

import java.util.List;
import java.util.UUID;

@Service
public class AiResponseProvider {

    private final LlmGateway llmGateway;

    public AiResponseProvider(LlmGateway llmGateway) {
        this.llmGateway = llmGateway;
    }

    public String generateResponse(String userInput) {
        // Stored chats keep no LLM-side history, so each call is a fresh turn.
        return llmGateway
                .chat(UUID.randomUUID(), userInput, List.of())
                .answer();
    }
}
