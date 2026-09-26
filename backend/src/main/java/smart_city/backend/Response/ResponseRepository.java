package smart_city.backend.Response;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ResponseRepository
        extends JpaRepository<ChatResponseMessage, Long> {

    @EntityGraph(attributePaths = "documents")
    List<ChatResponseMessage>
    findAllByChatIdAndChatClientIdOrderByCreatedAtAsc(
            UUID chatId,
            UUID clientId
    );

    Optional<ChatResponseMessage>
    findByIdAndChatIdAndChatClientId(
            Long responseId,
            UUID chatId,
            UUID clientId
    );
}

