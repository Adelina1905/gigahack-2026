package smart_city.backend.Project;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ProjectRepository extends JpaRepository<Project, UUID> {

    List<Project> findAllByClientIdOrderByUpdatedAtDesc(UUID clientId);

    Optional<Project> findByIdAndClientId(
            UUID id,
            UUID clientId
    );
}
