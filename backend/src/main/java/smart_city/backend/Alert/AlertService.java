package smart_city.backend.Alert;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Limit;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import smart_city.backend.Alert.dto.AlertMatch;
import smart_city.backend.Alert.dto.AlertSettingsView;
import smart_city.backend.Alert.dto.AlertTopicView;
import smart_city.backend.Alert.dto.AlertView;
import smart_city.backend.Alert.dto.MatchServiceReply;
import smart_city.backend.Alert.dto.MatchTopic;
import smart_city.backend.Alert.dto.ScopeUnreadCount;
import smart_city.backend.Alert.dto.ScanResult;
import smart_city.backend.Alert.dto.TopicSuggestion;
import smart_city.backend.Alert.dto.UnreadCountView;
import smart_city.backend.Alert.exceptions.AlertMatcherUnavailableException;
import smart_city.backend.Alert.exceptions.AlertNotFoundException;
import smart_city.backend.Alert.exceptions.AlertTopicNotFoundException;
import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Chat.exceptions.ChatNotFoundException;
import smart_city.backend.Project.ProjectRepository;
import smart_city.backend.Project.exceptions.ProjectNotFoundException;

import java.sql.Types;
import java.time.OffsetDateTime;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Alerts of projects and of single chats. Both scopes share this logic through an
 * {@link AlertSubscription}; they differ only in ownership and where the questions come from.
 * Calls to the Python matcher happen between short transactions (TransactionTemplate),
 * so no DB connection is held while it runs.
 */
@Service
public class AlertService {

    private static final Logger log = LoggerFactory.getLogger(AlertService.class);

    static final int MAX_QUESTIONS = 50;
    static final int MAX_QUESTION_CHARS = 8000;
    static final int MAX_EXISTING_LABELS = 50;
    static final int MAX_MATCH_TOPICS = 50;
    static final int MAX_LIST_LIMIT = 200;
    static final int MAX_EXCERPT = 400;
    static final String NO_MATCHER = "none";

    private static final String INSERT_SUBSCRIPTION = """
            INSERT INTO alert_subscriptions (client_id, project_id, chat_id)
            VALUES (:clientId, :projectId, :chatId)
            ON CONFLICT DO NOTHING
            """;

    private static final String INSERT_ALERT = """
            INSERT INTO alerts (client_id, subscription_id, project_id, chat_id, topic_id, topic_label,
                                document_id, title, url, source, district, category, published_date,
                                excerpt, score, created_at)
            VALUES (:clientId, :subscriptionId, :projectId, :chatId, :topicId, :topicLabel,
                    :documentId, :title, :url, :source, :district, :category, :publishedDate,
                    :excerpt, :score, :createdAt)
            ON CONFLICT (subscription_id, document_id) DO NOTHING
            """;

    private final AlertRepository alerts;
    private final AlertTopicRepository topics;
    private final AlertSubscriptionRepository subscriptions;
    private final ProjectRepository projects;
    private final ChatRepository chats;
    private final AlertMatcherGateway matcher;
    private final AlertProperties properties;
    private final TransactionTemplate transactions;
    private final NamedParameterJdbcTemplate jdbc;

    public AlertService(
            AlertRepository alerts,
            AlertTopicRepository topics,
            AlertSubscriptionRepository subscriptions,
            ProjectRepository projects,
            ChatRepository chats,
            AlertMatcherGateway matcher,
            AlertProperties properties,
            TransactionTemplate transactions,
            NamedParameterJdbcTemplate jdbc
    ) {
        this.alerts = alerts;
        this.topics = topics;
        this.subscriptions = subscriptions;
        this.projects = projects;
        this.chats = chats;
        this.matcher = matcher;
        this.properties = properties;
        this.transactions = transactions;
        this.jdbc = jdbc;
    }


    // Alerts

    // Null projectId / chatId: no filter.
    @Transactional(readOnly = true)
    public List<AlertView> getAlerts(UUID clientId, UUID projectId, UUID chatId, boolean unreadOnly, int limit) {

        requireOwnedFilters(clientId, projectId, chatId);

        return alerts
                .findVisible(clientId, projectId, chatId, unreadOnly, Limit.of(Math.clamp(limit, 1, MAX_LIST_LIMIT)))
                .stream()
                .map(AlertView::from)
                .toList();
    }


    @Transactional(readOnly = true)
    public UnreadCountView getUnreadCount(UUID clientId) {

        Map<UUID, Long> byProject = new LinkedHashMap<>();
        Map<UUID, Long> byChat = new LinkedHashMap<>();
        long total = 0;
        for (ScopeUnreadCount row : alerts.countUnreadByScope(clientId)) {
            if (row.projectId() != null) {
                byProject.merge(row.projectId(), row.count(), Long::sum);
            } else if (row.chatId() != null) {
                byChat.merge(row.chatId(), row.count(), Long::sum);
            }
            total += row.count();
        }

        return new UnreadCountView(total, byProject, byChat);
    }


    @Transactional
    public AlertView markRead(UUID clientId, Long alertId) {

        Alert alert = findVisibleAlert(clientId, alertId);
        alert.markRead(OffsetDateTime.now());

        return AlertView.from(alert);
    }


    // Null projectId and chatId: every alert of the client.
    @Transactional
    public int markAllRead(UUID clientId, UUID projectId, UUID chatId) {

        requireOwnedFilters(clientId, projectId, chatId);

        return alerts.markAllRead(clientId, projectId, chatId, OffsetDateTime.now());
    }


    // "Not relevant": hides the alert (its row keeps the document excluded) and makes its topic stricter.
    @Transactional
    public void dismissNotRelevant(UUID clientId, Long alertId) {

        Alert alert = findVisibleAlert(clientId, alertId);
        alert.dismiss(Alert.NOT_RELEVANT, OffsetDateTime.now());

        if (alert.getTopicId() != null) {
            topics.findById(alert.getTopicId())
                    .ifPresent(topic -> topic.raiseMinScore(alert.getScore()));
        }
    }


    // Settings and topics

    @Transactional(readOnly = true)
    public AlertSettingsView getSettings(UUID clientId, AlertScope scope) {

        requireOwned(clientId, scope);

        return settingsView(scope);
    }


    /**
     * Sets prompted=true (the one-time prompt is answered either way). Turning alerts on also
     * extracts topics when there are none and runs a backfill scan; if the Python service is
     * unavailable the saved setting stays and AlertMatcherUnavailableException is thrown.
     */
    public AlertSettingsView updateSettings(UUID clientId, AlertScope scope, boolean enabled) {

        Long turnedOn = transactions.execute(tx -> {
            requireOwned(clientId, scope);
            AlertSubscription row = findOrCreateSubscription(clientId, scope);
            boolean wasEnabled = row.isEnabled();
            row.setEnabled(enabled);
            row.setPrompted(true);
            row.touch();
            return enabled && !wasEnabled ? row.getId() : null;
        });

        if (turnedOn != null) {
            boolean hasTopics = Boolean.TRUE.equals(transactions.execute(
                    tx -> topics.existsBySubscriptionIdAndRemovedFalse(turnedOn)
            ));
            if (!hasTopics) {
                refresh(turnedOn);
            }
            scan(turnedOn, properties.manualMax());
        }

        return readSettings(scope);
    }


    public AlertSettingsView refreshTopics(UUID clientId, AlertScope scope) {

        Long subscriptionId = transactions.execute(tx -> {
            requireOwned(clientId, scope);
            return findOrCreateSubscription(clientId, scope).getId();
        });
        refresh(subscriptionId);

        return readSettings(scope);
    }


    @Transactional
    public AlertTopicView addTopic(UUID clientId, AlertScope scope, String label) {

        requireOwned(clientId, scope);
        Long subscriptionId = findOrCreateSubscription(clientId, scope).getId();
        String cleaned = clean(label, AlertTopic.MAX_LABEL);

        // Adding a label the scope already follows returns that topic instead of a duplicate.
        for (AlertTopic existing : topics.findAllBySubscriptionIdAndRemovedFalseOrderByCreatedAtAscIdAsc(subscriptionId)) {
            if (existing.getLabel().equalsIgnoreCase(cleaned)) {
                return AlertTopicView.from(existing);
            }
        }

        AlertTopic topic = topics.save(
                new AlertTopic(subscriptionId, cleaned, cleaned, AlertTopicSource.USER)
        );
        return AlertTopicView.from(topic);
    }


    @Transactional
    public AlertTopicView renameTopic(UUID clientId, AlertScope scope, Long topicId, String label) {

        requireOwned(clientId, scope);
        AlertTopic topic = findTopic(scope, topicId);

        String cleaned = clean(label, AlertTopic.MAX_LABEL);
        topic.setLabel(cleaned);
        topic.setQuery(cleaned);
        topic.setSource(AlertTopicSource.USER);

        return AlertTopicView.from(topic);
    }


    // AUTO topics are only marked removed, so a refresh never re-creates them; USER topics are deleted.
    @Transactional
    public void deleteTopic(UUID clientId, AlertScope scope, Long topicId) {

        requireOwned(clientId, scope);
        AlertTopic topic = findTopic(scope, topicId);

        if (topic.getSource() == AlertTopicSource.AUTO) {
            topic.setRemoved(true);
        } else {
            topics.delete(topic);
        }
    }


    // Scans

    // "Check now": works even when alerts are off.
    public ScanResult scanNow(UUID clientId, AlertScope scope) {

        Long subscriptionId = transactions.execute(tx -> {
            requireOwned(clientId, scope);
            return findOrCreateSubscription(clientId, scope).getId();
        });

        return scan(subscriptionId, properties.manualMax());
    }


    /**
     * The scheduled scan of every enabled subscription (project or chat): refreshes topics when
     * the scope has newer questions, then adds up to app.alerts.max-per-scan alerts. Never throws.
     */
    public void scanEnabledSubscriptions() {

        List<Long> subscriptionIds;
        try {
            subscriptionIds = transactions.execute(tx -> subscriptions.findEnabledIds());
        } catch (RuntimeException exception) {
            log.warn("Alert scan skipped: could not list enabled subscriptions", exception);
            return;
        }

        for (Long subscriptionId : subscriptionIds) {
            try {
                if (hasNewQuestions(subscriptionId)) {
                    refresh(subscriptionId);
                }
                ScanResult result = scan(subscriptionId, properties.maxPerScan());
                if (result.created() > 0) {
                    log.info("Alert scan created {} alert(s) for subscription {}", result.created(), subscriptionId);
                }
            } catch (AlertMatcherUnavailableException exception) {
                // The Python service is down: skip this round, the next one retries.
                log.warn("Alert scan skipped: {}", exception.getMessage());
                return;
            } catch (RuntimeException exception) {
                log.error("Alert scan failed for subscription {}", subscriptionId, exception);
            }
        }
    }


    // Where each scope's questions come from: all the project's chats, or the one chat.

    private List<String> prompts(AlertScope scope) {

        return scope.isProject()
                ? topics.findProjectPrompts(scope.projectId(), Limit.of(MAX_QUESTIONS))
                : topics.findChatPrompts(scope.chatId(), Limit.of(MAX_QUESTIONS));
    }

    private OffsetDateTime latestPromptAt(AlertScope scope) {

        return scope.isProject()
                ? topics.findLatestProjectPromptAt(scope.projectId())
                : topics.findLatestChatPromptAt(scope.chatId());
    }


    private boolean hasNewQuestions(Long subscriptionId) {

        return Boolean.TRUE.equals(transactions.execute(tx -> subscriptions.findById(subscriptionId)
                .map(row -> {
                    OffsetDateTime latest = latestPromptAt(row.scope());
                    OffsetDateTime refreshed = row.getTopicsRefreshedAt();
                    return latest != null && (refreshed == null || latest.isAfter(refreshed));
                })
                .orElse(false)
        ));
    }


    private record RefreshInput(List<String> questions, List<String> labels) {
    }

    // Extracts topics from the scope's questions and adds the new labels as AUTO topics.
    private void refresh(Long subscriptionId) {

        // Taken before the call, so questions asked meanwhile trigger the next refresh.
        OffsetDateTime refreshedAt = OffsetDateTime.now();

        RefreshInput input = transactions.execute(tx -> subscriptions.findById(subscriptionId)
                .map(row -> new RefreshInput(
                        prompts(row.scope())
                                .stream()
                                .map(String::trim)
                                .filter(prompt -> !prompt.isEmpty())
                                .map(prompt -> truncate(prompt, MAX_QUESTION_CHARS))
                                .toList(),
                        topics.findAllBySubscriptionIdOrderByCreatedAtAscIdAsc(subscriptionId)
                                .stream()
                                .map(AlertTopic::getLabel)
                                .toList()
                ))
                .orElse(null)
        );

        if (input == null || input.questions().isEmpty()) {
            return;
        }

        List<String> recentLabels = input.labels().subList(
                Math.max(0, input.labels().size() - MAX_EXISTING_LABELS),
                input.labels().size()
        );
        List<TopicSuggestion> suggestions = matcher.topics(input.questions(), recentLabels);

        transactions.executeWithoutResult(tx -> {
            AlertSubscription row = subscriptions.findById(subscriptionId).orElse(null);
            if (row == null) {
                // The project or chat was deleted while the service ran.
                return;
            }

            // Removed labels count too, so they never come back.
            Set<String> known = new HashSet<>();
            for (AlertTopic topic : topics.findAllBySubscriptionIdOrderByCreatedAtAscIdAsc(subscriptionId)) {
                known.add(key(topic.getLabel()));
            }

            for (TopicSuggestion suggestion : suggestions) {
                if (suggestion == null || suggestion.label() == null || suggestion.label().isBlank()) {
                    continue;
                }
                String label = clean(suggestion.label(), AlertTopic.MAX_LABEL);
                if (!known.add(key(label))) {
                    continue;
                }
                String query = suggestion.query() == null || suggestion.query().isBlank()
                        ? label
                        : clean(suggestion.query(), AlertTopic.MAX_QUERY);
                topics.save(new AlertTopic(subscriptionId, label, query, AlertTopicSource.AUTO));
            }

            row.setTopicsRefreshedAt(refreshedAt);
        });
    }


    private record ScanInput(
            UUID clientId,
            AlertScope scope,
            Map<Long, AlertTopic> topics,
            List<String> excluded
    ) {
    }

    // Matches the subscription's topics against the update feed and stores up to `limit` new alerts.
    private ScanResult scan(Long subscriptionId, int limit) {

        ScanInput input = transactions.execute(tx -> {
            AlertSubscription row = subscriptions.findById(subscriptionId).orElse(null);
            if (row == null) {
                return null;
            }
            Map<Long, AlertTopic> active = topics
                    .findAllBySubscriptionIdAndRemovedFalseOrderByCreatedAtAscIdAsc(subscriptionId)
                    .stream()
                    .limit(MAX_MATCH_TOPICS)
                    .collect(Collectors.toMap(
                            AlertTopic::getId,
                            Function.identity(),
                            (first, second) -> first,
                            LinkedHashMap::new
                    ));
            return new ScanInput(row.getClientId(), row.scope(), active, alerts.findDocumentIds(subscriptionId));
        });

        if (input == null) {
            return new ScanResult(0, NO_MATCHER);
        }
        if (input.topics().isEmpty()) {
            markScanned(subscriptionId);
            return new ScanResult(0, NO_MATCHER);
        }

        List<MatchTopic> request = input.topics().values().stream()
                .map(topic -> new MatchTopic(
                        topic.getId().toString(),
                        topic.getQuery(),
                        topic.getMinScore()
                ))
                .toList();
        MatchServiceReply reply = matcher.match(request, input.excluded(), limit);

        Integer created = transactions.execute(tx -> {
            if (!subscriptions.existsById(subscriptionId)) {
                // The project or chat was deleted while the matcher ran.
                return 0;
            }
            Set<String> seen = new HashSet<>(input.excluded());
            int inserted = 0;
            for (AlertMatch match : reply.matchesOrEmpty()) {
                if (inserted >= limit) {
                    break;
                }
                AlertTopic topic = topicOf(input.topics(), match);
                if (topic == null || match.documentId() == null || match.documentId().isBlank()
                        || match.documentId().length() > 128 || !seen.add(match.documentId())) {
                    continue;
                }
                inserted += insertAlert(subscriptionId, input, topic, match);
            }
            markScanned(subscriptionId);
            return inserted;
        });

        return new ScanResult(created == null ? 0 : created, reply.matcher());
    }


    private static AlertTopic topicOf(Map<Long, AlertTopic> active, AlertMatch match) {

        if (match == null || match.topicId() == null) {
            return null;
        }
        try {
            return active.get(Long.valueOf(match.topicId()));
        } catch (NumberFormatException exception) {
            return null;
        }
    }


    // ON CONFLICT: a concurrent scan that stored the same document first wins, without failing this one.
    private int insertAlert(Long subscriptionId, ScanInput input, AlertTopic topic, AlertMatch match) {

        // The topic may have been deleted while the matcher ran; the label snapshot keeps the reason.
        Long topicId = topics.existsById(topic.getId()) ? topic.getId() : null;
        String excerpt = match.excerpt() == null ? "" : truncate(match.excerpt().trim(), MAX_EXCERPT);
        String title = match.title() == null || match.title().isBlank()
                ? match.documentId()
                : match.title().trim();

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("clientId", input.clientId(), Types.OTHER)
                .addValue("subscriptionId", subscriptionId, Types.BIGINT)
                .addValue("projectId", input.scope().projectId(), Types.OTHER)
                .addValue("chatId", input.scope().chatId(), Types.OTHER)
                .addValue("topicId", topicId, Types.BIGINT)
                .addValue("topicLabel", topic.getLabel(), Types.VARCHAR)
                .addValue("documentId", match.documentId(), Types.VARCHAR)
                .addValue("title", title, Types.VARCHAR)
                .addValue("url", blankToNull(match.url(), Integer.MAX_VALUE), Types.VARCHAR)
                .addValue("source", blankToNull(match.source(), 128), Types.VARCHAR)
                .addValue("district", blankToNull(match.district(), 128), Types.VARCHAR)
                .addValue("category", blankToNull(match.category(), 128), Types.VARCHAR)
                .addValue("publishedDate", match.publishedDate(), Types.DATE)
                .addValue("excerpt", excerpt, Types.VARCHAR)
                .addValue("score", match.score(), Types.DOUBLE)
                .addValue("createdAt", OffsetDateTime.now(), Types.TIMESTAMP_WITH_TIMEZONE);

        return jdbc.update(INSERT_ALERT, parameters);
    }


    private void markScanned(Long subscriptionId) {

        transactions.executeWithoutResult(tx -> subscriptions.findById(subscriptionId)
                .ifPresent(row -> row.setLastScanAt(OffsetDateTime.now())));
    }


    private AlertSettingsView readSettings(AlertScope scope) {

        return transactions.execute(tx -> settingsView(scope));
    }


    private AlertSettingsView settingsView(AlertScope scope) {

        return subscriptions.findByScope(scope)
                .map(row -> new AlertSettingsView(
                        scope.projectId(),
                        scope.chatId(),
                        row.isEnabled(),
                        row.isPrompted(),
                        topics.findAllBySubscriptionIdAndRemovedFalseOrderByCreatedAtAscIdAsc(row.getId())
                                .stream()
                                .map(AlertTopicView::from)
                                .toList(),
                        row.getLastScanAt()
                ))
                .orElseGet(() -> new AlertSettingsView(
                        scope.projectId(), scope.chatId(), false, false, List.of(), null
                ));
    }


    // ON CONFLICT: a concurrent request that created the subscription first wins, without failing this one.
    private AlertSubscription findOrCreateSubscription(UUID clientId, AlertScope scope) {

        return subscriptions.findByScope(scope).orElseGet(() -> {
            jdbc.update(INSERT_SUBSCRIPTION, new MapSqlParameterSource()
                    .addValue("clientId", clientId, Types.OTHER)
                    .addValue("projectId", scope.projectId(), Types.OTHER)
                    .addValue("chatId", scope.chatId(), Types.OTHER));
            return subscriptions.findByScope(scope).orElseThrow();
        });
    }


    // 404 (ProjectNotFoundException / ChatNotFoundException) unless the client owns the scope.
    private void requireOwned(UUID clientId, AlertScope scope) {

        if (scope.isProject()) {
            projects.findByIdAndClientId(scope.projectId(), clientId)
                    .orElseThrow(ProjectNotFoundException::new);
        } else {
            chats.findByIdAndClientId(scope.chatId(), clientId)
                    .orElseThrow(ChatNotFoundException::new);
        }
    }


    private void requireOwnedFilters(UUID clientId, UUID projectId, UUID chatId) {

        if (projectId != null) {
            requireOwned(clientId, AlertScope.project(projectId));
        }
        if (chatId != null) {
            requireOwned(clientId, AlertScope.chat(chatId));
        }
    }


    private Alert findVisibleAlert(UUID clientId, Long alertId) {

        return alerts
                .findByIdAndClientId(alertId, clientId)
                .filter(alert -> alert.getDismissedAt() == null)
                .orElseThrow(AlertNotFoundException::new);
    }


    private AlertTopic findTopic(AlertScope scope, Long topicId) {

        return subscriptions.findByScope(scope)
                .flatMap(row -> topics.findByIdAndSubscriptionIdAndRemovedFalse(topicId, row.getId()))
                .orElseThrow(AlertTopicNotFoundException::new);
    }


    private static String key(String label) {
        return label.trim().toLowerCase(Locale.ROOT);
    }

    private static String clean(String value, int length) {
        return truncate(value.trim().replaceAll("\\s+", " "), length);
    }

    private static String blankToNull(String value, int length) {
        return value == null || value.isBlank() ? null : truncate(value.trim(), length);
    }

    private static String truncate(String value, int length) {
        return value.length() <= length ? value : value.substring(0, length).trim();
    }
}
