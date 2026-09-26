package smart_city.backend.Response;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import smart_city.backend.Chat.Chat;
import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Chat.exceptions.ChatNotFoundException;
import smart_city.backend.Document.DocumentService;
import smart_city.backend.Document.StoredDocument;
import smart_city.backend.Llm.dto.LlmCitation;
import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.Llm.dto.LlmSourceView;
import smart_city.backend.Llm.dto.LlmTurn;
import smart_city.backend.Response.dto.ResponseCreateRequest;
import smart_city.backend.Response.dto.ResponseView;
import smart_city.backend.Response.exceptions.ResponseNotFoundException;
import smart_city.backend.Response.exceptions.ResponseNotRegenerableException;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class ResponseService {

    private static final String DEFAULT_CHAT_NAME = "New chat";
    private static final int MAX_TITLE_LENGTH = 50;
    private static final int MAX_DOCUMENT_TITLE_LENGTH = 255;

    private final ResponseRepository responseRepository;
    private final ChatRepository chatRepository;
    private final DocumentService documentService;
    private final AiResponseProvider aiResponseProvider;
    private final TransactionTemplate transactions;

    public ResponseService(
            ResponseRepository responseRepository,
            ChatRepository chatRepository,
            DocumentService documentService,
            AiResponseProvider aiResponseProvider,
            TransactionTemplate transactions
    ) {
        this.responseRepository = responseRepository;
        this.chatRepository = chatRepository;
        this.documentService = documentService;
        this.aiResponseProvider = aiResponseProvider;
        this.transactions = transactions;
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

    // The LLM call can take a while, so it runs between two short
    // transactions instead of holding a database connection open.
    public ResponseView createResponse(
            UUID clientId,
            UUID chatId,
            ResponseCreateRequest request
    ) {
        String userInput = request.text().trim();

        List<LlmTurn> history = transactions.execute(status -> {
            requireOwnedChat(clientId, chatId);
            return aiResponseProvider.historyFrom(
                    responseRepository.findAllByChatIdAndChatClientIdOrderByCreatedAtAsc(
                            chatId,
                            clientId
                    )
            );
        });

        LlmReply reply = aiResponseProvider.generateResponse(
                chatId,
                userInput,
                history
        );

        return transactions.execute(status -> {
            Chat chat = requireOwnedChat(clientId, chatId);

            ChatResponseMessage response = new ChatResponseMessage(
                    chat,
                    userInput,
                    reply.displayText()
            );
            response.setDocuments(citedDocuments(reply));

            if (DEFAULT_CHAT_NAME.equals(chat.getName())) {
                chat.setName(titleFrom(userInput));
            }
            chat.setUpdatedAt(OffsetDateTime.now());

            return ResponseView.from(responseRepository.save(response));
        });
    }

    // Asks the AI again for the same prompt, with the conversation as it was
    // before it, and replaces the stored answer, so the chat history keeps a
    // single answer per question.
    public ResponseView regenerateResponse(
            UUID clientId,
            UUID chatId,
            Long responseId
    ) {
        record Pending(String prompt, List<LlmTurn> history) {
        }

        Pending pending = transactions.execute(status -> {
            ChatResponseMessage response =
                    requireOwnedResponse(clientId, chatId, responseId);

            if (response.getPrompt() == null || response.getPrompt().isBlank()) {
                throw new ResponseNotRegenerableException();
            }

            List<ChatResponseMessage> earlier = responseRepository
                    .findAllByChatIdAndChatClientIdOrderByCreatedAtAsc(
                            chatId,
                            clientId
                    )
                    .stream()
                    .filter(candidate -> candidate.getId() < responseId)
                    .toList();

            return new Pending(
                    response.getPrompt(),
                    aiResponseProvider.historyFrom(earlier)
            );
        });

        LlmReply reply = aiResponseProvider.generateResponse(
                chatId,
                pending.prompt(),
                pending.history()
        );

        return transactions.execute(status -> {
            ChatResponseMessage response =
                    requireOwnedResponse(clientId, chatId, responseId);

            response.setText(reply.displayText());
            response.setDocuments(citedDocuments(reply));
            response.getChat().setUpdatedAt(OffsetDateTime.now());

            return ResponseView.from(response);
        });
    }

    // Each distinct citation becomes a stored document linked to the response.
    private List<StoredDocument> citedDocuments(LlmReply reply) {
        Map<String, StoredDocument> documents = new LinkedHashMap<>();

        for (LlmCitation citation : reply.citationsOrEmpty()) {
            LlmSourceView source = LlmSourceView.from(citation);
            String title = truncate(source.title(), MAX_DOCUMENT_TITLE_LENGTH);
            String link = source.link() == null ? "" : source.link().trim();

            documents.computeIfAbsent(
                    title + "\n" + link,
                    key -> documentService.findOrCreate(title, link)
            );
        }
        return List.copyOf(documents.values());
    }

    private static String truncate(String value, int maxLength) {
        String trimmed = value.trim();
        if (trimmed.length() <= maxLength) {
            return trimmed;
        }
        return trimmed.substring(0, maxLength - 1).trim() + "…";
    }

    private static String titleFrom(String userInput) {
        return truncate(userInput.replaceAll("\\s+", " "), MAX_TITLE_LENGTH);
    }

    private ChatResponseMessage requireOwnedResponse(
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
                .orElseThrow(ResponseNotFoundException::new);
    }

    private Chat requireOwnedChat(UUID clientId, UUID chatId) {
        return chatRepository
                .findByIdAndClientId(chatId, clientId)
                .orElseThrow(ChatNotFoundException::new);
    }
}

