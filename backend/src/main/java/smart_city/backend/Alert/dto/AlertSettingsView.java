package smart_city.backend.Alert.dto;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

// Exactly one of projectId and chatId is set.
public record AlertSettingsView(
        UUID projectId,
        UUID chatId,
        boolean enabled,
        boolean prompted,
        // Not removed, oldest first.
        List<AlertTopicView> topics,
        OffsetDateTime lastScanAt
) {
}
