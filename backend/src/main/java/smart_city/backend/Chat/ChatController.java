package smart_city.backend.Chat;

import jakarta.validation.Valid;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import smart_city.backend.Chat.dto.ChatCreateRequest;
import smart_city.backend.Chat.dto.ChatResponse;
import smart_city.backend.Chat.dto.ChatUpdateRequest;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/chats")
public class ChatController {

    private final ChatService chatService;
    private final AnonymousClientCookie anonymousClientCookie;

    public ChatController(
            ChatService chatService,
            AnonymousClientCookie anonymousClientCookie
    ) {
        this.chatService = chatService;
        this.anonymousClientCookie = anonymousClientCookie;
    }


    @GetMapping
    public List<ChatResponse> getAllChats(
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {
        return chatService.getAllChats(
                anonymousClientCookie.resolve(clientCookie, response)
        );
    }


    @GetMapping("/{chatId}")
    public ChatResponse getChat(
            @PathVariable UUID chatId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return chatService.getChat(
                anonymousClientCookie.resolve(clientCookie, response),
                chatId
        );
    }


    @PostMapping
    public ResponseEntity<ChatResponse> createChat(
            @Valid @RequestBody(required = false)
            ChatCreateRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        ChatService.CreationResult result = chatService.createIdempotent(
                anonymousClientCookie.resolve(clientCookie, response),
                request
        );
        return ResponseEntity.status(result.created() ? 201 : 200).body(result.chat());
    }


    @PatchMapping("/{chatId}")
    public ChatResponse updateChat(
            @PathVariable UUID chatId,
            @Valid @RequestBody ChatUpdateRequest request,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        return chatService.updateChat(
                anonymousClientCookie.resolve(clientCookie, response),
                chatId,
                request
        );
    }


    @DeleteMapping("/{chatId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteChat(
            @PathVariable UUID chatId,
            @CookieValue(
                    name = AnonymousClientCookie.COOKIE_NAME,
                    required = false
            ) String clientCookie,
            HttpServletResponse response
    ) {

        chatService.deleteChat(
                anonymousClientCookie.resolve(clientCookie, response),
                chatId
        );
    }
}
