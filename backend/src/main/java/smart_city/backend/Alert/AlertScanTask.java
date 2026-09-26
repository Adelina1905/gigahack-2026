package smart_city.backend.Alert;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

// Periodically scans every project with alerts turned on (new documents "arrive" over time).
@Component
@EnableScheduling
@EnableConfigurationProperties(AlertProperties.class)
public class AlertScanTask {

    private final AlertService alertService;
    private final AlertProperties properties;

    public AlertScanTask(AlertService alertService, AlertProperties properties) {
        this.alertService = alertService;
        this.properties = properties;
    }

    @Scheduled(
            fixedDelayString = "${app.alerts.scan-interval:2m}",
            initialDelayString = "${app.alerts.scan-interval:2m}"
    )
    public void scan() {
        if (properties.enabled()) {
            alertService.scanEnabledProjects();
        }
    }
}
