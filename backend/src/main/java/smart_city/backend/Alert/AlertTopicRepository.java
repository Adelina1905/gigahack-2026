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
    List<AlertTopic> findAllBySubscriptionIdOrderByCreatedAtAscIdAsc(Long subscriptionId);

    List<AlertTopic> findAllBySubscriptionIdAndRemovedFalseOrderByCreatedAtAscIdAsc(Long subscriptionId);

    Optional<AlertTopic> findByIdAndSubscriptionIdAndRemovedFalse(Long id, Long subscriptionId);

    boolean existsBySubscriptionIdAndRemovedFalse(Long subscriptionId);

    // The user's questions in the project's chats, most recent first.
    @Query("select r.prompt from ChatResponseMessage r where r.chat.projectId = :projectId "
            + "and r.prompt is not null order by r.createdAt desc, r.id desc")
    List<String> findProjectPrompts(UUID projectId, Limit limit);

    @Query("select max(r.createdAt) from ChatResponseMessage r where r.chat.projectId = :projectId "
            + "and r.prompt is not null")
    OffsetDateTime findLatestProjectPromptAt(UUID projectId);

    // The user's questions in one chat, most recent first.
    @Query("select r.prompt from ChatResponseMessage r where r.chat.id = :chatId "
            + "and r.prompt is not null order by r.createdAt desc, r.id desc")
    List<String> findChatPrompts(UUID chatId, Limit limit);

    @Query("select max(r.createdAt) from ChatResponseMessage r where r.chat.id = :chatId "
            + "and r.prompt is not null")
    OffsetDateTime findLatestChatPromptAt(UUID chatId);
}
