package smart_city.backend.Response;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import smart_city.backend.Chat.Chat;
import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Chat.exceptions.ChatNotFoundException;
import smart_city.backend.Document.DocumentService;
import smart_city.backend.Document.StoredDocument;
import smart_city.backend.Llm.dto.*;
import smart_city.backend.Llm.exceptions.LlmUnavailableException;
import smart_city.backend.Response.dto.*;
import smart_city.backend.Response.exceptions.*;
import smart_city.backend.config.ApiConflictException;
import java.time.OffsetDateTime;
import java.util.*;

@Service
public class ResponseService {
    private final ResponseRepository responses;
    private final ChatRepository chats;
    private final DocumentService documents;
    private final AiResponseProvider ai;
    private final TransactionTemplate transactions;

    public ResponseService(ResponseRepository responses, ChatRepository chats, DocumentService documents,
                           AiResponseProvider ai, TransactionTemplate transactions) {
        this.responses = responses; this.chats = chats; this.documents = documents;
        this.ai = ai; this.transactions = transactions;
    }

    @Transactional(readOnly = true)
    public List<ResponseView> getAllResponses(UUID clientId, UUID chatId) {
        chats.findByIdAndClientId(chatId, clientId).orElseThrow(ChatNotFoundException::new);
        return history(clientId, chatId).stream().map(ResponseView::from).toList();
    }

    @Transactional(readOnly = true)
    public ResponseView getResponse(UUID clientId, UUID chatId, Long responseId) {
        return ResponseView.from(responses.findByIdAndChatIdAndChatClientId(responseId, chatId, clientId)
                .orElseThrow(ResponseNotFoundException::new));
    }

    public ResponseView createResponse(UUID clientId, UUID chatId, ResponseCreateRequest request) {
        return submit(clientId, chatId, request).response();
    }

    public WriteResult submit(UUID clientId, UUID chatId, ResponseCreateRequest request) {
        UUID requestId = request.requestId() == null ? UUID.randomUUID() : request.requestId();
        Prepared prepared = transactions.execute(tx -> {
            Chat chat = lockChat(clientId, chatId);
            var previous = responses.findByChatIdAndRequestId(chatId, requestId);
            if (previous.isPresent()) {
                if (!Objects.equals(previous.get().getPrompt(), request.text()))
                    throw conflict("REQUEST_CONFLICT", "This request ID was already used for another message.");
                return new Prepared(ResponseView.from(previous.get()), null, List.of(), false);
            }
            requireFreeChat(chatId);
            List<LlmTurn> context = ai.historyFrom(history(clientId, chatId));
            ChatResponseMessage response = new ChatResponseMessage(chat, request.text(), null);
            response.setRequestId(requestId);
            response.beginGeneration(requestId, OffsetDateTime.now());
            responses.saveAndFlush(response);
            if ("New chat".equals(chat.getName())) chat.setName(truncate(request.text().replaceAll("\\s+", " "), 50));
            chat.setUpdatedAt(OffsetDateTime.now());
            return new Prepared(ResponseView.from(response), requestId, context, true);
        });
        return new WriteResult(generate(clientId, chatId, prepared), prepared.created());
    }

    public ResponseView regenerateResponse(UUID clientId, UUID chatId, Long responseId) {
        return regenerateResponse(clientId, chatId, responseId, null);
    }

    public ResponseView regenerateResponse(UUID clientId, UUID chatId, Long responseId, RegenerateRequest request) {
        Prepared prepared = transactions.execute(tx -> {
            lockChat(clientId, chatId);
            ChatResponseMessage response = lockResponse(clientId, chatId, responseId);
            if (response.getPrompt() == null || response.getPrompt().isBlank()) throw new ResponseNotRegenerableException();
            if (request != null && request.requestId().equals(response.getGenerationRequestId())) {
                if (request.expectedGenerationVersion() != response.getGenerationVersion() - 1)
                    throw conflict("REQUEST_CONFLICT", "This operation ID was already used for a different attempt.");
                return new Prepared(ResponseView.from(response), null, List.of(), false);
            }
            if (request != null && request.expectedGenerationVersion() != response.getGenerationVersion())
                throw conflict("STALE_GENERATION", "The response has changed. Refresh it before retrying.");
            requireFreeChat(chatId);
            UUID operation = request == null ? UUID.randomUUID() : request.requestId();
            List<LlmTurn> context = ai.historyFrom(history(clientId, chatId).stream()
                    .filter(row -> row.getId() < responseId).toList());
            response.beginGeneration(operation, OffsetDateTime.now());
            responses.flush();
            return new Prepared(ResponseView.from(response), operation, context, false);
        });
        return generate(clientId, chatId, prepared);
    }

    private record Prepared(ResponseView view, UUID operation, List<LlmTurn> history, boolean created) {}

    private ResponseView generate(UUID clientId, UUID chatId, Prepared prepared) {
        if (prepared.operation() == null) return prepared.view();
        // The pending prompt has committed. No DB connection is held during inference.
        LlmReply reply;
        try {
            reply = ai.generateResponse(chatId, prepared.view().prompt(), prepared.history());
            if (reply == null || reply.answer() == null || reply.answer().isBlank()
                    || !Set.of("rag", "llm", "demo").contains(Objects.toString(reply.mode(), ""))
                    || reply.status() == null || reply.status().isBlank()
                    || reply.citationsOrEmpty().stream().anyMatch(Objects::isNull)
                    || (reply.clarificationChoices() != null
                        && reply.clarificationChoices().stream().anyMatch(Objects::isNull)))
                return finish(clientId, chatId, prepared, null, "INVALID_AI_REPLY");
        } catch (LlmUnavailableException exception) {
            return finish(clientId, chatId, prepared, null, "AI_UNAVAILABLE");
        } catch (RuntimeException exception) {
            return finish(clientId, chatId, prepared, null, "GENERATION_FAILED");
        }
        return finish(clientId, chatId, prepared, reply, null);
    }

    private ResponseView finish(UUID clientId, UUID chatId, Prepared prepared, LlmReply reply, String error) {
        return transactions.execute(tx -> {
            lockChat(clientId, chatId);
            ChatResponseMessage row = lockResponse(clientId, chatId, prepared.view().id());
            if (row.isCurrentAttempt(prepared.operation(), prepared.view().generationVersion())) {
                if (row.getGenerationExpiresAt().isBefore(OffsetDateTime.now())) row.failGeneration("GENERATION_INTERRUPTED");
                else if (error != null) row.failGeneration(error);
                else row.completeGeneration(reply, citedDocuments(reply));
                row.getChat().setUpdatedAt(OffsetDateTime.now());
            }
            return ResponseView.from(row);
        });
    }

    public int recoverExpiredGenerations() {
        return transactions.execute(tx -> responses.failExpiredGenerations(OffsetDateTime.now()));
    }

    private void requireFreeChat(UUID chatId) {
        if (responses.existsByChatIdAndGenerationStatus(chatId, GenerationStatus.PENDING))
            throw conflict("CHAT_BUSY", "This chat is waiting for a response. Your unsent message can be retried shortly.");
    }
    private List<ChatResponseMessage> history(UUID clientId, UUID chatId) {
        return responses.findAllByChatIdAndChatClientIdOrderByCreatedAtAscIdAsc(chatId, clientId);
    }
    private Chat lockChat(UUID clientId, UUID chatId) {
        return chats.lockOwnedChat(chatId, clientId).orElseThrow(ChatNotFoundException::new);
    }
    private ChatResponseMessage lockResponse(UUID clientId, UUID chatId, Long responseId) {
        return responses.lockOwnedResponse(responseId, chatId, clientId).orElseThrow(ResponseNotFoundException::new);
    }
    private List<StoredDocument> citedDocuments(LlmReply reply) {
        Map<String, StoredDocument> result = new LinkedHashMap<>();
        for (LlmCitation citation : reply.citationsOrEmpty()) {
            LlmSourceView source = LlmSourceView.from(citation);
            String title = truncate(source.title(), 255);
            String link = source.link() == null ? "" : source.link().trim();
            result.computeIfAbsent(title + "\n" + link, key -> documents.findOrCreate(title, link));
        }
        return List.copyOf(result.values());
    }
    private static String truncate(String value, int length) {
        String trimmed = value.trim();
        return trimmed.length() <= length ? trimmed : trimmed.substring(0, length - 1).trim() + "…";
    }
    private static ApiConflictException conflict(String code, String message) { return new ApiConflictException(code, message); }
}
