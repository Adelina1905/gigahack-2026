package smart_city.backend.Alert;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.UUID;

public interface ProjectAlertSettingsRepository extends JpaRepository<ProjectAlertSettings, UUID> {

    @Query("select s.projectId from ProjectAlertSettings s where s.enabled = true order by s.projectId")
    List<UUID> findEnabledProjectIds();
}
