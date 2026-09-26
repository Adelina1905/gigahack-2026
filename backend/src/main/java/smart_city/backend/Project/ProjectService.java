package smart_city.backend.Project;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import smart_city.backend.Chat.Chat;
import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Chat.dto.ChatResponse;
import smart_city.backend.Project.dto.ProjectCreateRequest;
import smart_city.backend.Project.dto.ProjectResponse;
import smart_city.backend.Project.dto.ProjectUpdateRequest;
import smart_city.backend.Project.exceptions.ProjectNotFoundException;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class ProjectService {

    private final ProjectRepository projectRepository;
    private final ChatRepository chatRepository;

    public ProjectService(
            ProjectRepository projectRepository,
            ChatRepository chatRepository
    ) {
        this.projectRepository = projectRepository;
        this.chatRepository = chatRepository;
    }


    @Transactional(readOnly = true)
    public List<ProjectResponse> getAllProjects(UUID clientId) {

        // One query for all grouped chats; groupingBy keeps their updatedAt order.
        Map<UUID, List<ChatResponse>> chatsByProject = chatRepository
                .findAllByClientIdAndProjectIdIsNotNullOrderByUpdatedAtDesc(clientId)
                .stream()
                .collect(Collectors.groupingBy(
                        Chat::getProjectId,
                        Collectors.mapping(ChatResponse::from, Collectors.toList())
                ));

        return projectRepository
                .findAllByClientIdOrderByUpdatedAtDesc(clientId)
                .stream()
                .map(project -> ProjectResponse.from(
                        project,
                        chatsByProject.getOrDefault(project.getId(), List.of())
                ))
                .toList();
    }


    @Transactional(readOnly = true)
    public ProjectResponse getProject(
            UUID clientId,
            UUID projectId
    ) {

        return withChats(
                findOwnedProject(clientId, projectId)
        );
    }


    @Transactional
    public ProjectResponse createProject(
            UUID clientId,
            ProjectCreateRequest request
    ) {

        Project project = projectRepository.save(
                new Project(clientId, request.name().trim())
        );

        return ProjectResponse.from(project, List.of());
    }


    @Transactional
    public ProjectResponse updateProject(
            UUID clientId,
            UUID projectId,
            ProjectUpdateRequest request
    ) {

        Project project = findOwnedProject(
                clientId,
                projectId
        );

        project.setName(
                request.name().trim()
        );
        project.touch();

        return withChats(project);
    }


    @Transactional
    public void deleteProject(
            UUID clientId,
            UUID projectId
    ) {

        Project project = findOwnedProject(
                clientId,
                projectId
        );

        // Chats survive and return to the ungrouped list.
        chatRepository.detachFromProject(project.getId());
        projectRepository.deleteById(project.getId());
    }


    private ProjectResponse withChats(Project project) {

        List<ChatResponse> chats = chatRepository
                .findAllByClientIdAndProjectIdOrderByUpdatedAtDesc(
                        project.getClientId(),
                        project.getId()
                )
                .stream()
                .map(ChatResponse::from)
                .toList();

        return ProjectResponse.from(project, chats);
    }


    private Project findOwnedProject(
            UUID clientId,
            UUID projectId
    ) {

        return projectRepository
                .findByIdAndClientId(
                        projectId,
                        clientId
                )
                .orElseThrow(
                        ProjectNotFoundException::new
                );
    }
}
