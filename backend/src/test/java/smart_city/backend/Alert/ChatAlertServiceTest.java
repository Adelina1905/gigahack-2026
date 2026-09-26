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
import smart_city.backend.Alert.dto.TopicSuggestion;
import smart_city.backend.Alert.dto.UnreadCountView;
import smart_city.backend.Alert.exceptions.AlertNotFoundException;
import smart_city.backend.Alert.exceptions.AlertTopicNotFoundException;
import smart_city.backend.Chat.Chat;
import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Chat.ChatService;
import smart_city.backend.Chat.dto.ChatProjectRequest;
import smart_city.backend.Chat.exceptions.ChatNotFoundException;
import smart_city.backend.Project.Project;
import smart_city.backend.Project.ProjectRepository;
import smart_city.backend.Response.ChatResponseMessage;
import smart_city.backend.Response.ResponseRepository;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

// Alerts of a single chat (a conversation outside or inside a project). Same setup as AlertServiceTest.
@EnabledIfEnvironmentVariable(named = "CHAT_TEST_JDBC_URL", matches = "jdbc:postgresql:.*")
@TestPropertySource(properties = "app.alerts.enabled=false")
@Transactional
class ChatAlertServiceTest extends smart_city.backend.IsolatedDatabaseTest {

    @TestConfiguration
    static class Fakes {

        @Bean
        @Primary
        FakeAlertMatcher fakeAlertMatcher() {
            return new FakeAlertMatcher();
        }
    }

    @Autowired private AlertService alertService;
    @Autowired private ChatService chatService;
    @Autowired private FakeAlertMatcher matcher;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private ChatRepository chatRepository;
    @Autowired private ResponseRepository responseRepository;
    @Autowired private AlertRepository alertRepository;
    @Autowired private AlertTopicRepository topicRepository;
    @Autowired private AlertSubscriptionRepository subscriptionRepository;

    private final UUID clientId = UUID.randomUUID();
    private final UUID otherClientId = UUID.randomUUID();
    private UUID projectId;
    private Chat projectChat;
    private Chat chat;
    private AlertScope scope;

    @BeforeEach
    void setUp() {
        matcher.reset();
        projectId = projectRepository.save(new Project(clientId, "Proiect")).getId();
        projectChat = new Chat(clientId, "In project");
        projectChat.setProjectId(projectId);
        projectChat = chatRepository.save(projectChat);
        chat = chatRepository.save(new Chat(clientId, "Loose"));
        scope = AlertScope.chat(chat.getId());
    }

    private void ask(Chat target, String prompt) {
        responseRepository.saveAndFlush(new ChatResponseMessage(target, prompt, "answer"));
    }

    private static FeedDocument doc(String id, String keyword, double score) {
        return new FeedDocument(id, keyword, score);
    }

    // Turns alerts on without the backfill scan that updateSettings runs.
    private void enableDirectly(AlertScope target) {
        alertService.updateSettings(clientId, target, false);
        AlertSubscription row = subscriptionRepository.findByScope(target).orElseThrow();
        row.setEnabled(true);
        subscriptionRepository.saveAndFlush(row);
    }

    @Test
    void settingsDefaultToOffWithoutARow() {
        AlertSettingsView view = alertService.getSettings(clientId, scope);

        assertThat(view).isEqualTo(new AlertSettingsView(null, chat.getId(), false, false, List.of(), null));
        assertThat(subscriptionRepository.findByChatId(chat.getId())).isEmpty();
    }

    @Test
    void refreshUsesOnlyThatChatsQuestions() {
        ask(projectChat, "Întrebare din proiect");
        ask(chat, "Când se repară drumul?");
        responseRepository.saveAndFlush(new ChatResponseMessage(chat, null, "no prompt"));
        ask(chat, "Cât costă abonamentul?");
        matcher.suggest(new TopicSuggestion("Transport public", "abonament transport"));

        AlertSettingsView view = alertService.refreshTopics(clientId, scope);

        assertThat(matcher.topicsCalls.getFirst().questions())
                .containsExactly("Cât costă abonamentul?", "Când se repară drumul?");
        assertThat(view.chatId()).isEqualTo(chat.getId());
        assertThat(view.projectId()).isNull();
        assertThat(view.topics()).extracting(AlertTopicView::label).containsExactly("Transport public");
        assertThat(subscriptionRepository.findByChatId(chat.getId()).orElseThrow().getClientId()).isEqualTo(clientId);

        // A chat inside a project has its own questions too, separate from the project's.
        alertService.refreshTopics(clientId, AlertScope.chat(projectChat.getId()));
        assertThat(matcher.topicsCalls.get(1).questions()).containsExactly("Întrebare din proiect");
        assertThat(alertService.getSettings(clientId, AlertScope.project(projectId)).topics()).isEmpty();
    }

    @Test
    void refreshSendsAtMostFiftyRecentQuestions() {
        for (int i = 0; i < 51; i++) {
            ask(chat, "Întrebarea " + i);
        }

        alertService.refreshTopics(clientId, scope);

        List<String> questions = matcher.topicsCalls.getFirst().questions();
        assertThat(questions).hasSize(50);
        assertThat(questions.getFirst()).isEqualTo("Întrebarea 50");
        assertThat(questions).doesNotContain("Întrebarea 0");
    }

    @Test
    void enablingBackfillsChatAlerts() {
        ask(chat, "Unde găsesc orarul transportului?");
        matcher.suggest(new TopicSuggestion("Transport", "orar transport"));
        matcher.feed(
                doc("d1", "transport", 0.9),
                doc("d2", "transport", 0.8),
                doc("d3", "transport", 0.7),
                doc("d4", "transport", 0.6)
        );

        AlertSettingsView on = alertService.updateSettings(clientId, scope, true);

        assertThat(on.enabled()).isTrue();
        assertThat(on.prompted()).isTrue();
        assertThat(on.lastScanAt()).isNotNull();
        assertThat(matcher.matchCalls.getFirst().limit()).isEqualTo(3);
        List<AlertView> alerts = alertService.getAlerts(clientId, null, chat.getId(), false, 50);
        assertThat(alerts).extracting(AlertView::documentId).containsExactlyInAnyOrder("d1", "d2", "d3");
        assertThat(alerts).allSatisfy(alert -> {
            assertThat(alert.chatId()).isEqualTo(chat.getId());
            assertThat(alert.projectId()).isNull();
            assertThat(alert.topicLabel()).isEqualTo("Transport");
        });
        assertThat(alertService.getAlerts(clientId, projectId, null, false, 50)).isEmpty();
    }

    @Test
    void theSameDocumentCanAlertAProjectAndAChat() {
        alertService.addTopic(clientId, scope, "transport");
        alertService.addTopic(clientId, AlertScope.project(projectId), "transport");
        matcher.feed(doc("d1", "transport", 0.9));

        alertService.scanNow(clientId, scope);
        alertService.scanNow(clientId, AlertScope.project(projectId));

        assertThat(alertService.getAlerts(clientId, null, null, false, 50))
                .extracting(AlertView::documentId).containsExactly("d1", "d1");
    }

    @Test
    void scheduledScanCoversEnabledProjectsAndChats() {
        enableDirectly(scope);
        enableDirectly(AlertScope.project(projectId));
        alertService.addTopic(clientId, scope, "transport");
        alertService.addTopic(clientId, AlertScope.project(projectId), "parcare");
        Chat disabled = chatRepository.save(new Chat(clientId, "Off"));
        alertService.addTopic(clientId, AlertScope.chat(disabled.getId()), "transport");
        matcher.feed(
                doc("t1", "transport", 0.9),
                doc("t2", "transport", 0.8),
                doc("t3", "transport", 0.7),
                doc("p1", "parcare", 0.9)
        );

        alertService.scanEnabledSubscriptions();

        assertThat(matcher.matchCalls).hasSize(2);
        assertThat(matcher.matchCalls).allSatisfy(call -> assertThat(call.limit()).isEqualTo(2));
        assertThat(alertService.getAlerts(clientId, null, chat.getId(), false, 50))
                .extracting(AlertView::documentId).containsExactlyInAnyOrder("t1", "t2");
        assertThat(alertService.getAlerts(clientId, projectId, null, false, 50))
                .extracting(AlertView::documentId).containsExactly("p1");
        assertThat(alertService.getAlerts(clientId, null, disabled.getId(), false, 50)).isEmpty();
    }

    @Test
    void scheduledScanRefreshesChatTopicsFromNewQuestions() {
        enableDirectly(scope);
        ask(chat, "Cum plătesc impozitul?");
        matcher.suggest(new TopicSuggestion("Impozite", "impozit"));

        alertService.scanEnabledSubscriptions();
        alertService.scanEnabledSubscriptions();

        assertThat(matcher.topicsCalls).hasSize(1);
        assertThat(alertService.getSettings(clientId, scope).topics())
                .extracting(AlertTopicView::label).containsExactly("Impozite");

        // A question in another chat is not new for this one.
        ask(projectChat, "Altă întrebare");
        alertService.scanEnabledSubscriptions();
        assertThat(matcher.topicsCalls).hasSize(1);

        ask(chat, "Și termenul?");
        alertService.scanEnabledSubscriptions();
        assertThat(matcher.topicsCalls).hasSize(2);
    }

    @Test
    void countsUnreadByChatAndMarksAllReadByChat() {
        Chat second = chatRepository.save(new Chat(clientId, "Second"));
        alertService.addTopic(clientId, scope, "transport");
        alertService.addTopic(clientId, AlertScope.chat(second.getId()), "transport");
        alertService.addTopic(clientId, AlertScope.project(projectId), "parcare");
        matcher.feed(doc("t1", "transport", 0.9), doc("t2", "transport", 0.8), doc("p1", "parcare", 0.9));
        alertService.scanNow(clientId, scope);
        alertService.scanNow(clientId, AlertScope.chat(second.getId()));
        alertService.scanNow(clientId, AlertScope.project(projectId));

        UnreadCountView counts = alertService.getUnreadCount(clientId);
        assertThat(counts.total()).isEqualTo(5);
        assertThat(counts.byProject()).isEqualTo(Map.of(projectId, 1L));
        assertThat(counts.byChat()).isEqualTo(Map.of(chat.getId(), 2L, second.getId(), 2L));

        assertThat(alertService.markAllRead(clientId, null, chat.getId())).isEqualTo(2);
        UnreadCountView after = alertService.getUnreadCount(clientId);
        assertThat(after.byChat()).isEqualTo(Map.of(second.getId(), 2L));
        assertThat(after.byProject()).isEqualTo(Map.of(projectId, 1L));
        assertThat(alertService.getAlerts(clientId, null, chat.getId(), true, 50)).isEmpty();

        assertThat(alertService.markAllRead(clientId, null, null)).isEqualTo(3);
        assertThat(alertService.getUnreadCount(clientId).total()).isZero();
    }

    @Test
    void notRelevantRaisesTheChatTopicThreshold() {
        AlertTopicView topic = alertService.addTopic(clientId, scope, "transport");
        matcher.feed(doc("d1", "transport", 0.62));
        alertService.scanNow(clientId, scope);
        Long alertId = alertService.getAlerts(clientId, null, chat.getId(), false, 50).getFirst().id();

        alertService.dismissNotRelevant(clientId, alertId);

        assertThat(alertService.getAlerts(clientId, null, chat.getId(), false, 50)).isEmpty();
        assertThat(topicRepository.findById(topic.id()).orElseThrow().getMinScore())
                .isCloseTo(0.63, org.assertj.core.data.Offset.offset(1e-9));
    }

    @Test
    void deletingAChatDeletesItsSubscriptionTopicsAndAlerts() {
        AlertTopicView topic = alertService.addTopic(clientId, scope, "transport");
        matcher.feed(doc("d1", "transport", 0.9));
        alertService.scanNow(clientId, scope);
        Long alertId = alertService.getAlerts(clientId, null, chat.getId(), false, 50).getFirst().id();

        chatService.deleteChat(clientId, chat.getId());
        chatRepository.flush();

        assertThat(subscriptionRepository.findByChatId(chat.getId())).isEmpty();
        assertThat(topicRepository.existsById(topic.id())).isFalse();
        assertThat(alertRepository.existsById(alertId)).isFalse();
        assertThat(alertService.getUnreadCount(clientId).total()).isZero();
    }

    @Test
    void movingAChatIntoAProjectKeepsItsOwnSubscription() {
        ask(chat, "Transport public");
        alertService.addTopic(clientId, scope, "transport");
        enableDirectly(scope);
        matcher.feed(doc("d1", "transport", 0.9));

        chatService.moveChat(clientId, chat.getId(), new ChatProjectRequest(projectId));
        chatRepository.flush();

        AlertSettingsView view = alertService.getSettings(clientId, scope);
        assertThat(view.enabled()).isTrue();
        assertThat(view.topics()).extracting(AlertTopicView::label).containsExactly("transport");

        alertService.scanEnabledSubscriptions();

        AlertView alert = alertService.getAlerts(clientId, null, chat.getId(), false, 50).getFirst();
        assertThat(alert.chatId()).isEqualTo(chat.getId());
        assertThat(alert.projectId()).isNull();

        chatService.moveChat(clientId, chat.getId(), new ChatProjectRequest(null));
        chatRepository.flush();
        assertThat(alertService.getSettings(clientId, scope).enabled()).isTrue();
        assertThat(alertService.getAlerts(clientId, null, chat.getId(), false, 50)).hasSize(1);
    }

    @Test
    void deletingAProjectKeepsItsChatsSubscriptions() {
        AlertScope projectChatScope = AlertScope.chat(projectChat.getId());
        alertService.addTopic(clientId, projectChatScope, "transport");
        alertService.addTopic(clientId, AlertScope.project(projectId), "transport");

        projectRepository.deleteById(projectId);
        projectRepository.flush();

        assertThat(subscriptionRepository.findByProjectId(projectId)).isEmpty();
        assertThat(alertService.getSettings(clientId, projectChatScope).topics())
                .extracting(AlertTopicView::label).containsExactly("transport");
    }

    @Test
    void anotherClientsChatIsNotFound() {
        AlertTopicView topic = alertService.addTopic(clientId, scope, "transport");
        matcher.feed(doc("d1", "transport", 0.9));
        alertService.scanNow(clientId, scope);
        Long alertId = alertService.getAlerts(clientId, null, chat.getId(), false, 50).getFirst().id();
        int matchCalls = matcher.matchCalls.size();

        assertThat(alertService.getAlerts(otherClientId, null, null, false, 50)).isEmpty();
        assertThat(alertService.getUnreadCount(otherClientId).byChat()).isEmpty();
        assertThatThrownBy(() -> alertService.getAlerts(otherClientId, null, chat.getId(), false, 50))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> alertService.markAllRead(otherClientId, null, chat.getId()))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> alertService.markRead(otherClientId, alertId))
                .isInstanceOf(AlertNotFoundException.class);
        assertThatThrownBy(() -> alertService.getSettings(otherClientId, scope))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> alertService.updateSettings(otherClientId, scope, true))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> alertService.refreshTopics(otherClientId, scope))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> alertService.addTopic(otherClientId, scope, "X"))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> alertService.renameTopic(otherClientId, scope, topic.id(), "X"))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> alertService.deleteTopic(otherClientId, scope, topic.id()))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> alertService.scanNow(otherClientId, scope))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> alertService.getSettings(clientId, AlertScope.chat(UUID.randomUUID())))
                .isInstanceOf(ChatNotFoundException.class);
        assertThat(matcher.matchCalls).hasSize(matchCalls);

        // A chat topic is not reachable through another scope.
        assertThatThrownBy(() -> alertService.renameTopic(clientId, AlertScope.project(projectId), topic.id(), "X"))
                .isInstanceOf(AlertTopicNotFoundException.class);
    }
}
