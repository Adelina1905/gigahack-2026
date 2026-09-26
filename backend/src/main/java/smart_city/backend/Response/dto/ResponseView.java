package smart_city.backend.Response.dto;

import smart_city.backend.Response.ChatResponseMessage;

import java.time.OffsetDateTime;
import java.util.UUID;

public record ResponseView(
        Long id,
        UUID chatId,
        String prompt,
        String text,
        OffsetDateTime createdAt
) {

    public static ResponseView from(ChatResponseMessage response) {
        return new ResponseView(
                response.getId(),
                response.getChat().getId(),
                response.getPrompt(),
                response.getText(),
                response.getCreatedAt()
        );
    }
}

