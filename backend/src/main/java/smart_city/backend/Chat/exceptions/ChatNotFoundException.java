package smart_city.backend.Chat.exceptions;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class ChatNotFoundException extends RuntimeException {

    public ChatNotFoundException() {
        super("Chat not found");
    }
}
