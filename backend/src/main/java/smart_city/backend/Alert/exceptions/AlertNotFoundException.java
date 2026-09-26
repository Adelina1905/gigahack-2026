package smart_city.backend.Alert.exceptions;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class AlertNotFoundException extends RuntimeException {

    public AlertNotFoundException() {
        super("Alert not found");
    }
}
