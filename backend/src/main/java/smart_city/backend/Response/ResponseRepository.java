package smart_city.backend.Response;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.time.OffsetDateTime;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

public interface ResponseRepository
        extends JpaRepository<ChatResponseMessage, Long> {

    @org.springframework.data.jpa.repository.Lock(jakarta.persistence.LockModeType.PESSIMISTIC_WRITE)
    @Query("select r from ChatResponseMessage r where r.id = :id and r.chat.id = :chatId and r.chat.clientId = :clientId")
    Optional<ChatResponseMessage> lockOwnedResponse(Long id, UUID chatId, UUID clientId);

    Optional<ChatResponseMessage> findByChatIdAndRequestId(UUID chatId, UUID requestId);

    boolean existsByChatIdAndGenerationStatus(UUID chatId, GenerationStatus status);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update ChatResponseMessage r set r.generationStatus = smart_city.backend.Response.GenerationStatus.FAILED, "
            + "r.errorCode = 'GENERATION_INTERRUPTED', r.generationExpiresAt = null "
            + "where r.generationStatus = smart_city.backend.Response.GenerationStatus.PENDING "
            + "and r.generationExpiresAt <= :now")
    int failExpiredGenerations(OffsetDateTime now);

    @EntityGraph(attributePaths = "documents")
    List<ChatResponseMessage>
    findAllByChatIdAndChatClientIdOrderByCreatedAtAscIdAsc(
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

