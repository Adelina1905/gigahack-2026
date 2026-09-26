package smart_city.backend.Response;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@EnableScheduling
public class GenerationRecovery {
    private final ResponseService service;
    public GenerationRecovery(ResponseService service) { this.service = service; }
    @EventListener(ApplicationReadyEvent.class)
    public void onStartup() { service.recoverExpiredGenerations(); }
    @Scheduled(fixedDelay = 30000, initialDelay = 30000)
    public void recover() { service.recoverExpiredGenerations(); }
}
