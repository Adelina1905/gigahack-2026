package smart_city.backend.Chat;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "chats")
public class Chat {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "client_id", nullable = false)
    private UUID clientId;

    @Column(name = "request_id")
    private UUID requestId;

    // Plain column: the database clears it (ON DELETE SET NULL) when the project is deleted.
    @Column(name = "project_id")
    private UUID projectId;

    @Column(name = "creation_name")
    private String creationName;

    public String getCreationName() { return creationName; }
    public void setCreationName(String creationName) { this.creationName = creationName; }

    @Column(nullable = false)
    private String name = "New chat";

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt = OffsetDateTime.now();

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt = OffsetDateTime.now();


    // Required by JPA
    public Chat() {
    }


    // Optional constructor for creating a new chat
    public Chat(UUID clientId) {
        this.clientId = clientId;
        this.name = "New chat";
        this.createdAt = OffsetDateTime.now();
        this.updatedAt = this.createdAt;
    }


    // Optional constructor if you want to specify the name
    public Chat(UUID clientId, String name) {
        this.clientId = clientId;
        this.name = name;
        this.createdAt = OffsetDateTime.now();
        this.updatedAt = this.createdAt;
    }


    // Getters

    public UUID getId() {
        return id;
    }

    public UUID getClientId() {
        return clientId;
    }

    public UUID getRequestId() {
        return requestId;
    }

    public void setRequestId(UUID requestId) {
        this.requestId = requestId;
    }

    public UUID getProjectId() {
        return projectId;
    }

    public void setProjectId(UUID projectId) {
        this.projectId = projectId;
    }

    public String getName() {
        return name;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    public OffsetDateTime getUpdatedAt() {
        return updatedAt;
    }


    // Setters

    public void setId(UUID id) {
        this.id = id;
    }

    public void setClientId(UUID clientId) {
        this.clientId = clientId;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public void setUpdatedAt(OffsetDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
