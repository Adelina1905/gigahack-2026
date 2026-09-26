package smart_city.backend.Alert.exceptions;

// Mapped to 503 {code, message} by ApiExceptionHandler.
public class AlertMatcherUnavailableException extends RuntimeException {

    public static final String CODE = "ALERTS_UNAVAILABLE";

    public AlertMatcherUnavailableException(String message) {
        super(message);
    }

    public AlertMatcherUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
