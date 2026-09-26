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

// A chat's own alert settings, topics and manual scan (same semantics as ProjectAlertController).
@RestController
@RequestMapping("/api/chats/{chatId}")
public class ChatAlertController {

    private final AlertService alertService;
    private final AnonymousClientCookie anonymousClientCookie;

    public ChatAlertController(
            AlertService alertService,
            AnonymousClientCookie anonymousClientCookie
    ) {
        this.alertService = alertService;
        this.anonymousClientCookie = anonymousClientCookie;
    }


    @GetMapping("/alert-settings")
    public AlertSettingsView getSettings(
            @PathVariable UUID chatId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.getSettings(
                anonymousClientCookie.resolve(clientCookie, response),
                AlertScope.chat(chatId)
        );
    }


    @PutMapping("/alert-settings")
    public AlertSettingsView updateSettings(
            @PathVariable UUID chatId,
            @Valid @RequestBody AlertSettingsRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.updateSettings(
                anonymousClientCookie.resolve(clientCookie, response),
                AlertScope.chat(chatId),
                request.enabled()
        );
    }


    @PostMapping("/alert-topics/refresh")
    public AlertSettingsView refreshTopics(
            @PathVariable UUID chatId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.refreshTopics(
                anonymousClientCookie.resolve(clientCookie, response),
                AlertScope.chat(chatId)
        );
    }


    @PostMapping("/alert-topics")
    @ResponseStatus(HttpStatus.CREATED)
    public AlertTopicView addTopic(
            @PathVariable UUID chatId,
            @Valid @RequestBody AlertTopicRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.addTopic(
                anonymousClientCookie.resolve(clientCookie, response),
                AlertScope.chat(chatId),
                request.label()
        );
    }


    @PatchMapping("/alert-topics/{topicId}")
    public AlertTopicView renameTopic(
            @PathVariable UUID chatId,
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
                AlertScope.chat(chatId),
                topicId,
                request.label()
        );
    }


    @DeleteMapping("/alert-topics/{topicId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteTopic(
            @PathVariable UUID chatId,
            @PathVariable Long topicId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        alertService.deleteTopic(
                anonymousClientCookie.resolve(clientCookie, response),
                AlertScope.chat(chatId),
                topicId
        );
    }


    @PostMapping("/alerts/scan")
    public ScanResult scan(
            @PathVariable UUID chatId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.scanNow(
                anonymousClientCookie.resolve(clientCookie, response),
                AlertScope.chat(chatId)
        );
    }
}
