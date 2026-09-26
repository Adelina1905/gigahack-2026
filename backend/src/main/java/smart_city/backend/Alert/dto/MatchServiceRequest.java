package smart_city.backend.Alert.dto;

import java.util.List;

public record MatchServiceRequest(
        List<MatchTopic> topics,
        List<String> excludedDocumentIds,
        int limit
) {
}
