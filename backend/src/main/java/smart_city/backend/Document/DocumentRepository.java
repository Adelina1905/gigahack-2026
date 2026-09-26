package smart_city.backend.Document;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface DocumentRepository
        extends JpaRepository<StoredDocument, Long> {

    List<StoredDocument> findAllByOrderByAddedAtDesc();
}

