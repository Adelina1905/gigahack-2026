package smart_city.backend.Alert.dto;

// A topic sent to POST /v1/alerts/match; a null minScore uses the matcher's default threshold.
public record MatchTopic(
        String id,
        String query,
        Double minScore
) {
}
