package smart_city.backend.Alert;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

import java.time.Duration;

@ConfigurationProperties("app.alerts")
public record AlertProperties(
        // Turns the scheduled scan on or off; manual scans always work.
        @DefaultValue("true") boolean enabled,
        @DefaultValue("2m") Duration scanInterval,
        // New alerts per project per scheduled scan.
        @DefaultValue("2") int maxPerScan,
        // New alerts per manual scan ("Check now" and turning alerts on).
        @DefaultValue("3") int manualMax
) {
}
