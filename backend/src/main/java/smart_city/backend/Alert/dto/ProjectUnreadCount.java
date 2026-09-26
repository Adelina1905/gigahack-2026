package smart_city.backend.Alert.dto;

import java.util.UUID;

// Query projection: unread, not dismissed alerts of one project.
public record ProjectUnreadCount(
        UUID projectId,
        long count
) {
}
