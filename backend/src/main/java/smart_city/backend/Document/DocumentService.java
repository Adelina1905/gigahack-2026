package smart_city.backend.Document;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import smart_city.backend.Document.dto.DocumentCreateRequest;
import smart_city.backend.Document.dto.DocumentView;
import smart_city.backend.Document.exceptions.DocumentNotFoundException;

import java.util.List;

@Service
public class DocumentService {

    private final DocumentRepository documentRepository;

    public DocumentService(DocumentRepository documentRepository) {
        this.documentRepository = documentRepository;
    }

    @Transactional(readOnly = true)
    public List<DocumentView> getAllDocuments() {
        return documentRepository
                .findAllByOrderByAddedAtDesc()
                .stream()
                .map(DocumentView::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public DocumentView getDocument(Long documentId) {
        return documentRepository
                .findById(documentId)
                .map(DocumentView::from)
                .orElseThrow(DocumentNotFoundException::new);
    }

    @Transactional
    public DocumentView createDocument(DocumentCreateRequest request) {
        StoredDocument document = new StoredDocument(
                request.title().trim(),
                request.documentLink().trim()
        );

        return DocumentView.from(documentRepository.save(document));
    }

    // Cited documents are stored once and shared by every response citing them.
    @Transactional
    public StoredDocument findOrCreate(String title, String documentLink) {
        return documentRepository
                .findFirstByTitleAndDocumentLinkOrderByIdAsc(title, documentLink)
                .orElseGet(() -> documentRepository.save(
                        new StoredDocument(title, documentLink)
                ));
    }
}
