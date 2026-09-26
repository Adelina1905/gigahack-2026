package smart_city.backend.Alert.dto;

import java.util.UUID;

// Query projection: unread, not dismissed alerts of one project or one chat (exactly one id is set).
public record ScopeUnreadCount(
        UUID projectId,
        UUID chatId,
        long count
) {
}
