package smart_city.backend.Llm;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import smart_city.backend.Llm.dto.LlmErrorBody;
import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.Llm.dto.LlmServiceRequest;
import smart_city.backend.Llm.dto.LlmTurn;
import smart_city.backend.Llm.exceptions.LlmUnavailableException;

import java.util.List;
import java.util.UUID;

@Component
public class LlmServiceClient implements LlmGateway {

    static final String CHAT_PATH = "/v1/chat";

    private final RestClient llmRestClient;

    public LlmServiceClient(RestClient llmRestClient) {
        this.llmRestClient = llmRestClient;
    }

    @Override
    public LlmReply chat(
            UUID chatId,
            String message,
            List<LlmTurn> history
    ) {
        LlmServiceRequest request = new LlmServiceRequest(
                chatId,
                message,
                history
        );

        LlmReply reply;
        try {
            reply = llmRestClient
                    .post()
                    .uri(CHAT_PATH)
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(LlmReply.class);
        } catch (RestClientResponseException exception) {
            throw new LlmUnavailableException(
                    "LLM service responded with "
                            + exception.getStatusCode().value()
                            + describeDetail(exception),
                    exception
            );
        } catch (RestClientException exception) {
            throw new LlmUnavailableException(
                    "LLM service call failed: " + exception.getMessage(),
                    exception
            );
        }

        if (reply == null || reply.answer() == null) {
            throw new LlmUnavailableException(
                    "LLM service returned an empty answer"
            );
        }

        return reply;
    }

    private String describeDetail(RestClientResponseException exception) {
        try {
            LlmErrorBody body = exception.getResponseBodyAs(LlmErrorBody.class);
            if (body != null && body.detail() != null) {
                return ": " + body.detail();
            }
        } catch (RuntimeException ignored) {
            // Body was not the expected {"detail": ...} JSON.
        }
        return "";
    }
}
