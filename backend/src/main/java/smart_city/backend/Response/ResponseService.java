package smart_city.backend.Response;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import smart_city.backend.Chat.Chat;
import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Chat.exceptions.ChatNotFoundException;
import smart_city.backend.Response.dto.ResponseCreateRequest;
import smart_city.backend.Response.dto.ResponseView;
import smart_city.backend.Response.exceptions.ResponseNotFoundException;

import java.util.List;
import java.util.UUID;

@Service
public class ResponseService {

    private final ResponseRepository responseRepository;
    private final ChatRepository chatRepository;

    public ResponseService(
            ResponseRepository responseRepository,
            ChatRepository chatRepository
    ) {
        this.responseRepository = responseRepository;
        this.chatRepository = chatRepository;
    }

    @Transactional(readOnly = true)
    public List<ResponseView> getAllResponses(
            UUID clientId,
            UUID chatId
    ) {
        requireOwnedChat(clientId, chatId);

        return responseRepository
                .findAllByChatIdAndChatClientIdOrderByCreatedAtAsc(
                        chatId,
                        clientId
                )
                .stream()
                .map(ResponseView::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public ResponseView getResponse(
            UUID clientId,
            UUID chatId,
            Long responseId
    ) {
        return responseRepository
                .findByIdAndChatIdAndChatClientId(
                        responseId,
                        chatId,
                        clientId
                )
                .map(ResponseView::from)
                .orElseThrow(ResponseNotFoundException::new);
    }

    @Transactional
    public ResponseView createResponse(
            UUID clientId,
            UUID chatId,
            ResponseCreateRequest request
    ) {
        Chat chat = requireOwnedChat(clientId, chatId);

        ChatResponseMessage response = new ChatResponseMessage(
                chat,
                request.text().trim()
        );

        return ResponseView.from(responseRepository.save(response));
    }

    private Chat requireOwnedChat(UUID clientId, UUID chatId) {
        return chatRepository
                .findByIdAndClientId(chatId, clientId)
                .orElseThrow(ChatNotFoundException::new);
    }
}

