package smart_city.backend.Response;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import smart_city.backend.Llm.dto.LlmReply;

import smart_city.backend.Chat.Chat;
import smart_city.backend.Document.StoredDocument;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "responses")
public class ChatResponseMessage {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "chat_id", nullable = false)
    private Chat chat;

    @Column(columnDefinition = "text")
    private String prompt;

    @Column(columnDefinition = "text")
    private String text;

    @Column(name = "request_id", nullable = false)
    private UUID requestId = UUID.randomUUID();

    @Enumerated(EnumType.STRING)
    @Column(name = "generation_status", nullable = false)
    private GenerationStatus generationStatus = GenerationStatus.COMPLETED;

    @Column(name = "generation_version", nullable = false)
    private int generationVersion;

    @Column(name = "generation_request_id")
    private UUID generationRequestId;

    @Column(name = "generation_started_at")
    private OffsetDateTime generationStartedAt;

    @Column(name = "generation_expires_at")
    private OffsetDateTime generationExpiresAt;

    @Column(name = "error_code")
    private String errorCode;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "ai_reply", columnDefinition = "jsonb")
    private LlmReply aiReply;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt = OffsetDateTime.now();

    // The documents the answer cites.
    @ManyToMany
    @JoinTable(
            name = "response_documents",
            joinColumns = @JoinColumn(name = "response_id"),
            inverseJoinColumns = @JoinColumn(name = "document_id")
    )
    @OrderBy("id")
    private List<StoredDocument> documents = new ArrayList<>();

    protected ChatResponseMessage() {
    }

    public ChatResponseMessage(Chat chat, String prompt, String text) {
        this.chat = chat;
        this.prompt = prompt;
        this.text = text;
        this.createdAt = OffsetDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public Chat getChat() {
        return chat;
    }

    public String getPrompt() {
        return prompt;
    }

    public String getText() {
        return text;
    }

    public void setText(String text) {
        this.text = text;
    }

    public UUID getRequestId() { return requestId; }
    public void setRequestId(UUID requestId) { this.requestId = requestId; }
    public GenerationStatus getGenerationStatus() { return generationStatus; }
    public int getGenerationVersion() { return generationVersion; }
    public UUID getGenerationRequestId() { return generationRequestId; }
    public OffsetDateTime getGenerationExpiresAt() { return generationExpiresAt; }
    public String getErrorCode() { return errorCode; }
    public LlmReply getAiReply() { return aiReply; }

    public void beginGeneration(UUID operationId, OffsetDateTime now) {
        generationRequestId = operationId;
        generationVersion++;
        generationStatus = GenerationStatus.PENDING;
        generationStartedAt = now;
        generationExpiresAt = now.plusMinutes(5);
        errorCode = null;
    }

    public boolean isCurrentAttempt(UUID operationId, int version) {
        return generationStatus == GenerationStatus.PENDING
                && generationVersion == version
                && operationId.equals(generationRequestId);
    }

    public void completeGeneration(LlmReply reply, List<StoredDocument> documents) {
        text = reply.displayText();
        aiReply = reply;
        setDocuments(documents);
        generationStatus = GenerationStatus.COMPLETED;
        generationExpiresAt = null;
        errorCode = null;
    }

    public void failGeneration(String code) {
        generationStatus = GenerationStatus.FAILED;
        generationExpiresAt = null;
        errorCode = code;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    public List<StoredDocument> getDocuments() {
        return documents;
    }

    public void setDocuments(List<StoredDocument> documents) {
        this.documents.clear();
        this.documents.addAll(documents);
    }
}

