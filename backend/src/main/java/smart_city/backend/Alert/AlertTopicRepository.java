package smart_city.backend.Alert;

import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface AlertTopicRepository extends JpaRepository<AlertTopic, Long> {

    // Removed AUTO topics included.
    List<AlertTopic> findAllByProjectIdOrderByCreatedAtAscIdAsc(UUID projectId);

    List<AlertTopic> findAllByProjectIdAndRemovedFalseOrderByCreatedAtAscIdAsc(UUID projectId);

    Optional<AlertTopic> findByIdAndProjectIdAndRemovedFalse(Long id, UUID projectId);

    boolean existsByProjectIdAndRemovedFalse(UUID projectId);

    // The user's questions in the project's chats, most recent first.
    @Query("select r.prompt from ChatResponseMessage r where r.chat.projectId = :projectId "
            + "and r.prompt is not null order by r.createdAt desc, r.id desc")
    List<String> findProjectPrompts(UUID projectId, Limit limit);

    @Query("select max(r.createdAt) from ChatResponseMessage r where r.chat.projectId = :projectId "
            + "and r.prompt is not null")
    OffsetDateTime findLatestPromptAt(UUID projectId);
}
