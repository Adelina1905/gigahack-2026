package smart_city.backend;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@EnabledIfEnvironmentVariable(named = "CHAT_TEST_JDBC_URL", matches = "jdbc:postgresql:.*")
class BackendApplicationTests extends IsolatedDatabaseTest {

	@Test
	void contextLoads() {
	}

}
