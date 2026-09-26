package smart_city.backend.Alert.dto;

import smart_city.backend.Alert.AlertTopic;
import smart_city.backend.Alert.AlertTopicSource;

public record AlertTopicView(
        Long id,
        String label,
        String query,
        AlertTopicSource source,
        Double minScore
) {

    public static AlertTopicView from(AlertTopic topic) {

        return new AlertTopicView(
                topic.getId(),
                topic.getLabel(),
                topic.getQuery(),
                topic.getSource(),
                topic.getMinScore()
        );
    }
}
