package smart_city.backend.Alert.dto;

import smart_city.backend.Alert.Alert;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;

public record AlertView(
        Long id,
        UUID projectId,
        Long topicId,
        String topicLabel,
        String documentId,
        String title,
        String url,
        String source,
        String district,
        String category,
        LocalDate publishedDate,
        String excerpt,
        double score,
        OffsetDateTime createdAt,
        OffsetDateTime readAt
) {

    public static AlertView from(Alert alert) {

        return new AlertView(
                alert.getId(),
                alert.getProjectId(),
                alert.getTopicId(),
                alert.getTopicLabel(),
                alert.getDocumentId(),
                alert.getTitle(),
                alert.getUrl(),
                alert.getSource(),
                alert.getDistrict(),
                alert.getCategory(),
                alert.getPublishedDate(),
                alert.getExcerpt(),
                alert.getScore(),
                alert.getCreatedAt(),
                alert.getReadAt()
        );
    }
}
