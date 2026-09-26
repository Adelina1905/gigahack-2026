package smart_city.backend.Alert;

import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import smart_city.backend.Alert.dto.AlertFeedbackRequest;
import smart_city.backend.Alert.dto.AlertView;
import smart_city.backend.Alert.dto.ReadAllRequest;
import smart_city.backend.Alert.dto.ReadAllResult;
import smart_city.backend.Alert.dto.UnreadCountView;
import smart_city.backend.Chat.AnonymousClientCookie;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/alerts")
public class AlertController {

    private final AlertService alertService;
    private final AnonymousClientCookie anonymousClientCookie;

    public AlertController(
            AlertService alertService,
            AnonymousClientCookie anonymousClientCookie
    ) {
        this.alertService = alertService;
        this.anonymousClientCookie = anonymousClientCookie;
    }


    @GetMapping
    public List<AlertView> getAlerts(
            @RequestParam(required = false) UUID projectId,
            @RequestParam(defaultValue = "false") boolean unreadOnly,
            @RequestParam(defaultValue = "50") int limit,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.getAlerts(
                anonymousClientCookie.resolve(clientCookie, response),
                projectId,
                unreadOnly,
                limit
        );
    }


    @GetMapping("/unread-count")
    public UnreadCountView getUnreadCount(
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.getUnreadCount(
                anonymousClientCookie.resolve(clientCookie, response)
        );
    }


    @PostMapping("/{alertId}/read")
    public AlertView markRead(
            @PathVariable Long alertId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return alertService.markRead(
                anonymousClientCookie.resolve(clientCookie, response),
                alertId
        );
    }


    @PostMapping("/read-all")
    public ReadAllResult markAllRead(
            @RequestBody(required = false) ReadAllRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return new ReadAllResult(alertService.markAllRead(
                anonymousClientCookie.resolve(clientCookie, response),
                request == null ? null : request.projectId()
        ));
    }


    @PostMapping("/{alertId}/feedback")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void giveFeedback(
            @PathVariable Long alertId,
            @Valid @RequestBody AlertFeedbackRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        // NOT_RELEVANT is the only feedback value (validated).
        alertService.dismissNotRelevant(
                anonymousClientCookie.resolve(clientCookie, response),
                alertId
        );
    }
}
