package smart_city.backend;

import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/** Database tests never fall back to the application's database or .env. */
@SpringBootTest(properties = "spring.config.import=")
@EnabledIfEnvironmentVariable(named = "CHAT_TEST_JDBC_URL", matches = "jdbc:postgresql:.*")
public abstract class IsolatedDatabaseTest {
    @DynamicPropertySource
    static void isolatedDatabase(DynamicPropertyRegistry properties) {
        String url = System.getenv("CHAT_TEST_JDBC_URL");
        if (url == null || !url.matches("jdbc:postgresql://[^/]+/[^?]+(?:_test|_integration)(?:\\?.*)?"))
            throw new IllegalArgumentException("CHAT_TEST_JDBC_URL must target a dedicated *_test or *_integration database");
        properties.add("spring.datasource.url", () -> url);
        properties.add("spring.datasource.username", () -> System.getenv().getOrDefault("CHAT_TEST_DB_USERNAME", "chat_test"));
        properties.add("spring.datasource.password", () -> System.getenv().getOrDefault("CHAT_TEST_DB_PASSWORD", ""));
    }
}
