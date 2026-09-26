package smart_city.backend.Alert;

import smart_city.backend.Alert.dto.AlertMatch;
import smart_city.backend.Alert.dto.MatchServiceReply;
import smart_city.backend.Alert.dto.MatchTopic;
import smart_city.backend.Alert.dto.TopicSuggestion;
import smart_city.backend.Alert.exceptions.AlertMatcherUnavailableException;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Hand-written matcher: topics come from a canned list; a feed document matches a topic
 * whose query contains the document's keyword, with the document's fixed score.
 */
public final class FakeAlertMatcher implements AlertMatcherGateway {

    public static final double DEFAULT_THRESHOLD = 0.3;

    public record FeedDocument(String documentId, String keyword, double score) {
    }

    public record TopicsCall(List<String> questions, List<String> existingLabels) {
    }

    public record MatchCall(List<MatchTopic> topics, List<String> excludedDocumentIds, int limit) {
    }

    public final List<TopicsCall> topicsCalls = new CopyOnWriteArrayList<>();
    public final List<MatchCall> matchCalls = new CopyOnWriteArrayList<>();

    private volatile List<TopicSuggestion> suggestions = List.of();
    private volatile List<FeedDocument> feed = List.of();
    private volatile boolean failing;
    private volatile boolean ignoringExclusions;

    public void reset() {
        topicsCalls.clear();
        matchCalls.clear();
        suggestions = List.of();
        feed = List.of();
        failing = false;
        ignoringExclusions = false;
    }

    public void suggest(TopicSuggestion... suggestions) {
        this.suggestions = List.of(suggestions);
    }

    public void feed(FeedDocument... documents) {
        this.feed = List.of(documents);
    }

    public void setFailing(boolean failing) {
        this.failing = failing;
    }

    // Simulates a concurrent scan that stored a document after the exclusion list was read.
    public void setIgnoringExclusions(boolean ignoringExclusions) {
        this.ignoringExclusions = ignoringExclusions;
    }

    @Override
    public List<TopicSuggestion> topics(List<String> questions, List<String> existingLabels) {
        topicsCalls.add(new TopicsCall(List.copyOf(questions), List.copyOf(existingLabels)));
        if (failing) {
            throw new AlertMatcherUnavailableException("service down");
        }
        return suggestions;
    }

    @Override
    public MatchServiceReply match(List<MatchTopic> topics, List<String> excludedDocumentIds, int limit) {
        matchCalls.add(new MatchCall(List.copyOf(topics), List.copyOf(excludedDocumentIds), limit));
        if (failing) {
            throw new AlertMatcherUnavailableException("service down");
        }

        List<AlertMatch> matches = new ArrayList<>();
        for (FeedDocument document : feed) {
            if (!ignoringExclusions && excludedDocumentIds.contains(document.documentId())) {
                continue;
            }
            topics.stream()
                    .filter(topic -> topic.query().toLowerCase(Locale.ROOT)
                            .contains(document.keyword().toLowerCase(Locale.ROOT)))
                    .filter(topic -> document.score()
                            >= (topic.minScore() == null ? DEFAULT_THRESHOLD : topic.minScore()))
                    .findFirst()
                    .ifPresent(topic -> matches.add(new AlertMatch(
                            topic.id(),
                            document.documentId(),
                            "Title " + document.documentId(),
                            "https://example.md/" + document.documentId(),
                            "Primăria",
                            "Centru",
                            "anunț",
                            LocalDate.of(2026, 9, 1),
                            "Excerpt " + document.documentId(),
                            document.score()
                    )));
        }
        matches.sort(Comparator.comparingDouble(AlertMatch::score).reversed());

        return new MatchServiceReply(
                "lexical",
                matches.subList(0, Math.min(limit, matches.size()))
        );
    }
}
