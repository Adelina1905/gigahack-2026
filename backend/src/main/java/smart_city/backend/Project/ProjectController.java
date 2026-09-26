package smart_city.backend.Project;

import jakarta.validation.Valid;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import smart_city.backend.Chat.AnonymousClientCookie;
import smart_city.backend.Project.dto.ProjectCreateRequest;
import smart_city.backend.Project.dto.ProjectResponse;
import smart_city.backend.Project.dto.ProjectUpdateRequest;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/projects")
public class ProjectController {

    private final ProjectService projectService;
    private final AnonymousClientCookie anonymousClientCookie;

    public ProjectController(
            ProjectService projectService,
            AnonymousClientCookie anonymousClientCookie
    ) {
        this.projectService = projectService;
        this.anonymousClientCookie = anonymousClientCookie;
    }


    @GetMapping
    public List<ProjectResponse> getAllProjects(
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return projectService.getAllProjects(
                anonymousClientCookie.resolve(clientCookie, response)
        );
    }


    @GetMapping("/{projectId}")
    public ProjectResponse getProject(
            @PathVariable UUID projectId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return projectService.getProject(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId
        );
    }


    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProjectResponse createProject(
            @Valid @RequestBody ProjectCreateRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return projectService.createProject(
                anonymousClientCookie.resolve(clientCookie, response),
                request
        );
    }


    @PatchMapping("/{projectId}")
    public ProjectResponse updateProject(
            @PathVariable UUID projectId,
            @Valid @RequestBody ProjectUpdateRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return projectService.updateProject(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId,
                request
        );
    }


    @DeleteMapping("/{projectId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteProject(
            @PathVariable UUID projectId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        projectService.deleteProject(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId
        );
    }
}
