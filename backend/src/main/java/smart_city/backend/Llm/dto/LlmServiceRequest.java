package smart_city.backend.Llm.dto;

import java.util.List;
import java.util.UUID;

public record LlmServiceRequest(
        UUID chatId,
        String message,
        List<LlmTurn> history
) {
}
