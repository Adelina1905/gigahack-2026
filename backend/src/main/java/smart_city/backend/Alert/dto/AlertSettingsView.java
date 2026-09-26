package smart_city.backend.Alert.dto;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public record AlertSettingsView(
        UUID projectId,
        boolean enabled,
        boolean prompted,
        // Not removed, oldest first.
        List<AlertTopicView> topics,
        OffsetDateTime lastScanAt
) {
}
