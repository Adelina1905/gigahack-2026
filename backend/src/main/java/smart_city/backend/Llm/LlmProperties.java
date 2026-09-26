package smart_city.backend.Llm;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

@ConfigurationProperties("app.llm")
public record LlmProperties(
        String baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        Duration sessionTtl,
        int maxHistory
) {
}
