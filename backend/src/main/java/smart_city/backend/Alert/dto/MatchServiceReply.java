package smart_city.backend.Alert.dto;

import java.util.List;

public record MatchServiceReply(
        String matcher,
        List<AlertMatch> matches
) {

    public List<AlertMatch> matchesOrEmpty() {
        return matches == null ? List.of() : matches;
    }
}
