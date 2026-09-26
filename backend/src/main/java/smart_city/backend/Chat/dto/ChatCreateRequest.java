package smart_city.backend.Chat.dto;

import jakarta.validation.constraints.Size;
import java.util.UUID;

public record ChatCreateRequest(

        @Size(max = 255)
        String name,
        UUID requestId,
        UUID projectId

) {
    public ChatCreateRequest(String name) {
        this(name, null, null);
    }

    public ChatCreateRequest(String name, UUID requestId) {
        this(name, requestId, null);
    }
}
