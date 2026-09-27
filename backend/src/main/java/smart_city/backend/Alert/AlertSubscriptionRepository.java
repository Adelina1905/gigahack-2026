package smart_city.backend.Alert;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface AlertSubscriptionRepository extends JpaRepository<AlertSubscription, Long> {

    Optional<AlertSubscription> findByProjectId(UUID projectId);

    Optional<AlertSubscription> findByChatId(UUID chatId);

    default Optional<AlertSubscription> findByScope(AlertScope scope) {
        return scope.isProject() ? findByProjectId(scope.projectId()) : findByChatId(scope.chatId());
    }

    // Topics and alerts go with it (ON DELETE CASCADE).
    @Modifying
    @Query("delete from AlertSubscription s where s.chatId = :chatId")
    int deleteByChatId(UUID chatId);

    @Query("select s.id from AlertSubscription s where s.enabled = true order by s.id")
    List<Long> findEnabledIds();
}
