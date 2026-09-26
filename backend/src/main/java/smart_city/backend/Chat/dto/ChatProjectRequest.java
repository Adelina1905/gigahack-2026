package smart_city.backend.Chat.dto;

import java.util.UUID;

// A null projectId takes the chat out of its project.
public record ChatProjectRequest(
        UUID projectId
) {
}
