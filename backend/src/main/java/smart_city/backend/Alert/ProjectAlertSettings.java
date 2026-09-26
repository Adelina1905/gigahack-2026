package smart_city.backend.Alert;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "project_alert_settings")
public class ProjectAlertSettings {

    // Plain column: the database removes the row (ON DELETE CASCADE) with the project.
    @Id
    @Column(name = "project_id")
    private UUID projectId;

    @Column(nullable = false)
    private boolean enabled;

    // True once the user answered the one-time "turn on alerts?" popup.
    @Column(nullable = false)
    private boolean prompted;

    @Column(name = "topics_refreshed_at")
    private OffsetDateTime topicsRefreshedAt;

    @Column(name = "last_scan_at")
    private OffsetDateTime lastScanAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt = OffsetDateTime.now();


    // Required by JPA
    protected ProjectAlertSettings() {
    }


    public ProjectAlertSettings(UUID projectId) {
        this.projectId = projectId;
        this.updatedAt = OffsetDateTime.now();
    }


    public void touch() {
        this.updatedAt = OffsetDateTime.now();
    }


    // Getters

    public UUID getProjectId() {
        return projectId;
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
