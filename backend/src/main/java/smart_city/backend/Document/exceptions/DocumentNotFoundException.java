package smart_city.backend.Document.exceptions;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class DocumentNotFoundException extends RuntimeException {

    public DocumentNotFoundException() {
        super("Document not found");
    }
}

