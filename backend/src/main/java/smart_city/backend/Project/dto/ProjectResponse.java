package smart_city.backend.Project.dto;

import smart_city.backend.Chat.dto.ChatResponse;
import smart_city.backend.Project.Project;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public record ProjectResponse(
        UUID id,
        String name,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        List<ChatResponse> chats
) {

    public static ProjectResponse from(Project project, List<ChatResponse> chats) {

        return new ProjectResponse(
                project.getId(),
                project.getName(),
                project.getCreatedAt(),
                project.getUpdatedAt(),
                chats
        );
    }
}
