package smart_city.backend.Llm;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.web.client.RestClient;

import java.net.http.HttpClient;
import java.time.Clock;

@Configuration
@EnableScheduling
@EnableConfigurationProperties(LlmProperties.class)
public class LlmClientConfig {

    @Bean
    public RestClient llmRestClient(LlmProperties properties) {
        HttpClient httpClient = HttpClient
                .newBuilder()
                .connectTimeout(properties.connectTimeout())
                .build();

        JdkClientHttpRequestFactory requestFactory =
                new JdkClientHttpRequestFactory(httpClient);
        requestFactory.setReadTimeout(properties.readTimeout());

        return RestClient
                .builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(requestFactory)
                .build();
    }

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
