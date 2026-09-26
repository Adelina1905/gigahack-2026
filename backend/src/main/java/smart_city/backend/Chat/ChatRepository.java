package smart_city.backend.Chat;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ChatRepository extends JpaRepository<Chat, UUID> {

    List<Chat> findAllByClientIdOrderByCreatedAtDesc(UUID clientId);

    Optional<Chat> findByIdAndClientId(
            UUID id,
            UUID clientId
    );
}