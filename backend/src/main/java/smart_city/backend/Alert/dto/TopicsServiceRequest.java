package smart_city.backend.Alert.dto;

import java.util.List;

public record TopicsServiceRequest(
        List<String> questions,
        List<String> existingLabels
) {
}
