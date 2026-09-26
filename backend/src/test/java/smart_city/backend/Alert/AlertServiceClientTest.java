package smart_city.backend.Alert;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import smart_city.backend.Alert.dto.AlertMatch;
import smart_city.backend.Alert.dto.MatchServiceReply;
import smart_city.backend.Alert.dto.MatchTopic;
import smart_city.backend.Alert.dto.TopicSuggestion;
import smart_city.backend.Alert.exceptions.AlertMatcherUnavailableException;

import java.time.LocalDate;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class AlertServiceClientTest {
    private final RestClient.Builder builder = RestClient.builder().baseUrl("http://llm.test");
    private final MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    private final AlertServiceClient client = new AlertServiceClient(builder.build());

    @Test
    void extractsTopics() {
        server.expect(requestTo("http://llm.test/v1/alerts/topics"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().json("""
                        {"questions":["Cât costă parcarea?"],"existingLabels":["Transport"]}
                        """, JsonCompareMode.STRICT))
                .andRespond(withSuccess("""
                        {"topics":[{"label":"Parcări","query":"tarif parcare"}]}
                        """, MediaType.APPLICATION_JSON));

        List<TopicSuggestion> topics = client.topics(List.of("Cât costă parcarea?"), List.of("Transport"));

        server.verify();
        assertThat(topics).containsExactly(new TopicSuggestion("Parcări", "tarif parcare"));
    }

    @Test
    void matchesTopicsAgainstTheFeed() {
        server.expect(requestTo("http://llm.test/v1/alerts/match"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().json("""
                        {"topics":[{"id":"7","query":"tarif parcare","minScore":null},
                                   {"id":"8","query":"transport","minScore":0.55}],
                         "excludedDocumentIds":["doc-1"],"limit":3}
                        """, JsonCompareMode.STRICT))
                .andRespond(withSuccess("""
                        {"matcher":"embedding","matches":[
                          {"topicId":"7","documentId":"doc-2","title":"Decizia 12","url":"https://cmc.md/12",
                           "source":"CMC","district":null,"category":"decizie","publishedDate":"2026-09-20",
                           "excerpt":"Tariful de parcare...","score":0.81,"extra":"ignored"},
                          {"topicId":"8","documentId":"doc-3","title":"Anunț","url":null,"source":null,
                           "district":null,"category":null,"publishedDate":null,"excerpt":"","score":0.6}
                        ]}
                        """, MediaType.APPLICATION_JSON));

        MatchServiceReply reply = client.match(
                List.of(new MatchTopic("7", "tarif parcare", null), new MatchTopic("8", "transport", 0.55)),
                List.of("doc-1"),
                3
        );

        server.verify();
        assertThat(reply.matcher()).isEqualTo("embedding");
        assertThat(reply.matches()).containsExactly(
                new AlertMatch("7", "doc-2", "Decizia 12", "https://cmc.md/12", "CMC", null, "decizie",
                        LocalDate.of(2026, 9, 20), "Tariful de parcare...", 0.81),
                new AlertMatch("8", "doc-3", "Anunț", null, null, null, null, null, "", 0.6)
        );
    }

    @Test
    void failuresAreUnavailable() {
        server.expect(requestTo("http://llm.test/v1/alerts/match"))
                .andRespond(withServerError());
        server.expect(requestTo("http://llm.test/v1/alerts/topics"))
                .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.match(List.of(new MatchTopic("1", "q", null)), List.of(), 2))
                .isInstanceOf(AlertMatcherUnavailableException.class);
        assertThatThrownBy(() -> client.topics(List.of("q"), List.of()))
                .isInstanceOf(AlertMatcherUnavailableException.class);
    }
}
