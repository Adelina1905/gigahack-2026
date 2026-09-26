package smart_city.backend.Alert.dto;

public record ScanResult(
        int created,
        // "embedding" or "lexical" from the Python matcher, "none" when there was nothing to match.
        String matcher
) {
}
