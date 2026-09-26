package smart_city.backend.Llm;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import smart_city.backend.Llm.dto.LlmMessageRequest;
import smart_city.backend.Llm.dto.LlmMessageView;

import java.util.UUID;

@RestController
@RequestMapping("/api/llm/chats")
public class LlmController {

    private final LlmChatService llmChatService;

    public LlmController(LlmChatService llmChatService) {
        this.llmChatService = llmChatService;
    }

    @PostMapping("/{chatId}/messages")
    public LlmMessageView sendMessage(
            @PathVariable UUID chatId,
            @Valid @RequestBody LlmMessageRequest request
    ) {
        return llmChatService.send(chatId, request.text());
    }

    @DeleteMapping("/{chatId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void clearChat(@PathVariable UUID chatId) {
        llmChatService.clear(chatId);
    }
}
