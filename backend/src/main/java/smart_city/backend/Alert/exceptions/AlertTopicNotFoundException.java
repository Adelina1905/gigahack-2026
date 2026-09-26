package smart_city.backend.Alert.exceptions;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class AlertTopicNotFoundException extends RuntimeException {

    public AlertTopicNotFoundException() {
        super("Alert topic not found");
    }
}
