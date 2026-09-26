package smart_city.backend.config;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import smart_city.backend.Alert.exceptions.AlertMatcherUnavailableException;

@RestControllerAdvice
public class ApiExceptionHandler {
    public record ErrorBody(String code, String message) {
    }

    @ExceptionHandler(ApiConflictException.class)
    public ResponseEntity<ErrorBody> conflict(ApiConflictException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ErrorBody(exception.getCode(), exception.getMessage()));
    }

    @ExceptionHandler(AlertMatcherUnavailableException.class)
    public ResponseEntity<ErrorBody> alertsUnavailable(AlertMatcherUnavailableException exception) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorBody(
                        AlertMatcherUnavailableException.CODE,
                        "The alerts service is unavailable. Try again shortly."
                ));
    }
}
