package smart_city.backend.Alert.dto;

import java.util.Map;
import java.util.UUID;

public record UnreadCountView(
        long total,
        Map<UUID, Long> byProject
) {
}
