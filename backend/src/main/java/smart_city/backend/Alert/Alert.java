package smart_city.backend.Alert;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;

// Rows are inserted by AlertService with ON CONFLICT DO NOTHING; JPA reads and updates them.
@Entity
@Table(name = "alerts")
public class Alert {

    public static final String NOT_RELEVANT = "NOT_RELEVANT";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "client_id", nullable = false)
    private UUID clientId;

    @Column(name = "project_id", nullable = false)
    private UUID projectId;

    // Plain column: the database clears it (ON DELETE SET NULL) when the topic is deleted.
    @Column(name = "topic_id")
    private Long topicId;

    // Snapshot, so the alert keeps its reason after the topic is renamed or deleted.
    @Column(name = "topic_label", nullable = false, length = 80)
    private String topicLabel;

    @Column(name = "document_id", nullable = false, length = 128)
    private String documentId;

    @Column(nullable = false, columnDefinition = "text")
    private String title;

    @Column(columnDefinition = "text")
    private String url;

    @Column(length = 128)
    private String source;

    @Column(length = 128)
    private String district;

    @Column(length = 128)
    private String category;

    @Column(name = "published_date")
    private LocalDate publishedDate;

    @Column(nullable = false, columnDefinition = "text")
    private String excerpt;

    @Column(nullable = false)
    private double score;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt = OffsetDateTime.now();

    @Column(name = "read_at")
    private OffsetDateTime readAt;

    @Column(name = "dismissed_at")
    private OffsetDateTime dismissedAt;

    @Column(length = 16)
    private String feedback;


    // Required by JPA
    protected Alert() {
    }


    public void markRead(OffsetDateTime now) {
        if (readAt == null) {
            readAt = now;
        }
    }

    public void dismiss(String feedback, OffsetDateTime now) {
        this.feedback = feedback;
        this.dismissedAt = now;
        markRead(now);
    }


    // Getters

    public Long getId() {
        return id;
    }

    public UUID getClientId() {
        return clientId;
    }

    public UUID getProjectId() {
        return projectId;
    }

    public Long getTopicId() {
        return topicId;
    }

    public String getTopicLabel() {
        return topicLabel;
    }

    public String getDocumentId() {
        return documentId;
    }

    public String getTitle() {
        return title;
    }

    public String getUrl() {
        return url;
    }

    public String getSource() {
        return source;
    }

    public String getDistrict() {
        return district;
    }

    public String getCategory() {
        return category;
    }

    public LocalDate getPublishedDate() {
        return publishedDate;
    }

    public String getExcerpt() {
        return excerpt;
    }

    public double getScore() {
        return score;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    public OffsetDateTime getReadAt() {
        return readAt;
    }

    public OffsetDateTime getDismissedAt() {
        return dismissedAt;
    }

    public String getFeedback() {
        return feedback;
    }
}
