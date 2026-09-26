package smart_city.backend.Llm;

import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.Llm.dto.LlmTurn;

import java.util.List;
import java.util.UUID;

public interface LlmGateway {

    /**
     * Sends one user message plus the prior conversation to the LLM service.
     *
     * @throws smart_city.backend.Llm.exceptions.LlmUnavailableException
     *         when the service is unreachable or does not answer properly
     */
    LlmReply chat(UUID chatId, String message, List<LlmTurn> history);
}
