package smart_city.backend.Response.exceptions;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class ResponseNotFoundException extends RuntimeException {

    public ResponseNotFoundException() {
        super("Response not found");
    }
}

