package smart_city.backend.Response;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import smart_city.backend.Chat.Chat;
import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Chat.exceptions.ChatNotFoundException;
import smart_city.backend.Response.dto.ResponseCreateRequest;
import smart_city.backend.Response.dto.ResponseView;
import smart_city.backend.Response.exceptions.ResponseNotFoundException;
import smart_city.backend.Response.exceptions.ResponseNotRegenerableException;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

@Service
public class ResponseService {

    private static final String DEFAULT_CHAT_NAME = "New chat";
    private static final int MAX_TITLE_LENGTH = 50;

    private final ResponseRepository responseRepository;
    private final ChatRepository chatRepository;
    private final AiResponseProvider aiResponseProvider;

    public ResponseService(
            ResponseRepository responseRepository,
            ChatRepository chatRepository,
            AiResponseProvider aiResponseProvider
    ) {
        this.responseRepository = responseRepository;
        this.chatRepository = chatRepository;
        this.aiResponseProvider = aiResponseProvider;
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

        String userInput = request.text().trim();
        String assistantText = aiResponseProvider.generateResponse(userInput);

        ChatResponseMessage response = new ChatResponseMessage(
                chat,
                userInput,
                assistantText
        );

        if (DEFAULT_CHAT_NAME.equals(chat.getName())) {
            chat.setName(titleFrom(userInput));
        }
        chat.setUpdatedAt(OffsetDateTime.now());

        return ResponseView.from(responseRepository.save(response));
    }

    // Asks the AI again for the same prompt and replaces the stored answer,
    // so the chat history keeps a single answer per question.
    @Transactional
    public ResponseView regenerateResponse(
            UUID clientId,
            UUID chatId,
            Long responseId
    ) {
        ChatResponseMessage response = responseRepository
                .findByIdAndChatIdAndChatClientId(
                        responseId,
                        chatId,
                        clientId
                )
                .orElseThrow(ResponseNotFoundException::new);

        if (response.getPrompt() == null || response.getPrompt().isBlank()) {
            throw new ResponseNotRegenerableException();
        }

        response.setText(
                aiResponseProvider.generateResponse(response.getPrompt())
        );
        response.getChat().setUpdatedAt(OffsetDateTime.now());

        return ResponseView.from(response);
    }

    private static String titleFrom(String userInput) {
        String singleLine = userInput.replaceAll("\\s+", " ").trim();

        if (singleLine.length() <= MAX_TITLE_LENGTH) {
            return singleLine;
        }

        return singleLine.substring(0, MAX_TITLE_LENGTH - 1).trim() + "…";
    }

    private Chat requireOwnedChat(UUID clientId, UUID chatId) {
        return chatRepository
                .findByIdAndClientId(chatId, clientId)
                .orElseThrow(ChatNotFoundException::new);
    }
}

