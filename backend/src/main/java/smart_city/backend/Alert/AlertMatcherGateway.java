package smart_city.backend.Alert;

import smart_city.backend.Alert.dto.MatchServiceReply;
import smart_city.backend.Alert.dto.MatchTopic;
import smart_city.backend.Alert.dto.TopicSuggestion;
import smart_city.backend.Alert.exceptions.AlertMatcherUnavailableException;

import java.util.List;

/** The Python service's alert endpoints. Implementations throw {@link AlertMatcherUnavailableException} on failure. */
public interface AlertMatcherGateway {

    List<TopicSuggestion> topics(List<String> questions, List<String> existingLabels);

    MatchServiceReply match(List<MatchTopic> topics, List<String> excludedDocumentIds, int limit);
}
