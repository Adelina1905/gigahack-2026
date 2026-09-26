package smart_city.backend.Chat.dto;

import smart_city.backend.Chat.Chat;

import java.time.OffsetDateTime;
import java.util.UUID;

public record ChatResponse(
        UUID id,
        String name,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt
) {

    public static ChatResponse from(Chat chat) {

        return new ChatResponse(
                chat.getId(),
                chat.getName(),
                chat.getCreatedAt(),
                chat.getUpdatedAt()
        );
    }
}