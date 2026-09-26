package smart_city.backend.Document;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.OffsetDateTime;

@Entity
@Table(name = "documents")
public class StoredDocument {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 255)
    private String title;

    @Column(name = "document_link", nullable = false, columnDefinition = "text")
    private String documentLink;

    @Column(name = "added_at", nullable = false)
    private OffsetDateTime addedAt = OffsetDateTime.now();

    protected StoredDocument() {
    }

    public StoredDocument(String title, String documentLink) {
        this.title = title;
        this.documentLink = documentLink;
        this.addedAt = OffsetDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getDocumentLink() {
        return documentLink;
    }

    public OffsetDateTime getAddedAt() {
        return addedAt;
    }
}

