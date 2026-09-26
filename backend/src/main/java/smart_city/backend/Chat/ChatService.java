package smart_city.backend.Chat;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.dao.DataIntegrityViolationException;
import smart_city.backend.config.ApiConflictException;

import smart_city.backend.Chat.dto.ChatCreateRequest;
import smart_city.backend.Chat.dto.ChatResponse;
import smart_city.backend.Chat.dto.ChatUpdateRequest;
import smart_city.backend.Chat.exceptions.ChatNotFoundException;

import java.util.List;
import java.util.UUID;

@Service
public class ChatService {

    private final ChatRepository chatRepository;
    private final TransactionTemplate transactions;

    public ChatService(ChatRepository chatRepository, TransactionTemplate transactions) {
        this.chatRepository = chatRepository;
        this.transactions = transactions;
    }


    @Transactional(readOnly = true)
    public List<ChatResponse> getAllChats(UUID clientId) {

        return chatRepository
                .findAllByClientIdOrderByUpdatedAtDesc(clientId)
                .stream()
                .map(ChatResponse::from)
                .toList();
    }


    @Transactional(readOnly = true)
    public ChatResponse getChat(
            UUID clientId,
            UUID chatId
    ) {

        Chat chat = findOwnedChat(clientId, chatId);

        return ChatResponse.from(chat);
    }


    public record CreationResult(ChatResponse chat, boolean created) {}

    public ChatResponse createChat(UUID clientId, ChatCreateRequest request) {
        return createIdempotent(clientId, request).chat();
    }

    public CreationResult createIdempotent(UUID clientId, ChatCreateRequest request) {
        String name = request == null || request.name() == null || request.name().isBlank()
                ? "New chat" : request.name().trim();
        UUID requestId = request == null || request.requestId() == null ? UUID.randomUUID() : request.requestId();
        try {
            return transactions.execute(tx -> {
                var previous = chatRepository.findByClientIdAndRequestId(clientId, requestId);
                if (previous.isPresent()) return replay(previous.get(), name);
                Chat chat = new Chat(clientId, name);
                chat.setRequestId(requestId);
                chat.setCreationName(name);
                return new CreationResult(ChatResponse.from(chatRepository.saveAndFlush(chat)), true);
            });
        } catch (DataIntegrityViolationException collision) {
            // A concurrent request may have committed the same key. Read outside the rolled-back transaction.
            return transactions.execute(tx -> chatRepository.findByClientIdAndRequestId(clientId, requestId)
                    .map(chat -> replay(chat, name)).orElseThrow(() -> collision));
        }
    }

    private CreationResult replay(Chat chat, String name) {
        if (!name.equals(chat.getCreationName()))
            throw new ApiConflictException("REQUEST_CONFLICT", "This request ID was already used for another chat name.");
        return new CreationResult(ChatResponse.from(chat), false);
    }


    @Transactional
    public ChatResponse updateChat(
            UUID clientId,
            UUID chatId,
            ChatUpdateRequest request
    ) {

        Chat chat = findOwnedChat(
                clientId,
                chatId
        );

        chat.setName(
                request.name().trim()
        );

        return ChatResponse.from(chat);
    }


    @Transactional
    public void deleteChat(
            UUID clientId,
            UUID chatId
    ) {

        Chat chat = findOwnedChat(
                clientId,
                chatId
        );

        chatRepository.delete(chat);
    }


    private Chat findOwnedChat(
            UUID clientId,
            UUID chatId
    ) {

        return chatRepository
                .findByIdAndClientId(
                        chatId,
                        clientId
                )
                .orElseThrow(
                        ChatNotFoundException::new
                );
    }
}
