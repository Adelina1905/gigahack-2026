package smart_city.backend.Alert.dto;

import java.util.UUID;

// A null projectId marks the alerts of every project as read.
public record ReadAllRequest(
        UUID projectId
) {
}
