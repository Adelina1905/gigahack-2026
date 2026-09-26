package smart_city.backend.Response;

import org.springframework.stereotype.Service;

@Service
public class AiResponseProvider {

    public String generateResponse(String userInput) {
        /*
         * AI INTEGRATION POINT:
         * Replace the placeholder below with the call to the Python AI service.
         * `userInput` contains the message submitted by the user.
         * Return the answer produced by the Python service from this method.
         */
        return "This is a placeholder AI response for: " + userInput;
    }
}
