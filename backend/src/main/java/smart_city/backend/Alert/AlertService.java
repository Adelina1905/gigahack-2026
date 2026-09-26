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
import smart_city.backend.Alert.dto.ProjectUnreadCount;
import smart_city.backend.Alert.dto.ScanResult;
import smart_city.backend.Alert.dto.TopicSuggestion;
import smart_city.backend.Alert.dto.UnreadCountView;
import smart_city.backend.Alert.exceptions.AlertMatcherUnavailableException;
import smart_city.backend.Alert.exceptions.AlertNotFoundException;
import smart_city.backend.Alert.exceptions.AlertTopicNotFoundException;
import smart_city.backend.Project.Project;
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
 * Project alerts. Calls to the Python matcher happen between short transactions
 * (TransactionTemplate), so no DB connection is held while it runs.
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

    private static final String INSERT_ALERT = """
            INSERT INTO alerts (client_id, project_id, topic_id, topic_label, document_id, title, url,
                                source, district, category, published_date, excerpt, score, created_at)
            VALUES (:clientId, :projectId, :topicId, :topicLabel, :documentId, :title, :url,
                    :source, :district, :category, :publishedDate, :excerpt, :score, :createdAt)
            ON CONFLICT (project_id, document_id) DO NOTHING
            """;

    private final AlertRepository alerts;
    private final AlertTopicRepository topics;
    private final ProjectAlertSettingsRepository settings;
    private final ProjectRepository projects;
    private final AlertMatcherGateway matcher;
    private final AlertProperties properties;
    private final TransactionTemplate transactions;
    private final NamedParameterJdbcTemplate jdbc;

    public AlertService(
            AlertRepository alerts,
            AlertTopicRepository topics,
            ProjectAlertSettingsRepository settings,
            ProjectRepository projects,
            AlertMatcherGateway matcher,
            AlertProperties properties,
            TransactionTemplate transactions,
            NamedParameterJdbcTemplate jdbc
    ) {
        this.alerts = alerts;
        this.topics = topics;
        this.settings = settings;
        this.projects = projects;
        this.matcher = matcher;
        this.properties = properties;
        this.transactions = transactions;
        this.jdbc = jdbc;
    }


    // Alerts

    @Transactional(readOnly = true)
    public List<AlertView> getAlerts(UUID clientId, UUID projectId, boolean unreadOnly, int limit) {

        if (projectId != null) {
            findOwnedProject(clientId, projectId);
        }

        return alerts
                .findVisible(clientId, projectId, unreadOnly, Limit.of(Math.clamp(limit, 1, MAX_LIST_LIMIT)))
                .stream()
                .map(AlertView::from)
                .toList();
    }


    @Transactional(readOnly = true)
    public UnreadCountView getUnreadCount(UUID clientId) {

        Map<UUID, Long> byProject = new LinkedHashMap<>();
        long total = 0;
        for (ProjectUnreadCount row : alerts.countUnreadByProject(clientId)) {
            byProject.put(row.projectId(), row.count());
            total += row.count();
        }

        return new UnreadCountView(total, byProject);
    }


    @Transactional
    public AlertView markRead(UUID clientId, Long alertId) {

        Alert alert = findVisibleAlert(clientId, alertId);
        alert.markRead(OffsetDateTime.now());

        return AlertView.from(alert);
    }


    @Transactional
    public int markAllRead(UUID clientId, UUID projectId) {

        if (projectId != null) {
            findOwnedProject(clientId, projectId);
        }

        return alerts.markAllRead(clientId, projectId, OffsetDateTime.now());
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
    public AlertSettingsView getSettings(UUID clientId, UUID projectId) {

        findOwnedProject(clientId, projectId);

        return settingsView(projectId);
    }


    /**
     * Sets prompted=true (the one-time popup is answered either way). Turning alerts on also
     * extracts topics when there are none and runs a backfill scan; if the Python service is
     * unavailable the saved setting stays and AlertMatcherUnavailableException is thrown.
     */
    public AlertSettingsView updateSettings(UUID clientId, UUID projectId, boolean enabled) {

        boolean turnedOn = Boolean.TRUE.equals(transactions.execute(tx -> {
            findOwnedProject(clientId, projectId);
            ProjectAlertSettings row = findOrCreateSettings(projectId);
            boolean wasEnabled = row.isEnabled();
            row.setEnabled(enabled);
            row.setPrompted(true);
            row.touch();
            return enabled && !wasEnabled;
        }));

        if (turnedOn) {
            boolean hasTopics = Boolean.TRUE.equals(transactions.execute(
                    tx -> topics.existsByProjectIdAndRemovedFalse(projectId)
            ));
            if (!hasTopics) {
                refresh(projectId);
            }
            scan(projectId, properties.manualMax());
        }

        return readSettings(projectId);
    }


    public AlertSettingsView refreshTopics(UUID clientId, UUID projectId) {

        transactions.executeWithoutResult(tx -> findOwnedProject(clientId, projectId));
        refresh(projectId);

        return readSettings(projectId);
    }


    @Transactional
    public AlertTopicView addTopic(UUID clientId, UUID projectId, String label) {

        findOwnedProject(clientId, projectId);
        String cleaned = clean(label, AlertTopic.MAX_LABEL);

        // Adding a label the project already follows returns that topic instead of a duplicate.
        for (AlertTopic existing : topics.findAllByProjectIdAndRemovedFalseOrderByCreatedAtAscIdAsc(projectId)) {
            if (existing.getLabel().equalsIgnoreCase(cleaned)) {
                return AlertTopicView.from(existing);
            }
        }

        AlertTopic topic = topics.save(
                new AlertTopic(projectId, cleaned, cleaned, AlertTopicSource.USER)
        );
        return AlertTopicView.from(topic);
    }


    @Transactional
    public AlertTopicView renameTopic(UUID clientId, UUID projectId, Long topicId, String label) {

        findOwnedProject(clientId, projectId);
        AlertTopic topic = findTopic(projectId, topicId);

        String cleaned = clean(label, AlertTopic.MAX_LABEL);
        topic.setLabel(cleaned);
        topic.setQuery(cleaned);
        topic.setSource(AlertTopicSource.USER);

        return AlertTopicView.from(topic);
    }


    // AUTO topics are only marked removed, so a refresh never re-creates them; USER topics are deleted.
    @Transactional
    public void deleteTopic(UUID clientId, UUID projectId, Long topicId) {

        findOwnedProject(clientId, projectId);
        AlertTopic topic = findTopic(projectId, topicId);

        if (topic.getSource() == AlertTopicSource.AUTO) {
            topic.setRemoved(true);
        } else {
            topics.delete(topic);
        }
    }


    // Scans

    // "Check now": works even when alerts are off.
    public ScanResult scanProject(UUID clientId, UUID projectId) {

        transactions.executeWithoutResult(tx -> findOwnedProject(clientId, projectId));

        return scan(projectId, properties.manualMax());
    }


    /**
     * The scheduled scan of every enabled project: refreshes topics when the project has newer
     * questions, then adds up to app.alerts.max-per-scan alerts. Never throws.
     */
    public void scanEnabledProjects() {

        List<UUID> projectIds;
        try {
            projectIds = transactions.execute(tx -> settings.findEnabledProjectIds());
        } catch (RuntimeException exception) {
            log.warn("Alert scan skipped: could not list enabled projects", exception);
            return;
        }

        for (UUID projectId : projectIds) {
            try {
                if (hasNewQuestions(projectId)) {
                    refresh(projectId);
                }
                ScanResult result = scan(projectId, properties.maxPerScan());
                if (result.created() > 0) {
                    log.info("Alert scan created {} alert(s) for project {}", result.created(), projectId);
                }
            } catch (AlertMatcherUnavailableException exception) {
                // The Python service is down: skip this round, the next one retries.
                log.warn("Alert scan skipped: {}", exception.getMessage());
                return;
            } catch (RuntimeException exception) {
                log.error("Alert scan failed for project {}", projectId, exception);
            }
        }
    }


    private boolean hasNewQuestions(UUID projectId) {

        return Boolean.TRUE.equals(transactions.execute(tx -> {
            OffsetDateTime latest = topics.findLatestPromptAt(projectId);
            OffsetDateTime refreshed = settings.findById(projectId)
                    .map(ProjectAlertSettings::getTopicsRefreshedAt)
                    .orElse(null);
            return latest != null && (refreshed == null || latest.isAfter(refreshed));
        }));
    }


    private record RefreshInput(List<String> questions, List<String> labels) {
    }

    // Extracts topics from the project's questions and adds the new labels as AUTO topics.
    private void refresh(UUID projectId) {

        // Taken before the call, so questions asked meanwhile trigger the next refresh.
        OffsetDateTime refreshedAt = OffsetDateTime.now();

        RefreshInput input = transactions.execute(tx -> new RefreshInput(
                topics.findProjectPrompts(projectId, Limit.of(MAX_QUESTIONS))
                        .stream()
                        .map(String::trim)
                        .filter(prompt -> !prompt.isEmpty())
                        .map(prompt -> truncate(prompt, MAX_QUESTION_CHARS))
                        .toList(),
                topics.findAllByProjectIdOrderByCreatedAtAscIdAsc(projectId)
                        .stream()
                        .map(AlertTopic::getLabel)
                        .toList()
        ));

        if (input.questions().isEmpty()) {
            return;
        }

        List<String> recentLabels = input.labels().subList(
                Math.max(0, input.labels().size() - MAX_EXISTING_LABELS),
                input.labels().size()
        );
        List<TopicSuggestion> suggestions = matcher.topics(input.questions(), recentLabels);

        transactions.executeWithoutResult(tx -> {
            // Removed labels count too, so they never come back.
            Set<String> known = new HashSet<>();
            for (AlertTopic topic : topics.findAllByProjectIdOrderByCreatedAtAscIdAsc(projectId)) {
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
                topics.save(new AlertTopic(projectId, label, query, AlertTopicSource.AUTO));
            }

            ProjectAlertSettings row = findOrCreateSettings(projectId);
            row.setTopicsRefreshedAt(refreshedAt);
        });
    }


    private record ScanInput(UUID clientId, Map<Long, AlertTopic> topics, List<String> excluded) {
    }

    // Matches the project's topics against the update feed and stores up to `limit` new alerts.
    private ScanResult scan(UUID projectId, int limit) {

        ScanInput input = transactions.execute(tx -> {
            Project project = projects.findById(projectId).orElse(null);
            if (project == null) {
                return null;
            }
            Map<Long, AlertTopic> active = topics
                    .findAllByProjectIdAndRemovedFalseOrderByCreatedAtAscIdAsc(projectId)
                    .stream()
                    .limit(MAX_MATCH_TOPICS)
                    .collect(Collectors.toMap(
                            AlertTopic::getId,
                            Function.identity(),
                            (first, second) -> first,
                            LinkedHashMap::new
                    ));
            return new ScanInput(project.getClientId(), active, alerts.findDocumentIds(projectId));
        });

        if (input == null) {
            return new ScanResult(0, NO_MATCHER);
        }
        if (input.topics().isEmpty()) {
            markScanned(projectId);
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
                inserted += insertAlert(input.clientId(), projectId, topic, match);
            }
            markScanned(projectId);
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
    private int insertAlert(UUID clientId, UUID projectId, AlertTopic topic, AlertMatch match) {

        // The topic may have been deleted while the matcher ran; the label snapshot keeps the reason.
        Long topicId = topics.existsById(topic.getId()) ? topic.getId() : null;
        String excerpt = match.excerpt() == null ? "" : truncate(match.excerpt().trim(), MAX_EXCERPT);
        String title = match.title() == null || match.title().isBlank()
                ? match.documentId()
                : match.title().trim();

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("clientId", clientId, Types.OTHER)
                .addValue("projectId", projectId, Types.OTHER)
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


    private void markScanned(UUID projectId) {

        transactions.executeWithoutResult(tx -> {
            ProjectAlertSettings row = findOrCreateSettings(projectId);
            row.setLastScanAt(OffsetDateTime.now());
        });
    }


    private AlertSettingsView readSettings(UUID projectId) {

        return transactions.execute(tx -> settingsView(projectId));
    }


    private AlertSettingsView settingsView(UUID projectId) {

        List<AlertTopicView> active = topics
                .findAllByProjectIdAndRemovedFalseOrderByCreatedAtAscIdAsc(projectId)
                .stream()
                .map(AlertTopicView::from)
                .toList();

        return settings.findById(projectId)
                .map(row -> new AlertSettingsView(
                        projectId,
                        row.isEnabled(),
                        row.isPrompted(),
                        active,
                        row.getLastScanAt()
                ))
                .orElseGet(() -> new AlertSettingsView(projectId, false, false, active, null));
    }


    private ProjectAlertSettings findOrCreateSettings(UUID projectId) {

        return settings.findById(projectId)
                .orElseGet(() -> settings.saveAndFlush(new ProjectAlertSettings(projectId)));
    }


    private Project findOwnedProject(UUID clientId, UUID projectId) {

        return projects
                .findByIdAndClientId(projectId, clientId)
                .orElseThrow(ProjectNotFoundException::new);
    }


    private Alert findVisibleAlert(UUID clientId, Long alertId) {

        return alerts
                .findByIdAndClientId(alertId, clientId)
                .filter(alert -> alert.getDismissedAt() == null)
                .orElseThrow(AlertNotFoundException::new);
    }


    private AlertTopic findTopic(UUID projectId, Long topicId) {

        return topics
                .findByIdAndProjectIdAndRemovedFalse(topicId, projectId)
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
