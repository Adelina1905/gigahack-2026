package smart_city.backend.Response.exceptions;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.CONFLICT)
public class ResponseNotRegenerableException extends RuntimeException {

    public ResponseNotRegenerableException() {
        super("Response has no stored prompt to regenerate from");
    }
}
