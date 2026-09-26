package smart_city.backend.Alert;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.TestPropertySource;
import org.springframework.transaction.annotation.Transactional;

import smart_city.backend.Alert.FakeAlertMatcher.FeedDocument;
import smart_city.backend.Alert.dto.AlertSettingsView;
import smart_city.backend.Alert.dto.AlertTopicView;
import smart_city.backend.Alert.dto.AlertView;
import smart_city.backend.Alert.dto.MatchTopic;
import smart_city.backend.Alert.dto.ScanResult;
import smart_city.backend.Alert.dto.TopicSuggestion;
import smart_city.backend.Alert.dto.UnreadCountView;
import smart_city.backend.Alert.exceptions.AlertMatcherUnavailableException;
import smart_city.backend.Alert.exceptions.AlertNotFoundException;
import smart_city.backend.Alert.exceptions.AlertTopicNotFoundException;
import smart_city.backend.Chat.Chat;
import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Project.Project;
import smart_city.backend.Project.ProjectRepository;
import smart_city.backend.Project.exceptions.ProjectNotFoundException;
import smart_city.backend.Response.ChatResponseMessage;
import smart_city.backend.Response.ResponseRepository;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

// Each test runs in a transaction that is rolled back; the service's TransactionTemplate joins it.
// The scheduled task is off so it never scans concurrently; the tests call the scan directly.
@EnabledIfEnvironmentVariable(named = "CHAT_TEST_JDBC_URL", matches = "jdbc:postgresql:.*")
@TestPropertySource(properties = "app.alerts.enabled=false")
@Transactional
class AlertServiceTest extends smart_city.backend.IsolatedDatabaseTest {

    @TestConfiguration
    static class Fakes {

        @Bean
        @Primary
        FakeAlertMatcher fakeAlertMatcher() {
            return new FakeAlertMatcher();
        }
    }

    @Autowired private AlertService alertService;
    @Autowired private FakeAlertMatcher matcher;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private ChatRepository chatRepository;
    @Autowired private ResponseRepository responseRepository;
    @Autowired private AlertTopicRepository topicRepository;
    @Autowired private ProjectAlertSettingsRepository settingsRepository;

    private final UUID clientId = UUID.randomUUID();
    private final UUID otherClientId = UUID.randomUUID();
    private UUID projectId;
    private Chat chat;

    @BeforeEach
    void setUp() {
        matcher.reset();
        projectId = project();
        chat = new Chat(clientId, "Chat");
        chat.setProjectId(projectId);
        chat = chatRepository.save(chat);
    }

    private UUID project() {
        return projectRepository.save(new Project(clientId, "Proiect")).getId();
    }

    private void ask(String prompt) {
        responseRepository.saveAndFlush(new ChatResponseMessage(chat, prompt, "answer"));
    }

    private AlertTopicView userTopic(UUID project, String label) {
        return alertService.addTopic(clientId, project, label);
    }

    private static FeedDocument doc(String id, String keyword, double score) {
        return new FeedDocument(id, keyword, score);
    }

    private void enableDirectly(UUID project) {
        ProjectAlertSettings row = new ProjectAlertSettings(project);
        row.setEnabled(true);
        row.setPrompted(true);
        settingsRepository.saveAndFlush(row);
    }

    @Test
    void settingsDefaultToOffWithoutARow() {
        AlertSettingsView view = alertService.getSettings(clientId, projectId);

        assertThat(view).isEqualTo(new AlertSettingsView(projectId, false, false, List.of(), null));
        assertThat(settingsRepository.findById(projectId)).isEmpty();
    }

    @Test
    void refreshAddsAutoTopicsAndNeverReAddsRemovedLabels() {
        ask("Când se repară drumul pe strada Ismail?");
        ask("Cât costă abonamentul de transport?");
        matcher.suggest(
                new TopicSuggestion("Reparații drumuri", "reparație drum strada"),
                new TopicSuggestion("Transport public", "abonament transport public")
        );

        AlertSettingsView refreshed = alertService.refreshTopics(clientId, projectId);

        assertThat(matcher.topicsCalls).hasSize(1);
        assertThat(matcher.topicsCalls.getFirst().questions()).containsExactly(
                "Cât costă abonamentul de transport?",
                "Când se repară drumul pe strada Ismail?"
        );
        assertThat(matcher.topicsCalls.getFirst().existingLabels()).isEmpty();
        assertThat(refreshed.topics())
                .extracting(AlertTopicView::label, AlertTopicView::query, AlertTopicView::source)
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple("Reparații drumuri", "reparație drum strada", AlertTopicSource.AUTO),
                        org.assertj.core.groups.Tuple.tuple("Transport public", "abonament transport public", AlertTopicSource.AUTO)
                );
        assertThat(settingsRepository.findById(projectId).orElseThrow().getTopicsRefreshedAt()).isNotNull();

        Long roads = refreshed.topics().getFirst().id();
        alertService.deleteTopic(clientId, projectId, roads);
        matcher.suggest(
                new TopicSuggestion("REPARAȚII DRUMURI", "drum"),
                new TopicSuggestion("transport public", "transport"),
                new TopicSuggestion("Parcări", "parcare")
        );

        AlertSettingsView again = alertService.refreshTopics(clientId, projectId);

        assertThat(matcher.topicsCalls.get(1).existingLabels())
                .containsExactly("Reparații drumuri", "Transport public");
        assertThat(again.topics()).extracting(AlertTopicView::label)
                .containsExactly("Transport public", "Parcări");
        assertThat(topicRepository.findById(roads).orElseThrow().isRemoved()).isTrue();
    }

    @Test
    void refreshWithoutQuestionsDoesNotCallTheService() {
        AlertSettingsView view = alertService.refreshTopics(clientId, projectId);

        assertThat(view.topics()).isEmpty();
        assertThat(matcher.topicsCalls).isEmpty();
    }

    @Test
    void enablingExtractsTopicsRunsABackfillScanAndSetsPrompted() {
        ask("Unde găsesc orarul transportului?");
        matcher.suggest(new TopicSuggestion("Transport", "orar transport"));
        matcher.feed(
                doc("d1", "transport", 0.9),
                doc("d2", "transport", 0.8),
                doc("d3", "transport", 0.7),
                doc("d4", "transport", 0.6),
                doc("d5", "parcare", 0.95)
        );

        AlertSettingsView on = alertService.updateSettings(clientId, projectId, true);

        assertThat(on.enabled()).isTrue();
        assertThat(on.prompted()).isTrue();
        assertThat(on.lastScanAt()).isNotNull();
        assertThat(on.topics()).extracting(AlertTopicView::label).containsExactly("Transport");
        assertThat(matcher.matchCalls).hasSize(1);
        assertThat(matcher.matchCalls.getFirst().limit()).isEqualTo(3);
        List<AlertView> alerts = alertService.getAlerts(clientId, projectId, false, 50);
        assertThat(alerts).extracting(AlertView::documentId).containsExactlyInAnyOrder("d1", "d2", "d3");
        AlertView first = alerts.stream().filter(a -> a.documentId().equals("d1")).findFirst().orElseThrow();
        assertThat(first.topicLabel()).isEqualTo("Transport");
        assertThat(first.topicId()).isEqualTo(on.topics().getFirst().id());
        assertThat(first.title()).isEqualTo("Title d1");
        assertThat(first.publishedDate()).hasToString("2026-09-01");
        assertThat(first.readAt()).isNull();

        // Already on: no second backfill.
        alertService.updateSettings(clientId, projectId, true);
        assertThat(matcher.matchCalls).hasSize(1);

        AlertSettingsView off = alertService.updateSettings(clientId, projectId, false);
        assertThat(off.enabled()).isFalse();
        assertThat(off.prompted()).isTrue();
    }

    @Test
    void declineOnlyMarksPrompted() {
        AlertSettingsView view = alertService.updateSettings(clientId, projectId, false);

        assertThat(view.enabled()).isFalse();
        assertThat(view.prompted()).isTrue();
        assertThat(matcher.topicsCalls).isEmpty();
        assertThat(matcher.matchCalls).isEmpty();
    }

    @Test
    void enablingKeepsTheSettingWhenTheServiceIsDown() {
        ask("Întrebare");
        matcher.setFailing(true);

        assertThatThrownBy(() -> alertService.updateSettings(clientId, projectId, true))
                .isInstanceOf(AlertMatcherUnavailableException.class);

        AlertSettingsView view = alertService.getSettings(clientId, projectId);
        assertThat(view.enabled()).isTrue();
        assertThat(view.prompted()).isTrue();
    }

    @Test
    void scheduledScanAddsAtMostTwoNewAlertsAndExcludesEarlierOnes() {
        enableDirectly(projectId);
        userTopic(projectId, "transport");
        UUID disabled = project();
        userTopic(disabled, "transport");
        matcher.feed(
                doc("d1", "transport", 0.9),
                doc("d2", "transport", 0.8),
                doc("d3", "transport", 0.7),
                doc("d4", "transport", 0.6),
                doc("d5", "transport", 0.5)
        );

        alertService.scanEnabledProjects();
        alertService.scanEnabledProjects();

        assertThat(matcher.matchCalls).hasSize(2);
        assertThat(matcher.matchCalls.get(0).limit()).isEqualTo(2);
        assertThat(matcher.matchCalls.get(0).excludedDocumentIds()).isEmpty();
        assertThat(matcher.matchCalls.get(1).excludedDocumentIds()).containsExactlyInAnyOrder("d1", "d2");
        assertThat(alertService.getAlerts(clientId, projectId, false, 50))
                .extracting(AlertView::documentId).containsExactlyInAnyOrder("d1", "d2", "d3", "d4");
        assertThat(alertService.getAlerts(clientId, disabled, false, 50)).isEmpty();

        alertService.scanEnabledProjects();
        alertService.scanEnabledProjects();

        assertThat(alertService.getAlerts(clientId, projectId, false, 50)).hasSize(5);
        assertThat(matcher.matchCalls.get(3).excludedDocumentIds()).hasSize(5);
        // No questions in the project: the scheduled scan never asked for topics.
        assertThat(matcher.topicsCalls).isEmpty();
    }

    @Test
    void scheduledScanRefreshesTopicsOnlyWhenThereAreNewQuestions() {
        enableDirectly(projectId);
        ask("Cum plătesc impozitul?");
        matcher.suggest(new TopicSuggestion("Impozite", "impozit pe bunuri"));

        alertService.scanEnabledProjects();
        alertService.scanEnabledProjects();

        assertThat(matcher.topicsCalls).hasSize(1);
        assertThat(alertService.getSettings(clientId, projectId).topics())
                .extracting(AlertTopicView::label).containsExactly("Impozite");

        ask("Și termenul de plată?");
        alertService.scanEnabledProjects();

        assertThat(matcher.topicsCalls).hasSize(2);
    }

    @Test
    void scheduledScanSkipsWhenTheServiceIsDown() {
        enableDirectly(projectId);
        userTopic(projectId, "transport");
        matcher.setFailing(true);

        alertService.scanEnabledProjects();

        assertThat(matcher.matchCalls).hasSize(1);
        assertThat(alertService.getAlerts(clientId, projectId, false, 50)).isEmpty();
    }

    @Test
    void manualScanWorksWhenDisabledAndNeverDuplicatesADocument() {
        userTopic(projectId, "transport");
        matcher.feed(doc("d1", "transport", 0.9), doc("d2", "transport", 0.8));

        ScanResult first = alertService.scanProject(clientId, projectId);
        matcher.setIgnoringExclusions(true);
        ScanResult second = alertService.scanProject(clientId, projectId);

        assertThat(first).isEqualTo(new ScanResult(2, "lexical"));
        assertThat(second).isEqualTo(new ScanResult(0, "lexical"));
        assertThat(alertService.getAlerts(clientId, projectId, false, 50)).hasSize(2);
        assertThat(alertService.getSettings(clientId, projectId).lastScanAt()).isNotNull();
    }

    @Test
    void scanWithoutTopicsMatchesNothing() {
        ScanResult result = alertService.scanProject(clientId, projectId);

        assertThat(result).isEqualTo(new ScanResult(0, "none"));
        assertThat(matcher.matchCalls).isEmpty();
    }

    @Test
    void notRelevantHidesTheAlertAndRaisesTheTopicThreshold() {
        AlertTopicView topic = userTopic(projectId, "transport");
        matcher.feed(doc("d1", "transport", 0.62), doc("d2", "transport", 0.61), doc("d3", "transport", 0.5));
        alertService.scanProject(clientId, projectId);
        AlertView dismissed = alertService.getAlerts(clientId, projectId, false, 50).stream()
                .filter(a -> a.documentId().equals("d2")).findFirst().orElseThrow();

        alertService.dismissNotRelevant(clientId, dismissed.id());

        assertThat(alertService.getAlerts(clientId, projectId, false, 50))
                .extracting(AlertView::documentId).containsExactlyInAnyOrder("d1", "d3");
        assertThat(alertService.getUnreadCount(clientId).total()).isEqualTo(2);
        Double minScore = alertService.getSettings(clientId, projectId).topics().getFirst().minScore();
        assertThat(minScore).isCloseTo(0.62, org.assertj.core.data.Offset.offset(1e-9));

        // A second dismissal with a lower score never lowers the threshold.
        AlertView lower = alertService.getAlerts(clientId, projectId, false, 50).stream()
                .filter(a -> a.documentId().equals("d3")).findFirst().orElseThrow();
        alertService.dismissNotRelevant(clientId, lower.id());
        assertThat(topicRepository.findById(topic.id()).orElseThrow().getMinScore())
                .isCloseTo(0.62, org.assertj.core.data.Offset.offset(1e-9));

        alertService.scanProject(clientId, projectId);
        List<MatchTopic> sent = matcher.matchCalls.getLast().topics();
        assertThat(sent).extracting(MatchTopic::minScore).containsExactly(minScore);
        assertThat(matcher.matchCalls.getLast().excludedDocumentIds()).containsExactlyInAnyOrder("d1", "d2", "d3");

        assertThatThrownBy(() -> alertService.markRead(clientId, dismissed.id()))
                .isInstanceOf(AlertNotFoundException.class);
    }

    @Test
    void countsUnreadByProjectAndMarksRead() {
        UUID second = project();
        userTopic(projectId, "transport");
        userTopic(second, "parcare");
        matcher.feed(doc("t1", "transport", 0.9), doc("t2", "transport", 0.8), doc("p1", "parcare", 0.9));
        alertService.scanProject(clientId, projectId);
        alertService.scanProject(clientId, second);

        UnreadCountView counts = alertService.getUnreadCount(clientId);
        assertThat(counts.total()).isEqualTo(3);
        assertThat(counts.byProject()).isEqualTo(Map.of(projectId, 2L, second, 1L));
        assertThat(alertService.getUnreadCount(otherClientId).total()).isZero();

        AlertView one = alertService.getAlerts(clientId, projectId, true, 50).getFirst();
        AlertView read = alertService.markRead(clientId, one.id());
        assertThat(read.readAt()).isNotNull();
        assertThat(alertService.getAlerts(clientId, projectId, true, 50)).hasSize(1);
        assertThat(alertService.getAlerts(clientId, null, false, 50)).hasSize(3);
        assertThat(alertService.getAlerts(clientId, null, false, 1)).hasSize(1);

        assertThat(alertService.markAllRead(clientId, projectId)).isEqualTo(1);
        assertThat(alertService.getUnreadCount(clientId).byProject()).isEqualTo(Map.of(second, 1L));
        assertThat(alertService.markAllRead(clientId, null)).isEqualTo(1);
        assertThat(alertService.getUnreadCount(clientId).total()).isZero();
    }

    @Test
    void topicCrud() {
        AlertTopicView added = alertService.addTopic(clientId, projectId, "  Apă   potabilă ");
        assertThat(added.label()).isEqualTo("Apă potabilă");
        assertThat(added.query()).isEqualTo("Apă potabilă");
        assertThat(added.source()).isEqualTo(AlertTopicSource.USER);
        assertThat(added.minScore()).isNull();
        assertThat(alertService.addTopic(clientId, projectId, "apă potabilă").id()).isEqualTo(added.id());

        AlertTopic auto = topicRepository.save(new AlertTopic(projectId, "Drumuri", "drum", AlertTopicSource.AUTO));
        AlertTopicView renamed = alertService.renameTopic(clientId, projectId, auto.getId(), "Drumuri noi");
        assertThat(renamed).isEqualTo(new AlertTopicView(auto.getId(), "Drumuri noi", "Drumuri noi", AlertTopicSource.USER, null));

        AlertTopic other = topicRepository.save(new AlertTopic(projectId, "Parcări", "parcare", AlertTopicSource.AUTO));
        alertService.deleteTopic(clientId, projectId, other.getId());
        alertService.deleteTopic(clientId, projectId, added.id());

        assertThat(topicRepository.findById(other.getId()).orElseThrow().isRemoved()).isTrue();
        assertThat(topicRepository.findById(added.id())).isEmpty();
        assertThat(alertService.getSettings(clientId, projectId).topics())
                .extracting(AlertTopicView::label).containsExactly("Drumuri noi");

        UUID second = project();
        Long secondTopic = userTopic(second, "Altceva").id();
        assertThatThrownBy(() -> alertService.renameTopic(clientId, projectId, secondTopic, "X"))
                .isInstanceOf(AlertTopicNotFoundException.class);
        assertThatThrownBy(() -> alertService.deleteTopic(clientId, projectId, other.getId()))
                .isInstanceOf(AlertTopicNotFoundException.class);
    }

    @Test
    void anotherClientsProjectOrAlertIsNotFound() {
        userTopic(projectId, "transport");
        matcher.feed(doc("d1", "transport", 0.9));
        alertService.scanProject(clientId, projectId);
        Long alertId = alertService.getAlerts(clientId, projectId, false, 50).getFirst().id();
        Long topicId = alertService.getSettings(clientId, projectId).topics().getFirst().id();
        int matchCalls = matcher.matchCalls.size();

        assertThat(alertService.getAlerts(otherClientId, null, false, 50)).isEmpty();
        assertThatThrownBy(() -> alertService.getAlerts(otherClientId, projectId, false, 50))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> alertService.markRead(otherClientId, alertId))
                .isInstanceOf(AlertNotFoundException.class);
        assertThatThrownBy(() -> alertService.dismissNotRelevant(otherClientId, alertId))
                .isInstanceOf(AlertNotFoundException.class);
        assertThatThrownBy(() -> alertService.markAllRead(otherClientId, projectId))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> alertService.getSettings(otherClientId, projectId))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> alertService.updateSettings(otherClientId, projectId, true))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> alertService.refreshTopics(otherClientId, projectId))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> alertService.addTopic(otherClientId, projectId, "X"))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> alertService.renameTopic(otherClientId, projectId, topicId, "X"))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> alertService.deleteTopic(otherClientId, projectId, topicId))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> alertService.scanProject(otherClientId, projectId))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThat(matcher.matchCalls).hasSize(matchCalls);
    }
}
