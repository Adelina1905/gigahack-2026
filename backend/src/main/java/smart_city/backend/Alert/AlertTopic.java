package smart_city.backend.Alert;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "alert_topics")
public class AlertTopic {

    public static final int MAX_LABEL = 80;
    public static final int MAX_QUERY = 300;

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "project_id", nullable = false)
    private UUID projectId;

    @Column(nullable = false, length = MAX_LABEL)
    private String label;

    @Column(nullable = false, length = MAX_QUERY)
    private String query;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 8)
    private AlertTopicSource source;

    // Removed AUTO topics are kept so a refresh never re-creates their label.
    @Column(nullable = false)
    private boolean removed;

    // Null: the matcher's default threshold.
    @Column(name = "min_score")
    private Double minScore;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt = OffsetDateTime.now();


    // Required by JPA
    protected AlertTopic() {
    }


    public AlertTopic(UUID projectId, String label, String query, AlertTopicSource source) {
        this.projectId = projectId;
        this.label = label;
        this.query = query;
        this.source = source;
        this.createdAt = OffsetDateTime.now();
    }


    // "Not relevant" feedback: only matches scoring above the dismissed one pass from now on.
    public void raiseMinScore(double score) {
        double current = minScore == null ? 0 : minScore;
        minScore = Math.max(current, score + 0.01);
    }


    // Getters

    public Long getId() {
        return id;
    }

    public UUID getProjectId() {
        return projectId;
    }

    public String getLabel() {
        return label;
    }

    public String getQuery() {
        return query;
    }

    public AlertTopicSource getSource() {
        return source;
    }

    public boolean isRemoved() {
        return removed;
    }

    public Double getMinScore() {
        return minScore;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }


    // Setters

    public void setLabel(String label) {
        this.label = label;
    }

    public void setQuery(String query) {
        this.query = query;
    }

    public void setSource(AlertTopicSource source) {
        this.source = source;
    }

    public void setRemoved(boolean removed) {
        this.removed = removed;
    }

    public void setMinScore(Double minScore) {
        this.minScore = minScore;
    }
}
