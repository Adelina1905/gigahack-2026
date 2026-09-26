package smart_city.backend.Document.dto;

import smart_city.backend.Document.StoredDocument;

import java.time.OffsetDateTime;

public record DocumentView(
        Long id,
        String title,
        String documentLink,
        OffsetDateTime addedAt
) {

    public static DocumentView from(StoredDocument document) {
        return new DocumentView(
                document.getId(),
                document.getTitle(),
                document.getDocumentLink(),
                document.getAddedAt()
        );
    }
}

