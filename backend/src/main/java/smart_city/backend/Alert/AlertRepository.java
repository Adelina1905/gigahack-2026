package smart_city.backend.Alert;

import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import smart_city.backend.Alert.dto.ProjectUnreadCount;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface AlertRepository extends JpaRepository<Alert, Long> {

    Optional<Alert> findByIdAndClientId(Long id, UUID clientId);

    // Newest first, dismissed alerts excluded; a null projectId means every project.
    @Query("select a from Alert a where a.clientId = :clientId and a.dismissedAt is null "
            + "and (:projectId is null or a.projectId = :projectId) "
            + "and (:unreadOnly = false or a.readAt is null) "
            + "order by a.createdAt desc, a.id desc")
    List<Alert> findVisible(UUID clientId, UUID projectId, boolean unreadOnly, Limit limit);

    @Query("select new smart_city.backend.Alert.dto.ProjectUnreadCount(a.projectId, count(a)) "
            + "from Alert a where a.clientId = :clientId and a.readAt is null and a.dismissedAt is null "
            + "group by a.projectId")
    List<ProjectUnreadCount> countUnreadByProject(UUID clientId);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update Alert a set a.readAt = :now where a.clientId = :clientId "
            + "and a.readAt is null and a.dismissedAt is null "
            + "and (:projectId is null or a.projectId = :projectId)")
    int markAllRead(UUID clientId, UUID projectId, OffsetDateTime now);

    // Every alerted document, dismissed ones included, so none is alerted twice.
    @Query("select a.documentId from Alert a where a.projectId = :projectId")
    List<String> findDocumentIds(UUID projectId);
}
