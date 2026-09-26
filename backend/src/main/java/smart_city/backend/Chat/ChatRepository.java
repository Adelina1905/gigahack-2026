package smart_city.backend.Chat;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
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

    Optional<Chat> findByIdAndClientId(
            UUID id,
            UUID clientId
    );
}
