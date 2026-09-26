package smart_city.backend.Llm.dto;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public record LlmMessageView(
        UUID chatId,
        String text,
        String mode,
        String status,
        List<LlmSourceView> sources,
        OffsetDateTime createdAt
) {
}
