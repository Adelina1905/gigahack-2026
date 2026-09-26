package smart_city.backend.Project;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;

import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Chat.ChatService;
import smart_city.backend.Chat.dto.ChatCreateRequest;
import smart_city.backend.Chat.dto.ChatProjectRequest;
import smart_city.backend.Chat.dto.ChatResponse;
import smart_city.backend.Chat.exceptions.ChatNotFoundException;
import smart_city.backend.Project.dto.ProjectCreateRequest;
import smart_city.backend.Project.dto.ProjectResponse;
import smart_city.backend.Project.dto.ProjectUpdateRequest;
import smart_city.backend.Project.exceptions.ProjectNotFoundException;

import java.time.OffsetDateTime;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

// Each test runs in a transaction that is rolled back.
@EnabledIfEnvironmentVariable(named = "CHAT_TEST_JDBC_URL", matches = "jdbc:postgresql:.*")
@Transactional
class ProjectServiceTest extends smart_city.backend.IsolatedDatabaseTest {

    @Autowired
    private ProjectService projectService;

    @Autowired
    private ChatService chatService;

    @Autowired
    private ChatRepository chatRepository;

    @Autowired
    private ProjectRepository projectRepository;

    private final UUID clientId = UUID.randomUUID();
    private final UUID otherClientId = UUID.randomUUID();

    private ProjectResponse project(String name) {
        return projectService.createProject(clientId, new ProjectCreateRequest(name));
    }

    private ChatResponse chat(String name, UUID projectId, OffsetDateTime updatedAt) {
        ChatResponse created = chatService.createChat(
                clientId,
                new ChatCreateRequest(name, null, projectId)
        );
        var row = chatRepository.findById(created.id()).orElseThrow();
        row.setUpdatedAt(updatedAt);
        chatRepository.flush();
        return ChatResponse.from(row);
    }

    @Test
    void createsAndListsProjectsWithTheirChatsNewestFirst() {
        OffsetDateTime now = OffsetDateTime.now();
        ProjectResponse created = project("  Taxe locale  ");
        ProjectResponse empty = project("Transport");
        projectRepository.findById(empty.id()).orElseThrow().setUpdatedAt(now.minusDays(1));

        ChatResponse older = chat("Older", created.id(), now.minusHours(2));
        ChatResponse newer = chat("Newer", created.id(), now.minusHours(1));
        chat("Loose", null, now);

        assertThat(created.name()).isEqualTo("Taxe locale");
        assertThat(created.chats()).isEmpty();

        var projects = projectService.getAllProjects(clientId);

        assertThat(projects).extracting(ProjectResponse::id).containsExactly(created.id(), empty.id());
        assertThat(projects.get(0).chats()).extracting(ChatResponse::id).containsExactly(newer.id(), older.id());
        assertThat(projects.get(0).chats()).allSatisfy(c -> assertThat(c.projectId()).isEqualTo(created.id()));
        assertThat(projects.get(1).chats()).isEmpty();
        assertThat(projectService.getProject(clientId, created.id()).chats())
                .extracting(ChatResponse::id).containsExactly(newer.id(), older.id());
        assertThat(chatService.getAllChats(clientId)).hasSize(3);
    }

    @Test
    void renamesAndBumpsUpdatedAt() {
        ProjectResponse created = project("Old");
        OffsetDateTime past = OffsetDateTime.now().minusDays(1);
        projectRepository.findById(created.id()).orElseThrow().setUpdatedAt(past);

        ProjectResponse renamed = projectService.updateProject(
                clientId, created.id(), new ProjectUpdateRequest("  New  "));

        assertThat(renamed.name()).isEqualTo("New");
        assertThat(renamed.updatedAt()).isAfter(past);
    }

    @Test
    void createsChatInsideProjectAndBumpsIt() {
        ProjectResponse created = project("P");
        OffsetDateTime past = OffsetDateTime.now().minusDays(1);
        projectRepository.findById(created.id()).orElseThrow().setUpdatedAt(past);

        ChatResponse inside = chatService.createChat(
                clientId, new ChatCreateRequest("Hi", null, created.id()));

        assertThat(inside.projectId()).isEqualTo(created.id());
        assertThat(projectService.getProject(clientId, created.id()).updatedAt()).isAfter(past);
    }

    @Test
    void movesChatIntoAndOutOfProject() {
        ProjectResponse created = project("P");
        ChatResponse loose = chat("Loose", null, OffsetDateTime.now());
        OffsetDateTime past = OffsetDateTime.now().minusDays(1);
        projectRepository.findById(created.id()).orElseThrow().setUpdatedAt(past);

        ChatResponse moved = chatService.moveChat(clientId, loose.id(), new ChatProjectRequest(created.id()));

        assertThat(moved.projectId()).isEqualTo(created.id());
        ProjectResponse reloaded = projectService.getProject(clientId, created.id());
        assertThat(reloaded.chats()).extracting(ChatResponse::id).containsExactly(loose.id());
        assertThat(reloaded.updatedAt()).isAfter(past);

        ChatResponse out = chatService.moveChat(clientId, loose.id(), new ChatProjectRequest(null));

        assertThat(out.projectId()).isNull();
        assertThat(projectService.getProject(clientId, created.id()).chats()).isEmpty();
    }

    @Test
    void deletingProjectKeepsItsChats() {
        ProjectResponse created = project("P");
        ChatResponse inside = chat("Inside", created.id(), OffsetDateTime.now());

        projectService.deleteProject(clientId, created.id());

        assertThat(projectService.getAllProjects(clientId)).isEmpty();
        assertThat(chatService.getChat(clientId, inside.id()).projectId()).isNull();
        assertThatThrownBy(() -> projectService.getProject(clientId, created.id()))
                .isInstanceOf(ProjectNotFoundException.class);
    }

    @Test
    void anotherClientsProjectOrChatIsNotFound() {
        ProjectResponse created = project("P");
        ChatResponse mine = chat("Mine", null, OffsetDateTime.now());
        ChatResponse theirs = chatService.createChat(otherClientId, new ChatCreateRequest("Theirs"));
        UUID id = created.id();

        assertThat(projectService.getAllProjects(otherClientId)).isEmpty();
        assertThatThrownBy(() -> projectService.getProject(otherClientId, id))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> projectService.updateProject(otherClientId, id, new ProjectUpdateRequest("X")))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> projectService.deleteProject(otherClientId, id))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> chatService.createChat(otherClientId, new ChatCreateRequest("C", null, id)))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThatThrownBy(() -> chatService.moveChat(otherClientId, mine.id(), new ChatProjectRequest(null)))
                .isInstanceOf(ChatNotFoundException.class);
        assertThatThrownBy(() -> chatService.moveChat(otherClientId, theirs.id(), new ChatProjectRequest(id)))
                .isInstanceOf(ProjectNotFoundException.class);
        assertThat(chatService.getChat(clientId, mine.id()).projectId()).isNull();
    }
}
