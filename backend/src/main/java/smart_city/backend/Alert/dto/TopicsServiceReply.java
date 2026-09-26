package smart_city.backend.Alert.dto;

import java.util.List;

public record TopicsServiceReply(
        List<TopicSuggestion> topics
) {
}
