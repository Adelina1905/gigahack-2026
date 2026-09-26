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

import smart_city.backend.Chat.Chat;
import smart_city.backend.Document.StoredDocument;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

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

    @Column(nullable = false, columnDefinition = "text")
    private String text;

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

