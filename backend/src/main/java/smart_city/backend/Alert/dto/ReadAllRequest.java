package smart_city.backend.Alert.dto;

import java.util.UUID;

// Null ids mark the alerts of every project and chat as read.
public record ReadAllRequest(
        UUID projectId,
        UUID chatId
) {
}
