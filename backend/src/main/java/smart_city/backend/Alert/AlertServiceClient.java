package smart_city.backend.Alert;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import smart_city.backend.Alert.dto.MatchServiceReply;
import smart_city.backend.Alert.dto.MatchServiceRequest;
import smart_city.backend.Alert.dto.MatchTopic;
import smart_city.backend.Alert.dto.TopicSuggestion;
import smart_city.backend.Alert.dto.TopicsServiceReply;
import smart_city.backend.Alert.dto.TopicsServiceRequest;
import smart_city.backend.Alert.exceptions.AlertMatcherUnavailableException;

import java.util.List;

@Component
public class AlertServiceClient implements AlertMatcherGateway {

    static final String TOPICS_PATH = "/v1/alerts/topics";
    static final String MATCH_PATH = "/v1/alerts/match";

    private final RestClient llmRestClient;

    public AlertServiceClient(RestClient llmRestClient) {
        this.llmRestClient = llmRestClient;
    }

    @Override
    public List<TopicSuggestion> topics(List<String> questions, List<String> existingLabels) {
        TopicsServiceReply reply = post(
                TOPICS_PATH,
                new TopicsServiceRequest(questions, existingLabels),
                TopicsServiceReply.class
        );

        if (reply.topics() == null) {
            throw new AlertMatcherUnavailableException("Alert service returned no topics list");
        }
        return reply.topics();
    }

    @Override
    public MatchServiceReply match(List<MatchTopic> topics, List<String> excludedDocumentIds, int limit) {
        MatchServiceReply reply = post(
                MATCH_PATH,
                new MatchServiceRequest(topics, excludedDocumentIds, limit),
                MatchServiceReply.class
        );

        if (reply.matcher() == null || reply.matches() == null) {
            throw new AlertMatcherUnavailableException("Alert service returned an incomplete match result");
        }
        return reply;
    }

    private <T> T post(String path, Object body, Class<T> type) {
        T reply;
        try {
            reply = llmRestClient
                    .post()
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(type);
        } catch (RestClientResponseException exception) {
            throw new AlertMatcherUnavailableException(
                    "Alert service responded with " + exception.getStatusCode().value(),
                    exception
            );
        } catch (RestClientException exception) {
            throw new AlertMatcherUnavailableException(
                    "Alert service call failed: " + exception.getMessage(),
                    exception
            );
        }

        if (reply == null) {
            throw new AlertMatcherUnavailableException("Alert service returned an empty body");
        }
        return reply;
    }
}
