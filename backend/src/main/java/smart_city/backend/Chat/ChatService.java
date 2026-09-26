package smart_city.backend.Chat;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import smart_city.backend.Chat.dto.ChatCreateRequest;
import smart_city.backend.Chat.dto.ChatResponse;
import smart_city.backend.Chat.dto.ChatUpdateRequest;
import smart_city.backend.Chat.exceptions.ChatNotFoundException;

import java.util.List;
import java.util.UUID;

@Service
public class ChatService {

    private final ChatRepository chatRepository;

    public ChatService(ChatRepository chatRepository) {
        this.chatRepository = chatRepository;
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


    @Transactional
    public ChatResponse createChat(
            UUID clientId,
            ChatCreateRequest request
    ) {

        String name = "New chat";

        if (
                request != null &&
                request.name() != null &&
                !request.name().isBlank()
        ) {
            name = request.name().trim();
        }

        Chat chat = new Chat(
                clientId,
                name
        );

        Chat savedChat = chatRepository.save(chat);

        return ChatResponse.from(savedChat);
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