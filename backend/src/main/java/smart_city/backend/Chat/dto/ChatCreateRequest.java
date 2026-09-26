package smart_city.backend.Chat.dto;

import jakarta.validation.constraints.Size;
import java.util.UUID;

public record ChatCreateRequest(

        @Size(max = 255)
        String name,
        UUID requestId

) {
    public ChatCreateRequest(String name) {
        this(name, null);
    }
}
