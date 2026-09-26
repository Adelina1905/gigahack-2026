package smart_city.backend.Document;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface DocumentRepository
        extends JpaRepository<StoredDocument, Long> {

    List<StoredDocument> findAllByOrderByAddedAtDesc();

    Optional<StoredDocument> findFirstByTitleAndDocumentLinkOrderByIdAsc(
            String title,
            String documentLink
    );
}

