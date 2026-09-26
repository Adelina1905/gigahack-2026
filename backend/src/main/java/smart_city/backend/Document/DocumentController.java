package smart_city.backend.Document;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import smart_city.backend.Document.dto.DocumentCreateRequest;
import smart_city.backend.Document.dto.DocumentView;

import java.util.List;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService documentService;

    public DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @GetMapping
    public List<DocumentView> getAllDocuments() {
        return documentService.getAllDocuments();
    }

    @GetMapping("/{documentId}")
    public DocumentView getDocument(@PathVariable Long documentId) {
        return documentService.getDocument(documentId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public DocumentView createDocument(
            @Valid @RequestBody DocumentCreateRequest request
    ) {
        return documentService.createDocument(request);
    }
}
