package smart_city.backend.Chat;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import jakarta.persistence.LockModeType;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ChatRepository extends JpaRepository<Chat, UUID> {

    Optional<Chat> findByClientIdAndRequestId(UUID clientId, UUID requestId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select c from Chat c where c.id = :id and c.clientId = :clientId")
    Optional<Chat> lockOwnedChat(UUID id, UUID clientId);

    List<Chat> findAllByClientIdOrderByUpdatedAtDesc(UUID clientId);

    List<Chat> findAllByClientIdAndProjectIdIsNotNullOrderByUpdatedAtDesc(UUID clientId);

    List<Chat> findAllByClientIdAndProjectIdOrderByUpdatedAtDesc(UUID clientId, UUID projectId);

    // Mirrors ON DELETE SET NULL so managed chats never write back a deleted project's id.
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update Chat c set c.projectId = null where c.projectId = :projectId")
    int detachFromProject(UUID projectId);

    Optional<Chat> findByIdAndClientId(
            UUID id,
            UUID clientId
    );
}
