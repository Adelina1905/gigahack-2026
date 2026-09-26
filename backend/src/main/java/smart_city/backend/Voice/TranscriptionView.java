package smart_city.backend.Voice;

public record TranscriptionView(
        String text,
        String language,
        Double durationSeconds
) {
}
