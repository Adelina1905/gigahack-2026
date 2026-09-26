package smart_city.backend.Alert.dto;

import java.time.LocalDate;

// One matched feed document, attributed to its best topic.
public record AlertMatch(
        String topicId,
        String documentId,
        String title,
        String url,
        String source,
        String district,
        String category,
        LocalDate publishedDate,
        String excerpt,
        double score
) {
}
