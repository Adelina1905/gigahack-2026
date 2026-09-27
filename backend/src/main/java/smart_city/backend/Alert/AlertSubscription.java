package smart_city.backend.Alert;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.OffsetDateTime;
import java.util.UUID;

// Alert settings of one project or one chat. Rows are created by AlertService with ON CONFLICT DO NOTHING.
@Entity
@Table(name = "alert_subscriptions")
public class AlertSubscription {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "client_id", nullable = false)
    private UUID clientId;

    // Plain columns: the database removes the row (ON DELETE CASCADE) with its project or chat.
    @Column(name = "project_id")
    private UUID projectId;

    @Column(name = "chat_id")
    private UUID chatId;

    @Column(nullable = false)
    private boolean enabled;

    // True once the user answered the one-time "get notified?" prompt.
    @Column(nullable = false)
    private boolean prompted;

    @Column(name = "topics_refreshed_at")
    private OffsetDateTime topicsRefreshedAt;

    @Column(name = "last_scan_at")
    private OffsetDateTime lastScanAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt = OffsetDateTime.now();


    // Required by JPA
    protected AlertSubscription() {
    }


    public AlertScope scope() {
        return new AlertScope(projectId, chatId);
    }

    public void touch() {
        this.updatedAt = OffsetDateTime.now();
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

    public UUID getChatId() {
        return chatId;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public boolean isPrompted() {
        return prompted;
    }

    public OffsetDateTime getTopicsRefreshedAt() {
        return topicsRefreshedAt;
    }

    public OffsetDateTime getLastScanAt() {
        return lastScanAt;
    }

    public OffsetDateTime getUpdatedAt() {
        return updatedAt;
    }


    // Setters

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void setPrompted(boolean prompted) {
        this.prompted = prompted;
    }

    public void setTopicsRefreshedAt(OffsetDateTime topicsRefreshedAt) {
        this.topicsRefreshedAt = topicsRefreshedAt;
    }

    public void setLastScanAt(OffsetDateTime lastScanAt) {
        this.lastScanAt = lastScanAt;
    }
}
