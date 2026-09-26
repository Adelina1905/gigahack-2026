package smart_city.backend.Alert.dto;

// One topic extracted by the Python service (POST /v1/alerts/topics).
public record TopicSuggestion(
        String label,
        String query
) {
}
