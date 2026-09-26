package smart_city.backend.Response;

import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import smart_city.backend.Chat.AnonymousClientCookie;
import smart_city.backend.Response.dto.ResponseCreateRequest;
import smart_city.backend.Response.dto.ResponseView;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/chats/{chatId}/responses")
public class ResponseController {

    private final ResponseService responseService;
    private final AnonymousClientCookie anonymousClientCookie;

    public ResponseController(
            ResponseService responseService,
            AnonymousClientCookie anonymousClientCookie
    ) {
        this.responseService = responseService;
        this.anonymousClientCookie = anonymousClientCookie;
    }

    @GetMapping
    public List<ResponseView> getAllResponses(
            @PathVariable UUID chatId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse servletResponse
    ) {
        return responseService.getAllResponses(
                anonymousClientCookie.resolve(
                        clientCookie,
                        servletResponse
                ),
                chatId
        );
    }

    @GetMapping("/{responseId}")
    public ResponseView getResponse(
            @PathVariable UUID chatId,
            @PathVariable Long responseId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse servletResponse
    ) {
        return responseService.getResponse(
                anonymousClientCookie.resolve(
                        clientCookie,
                        servletResponse
                ),
                chatId,
                responseId
        );
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ResponseView createResponse(
            @PathVariable UUID chatId,
            @Valid @RequestBody ResponseCreateRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse servletResponse
    ) {
        return responseService.createResponse(
                anonymousClientCookie.resolve(
                        clientCookie,
                        servletResponse
                ),
                chatId,
                request
        );
    }
}
