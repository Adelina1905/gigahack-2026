package smart_city.backend.Alert;

import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import smart_city.backend.Alert.dto.AlertSettingsRequest;
import smart_city.backend.Alert.dto.AlertSettingsView;
import smart_city.backend.Alert.dto.AlertTopicRequest;
import smart_city.backend.Alert.dto.AlertTopicView;
import smart_city.backend.Alert.dto.ScanResult;
import smart_city.backend.Chat.AnonymousClientCookie;

import java.util.UUID;

// A project's alert settings, topics and manual scan.
@RestController
@RequestMapping("/api/projects/{projectId}")
public class ProjectAlertController {

    private final AlertService alertService;
    private final AnonymousClientCookie anonymousClientCookie;

    public ProjectAlertController(
            AlertService alertService,
            AnonymousClientCookie anonymousClientCookie
    ) {
        this.alertService = alertService;
        this.anonymousClientCookie = anonymousClientCookie;
    }


    @GetMapping("/alert-settings")
    public AlertSettingsView getSettings(
            @PathVariable UUID projectId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.getSettings(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId
        );
    }


    @PutMapping("/alert-settings")
    public AlertSettingsView updateSettings(
            @PathVariable UUID projectId,
            @Valid @RequestBody AlertSettingsRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.updateSettings(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId,
                request.enabled()
        );
    }


    @PostMapping("/alert-topics/refresh")
    public AlertSettingsView refreshTopics(
            @PathVariable UUID projectId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.refreshTopics(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId
        );
    }


    @PostMapping("/alert-topics")
    @ResponseStatus(HttpStatus.CREATED)
    public AlertTopicView addTopic(
            @PathVariable UUID projectId,
            @Valid @RequestBody AlertTopicRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.addTopic(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId,
                request.label()
        );
    }


    @PatchMapping("/alert-topics/{topicId}")
    public AlertTopicView renameTopic(
            @PathVariable UUID projectId,
            @PathVariable Long topicId,
            @Valid @RequestBody AlertTopicRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.renameTopic(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId,
                topicId,
                request.label()
        );
    }


    @DeleteMapping("/alert-topics/{topicId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteTopic(
            @PathVariable UUID projectId,
            @PathVariable Long topicId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        alertService.deleteTopic(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId,
                topicId
        );
    }


    @PostMapping("/alerts/scan")
    public ScanResult scan(
            @PathVariable UUID projectId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.scanProject(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId
        );
    }
}
