package smart_city.backend.Llm;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import smart_city.backend.Llm.dto.LlmCitation;
import smart_city.backend.Llm.dto.LlmClarificationChoice;
import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.Llm.dto.LlmTurn;
import smart_city.backend.Llm.exceptions.LlmUnavailableException;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class LlmServiceClientTest {

    private final RestClient.Builder builder =
            RestClient.builder().baseUrl("http://llm.test");
    private final MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
    private final LlmServiceClient client =
            new LlmServiceClient(builder.build());

    private final UUID chatId =
            UUID.fromString("11111111-2222-3333-4444-555555555555");

    @Test
    void postsContractBodyAndParsesReply() {
        server.expect(requestTo("http://llm.test/v1/chat"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(content().json("""
                        {
                          "chatId": "11111111-2222-3333-4444-555555555555",
                          "message": "cat costa?",
                          "history": [
                            {"role": "user", "content": "salut"},
                            {"role": "assistant", "content": "Buna!"}
                          ]
                        }
                        """, JsonCompareMode.STRICT))
                .andRespond(withSuccess("""
                        {
                          "mode": "rag",
                          "status": "NEEDS_CLARIFICATION",
                          "answer": "Care?",
                          "citations": [
                            {"title": "T", "url": null, "exactQuote": "q", "documentId": "d"}
                          ],
                          "clarificationChoices": [
                            {"documentId": "d", "label": "L"}
                          ],
                          "extra": "ignored"
                        }
                        """, MediaType.APPLICATION_JSON));

        LlmReply reply = client.chat(
                chatId,
                "cat costa?",
                List.of(LlmTurn.user("salut"), LlmTurn.assistant("Buna!"))
        );

        server.verify();
        assertThat(reply).isEqualTo(new LlmReply(
                "rag",
                "NEEDS_CLARIFICATION",
                "Care?",
                List.of(new LlmCitation("T", null, "q", "d")),
                List.of(new LlmClarificationChoice("d", "L"))
        ));
        // An older service sends no reason, flags or citation dates.
        assertThat(reply.reason()).isNull();
        assertThat(reply.flagsOrEmpty()).isEmpty();
        assertThat(reply.citations().getFirst().outdated()).isFalse();
    }

    @Test
    void parsesReasonFlagsAndCitationProvenance() {
        server.expect(requestTo("http://llm.test/v1/chat"))
                .andRespond(withSuccess("""
                        {
                          "mode": "rag",
                          "status": "SUPPORTED",
                          "answer": "Taxa este 10 lei [S1].",
                          "citations": [
                            {
                              "id": "S1",
                              "evidenceId": "e1",
                              "versionId": "v1",
                              "title": "Decizia 1",
                              "url": "https://cmc.md/1",
                              "exactQuote": "10 lei",
                              "documentId": "d1",
                              "sourceFile": "decizia-1.pdf",
                              "locator": {"page": 2},
                              "publisher": "Consiliul Municipal Chișinău",
                              "publishedDate": "2019-03-14",
                              "outdated": true
                            }
                          ],
                          "clarificationChoices": null,
                          "reason": null,
                          "flags": ["OFF_TOPIC_DROPPED:3", "OUTDATED_SOURCES"]
                        }
                        """, MediaType.APPLICATION_JSON));

        LlmReply reply = client.chat(chatId, "cat costa?", List.of());

        assertThat(reply.reason()).isNull();
        assertThat(reply.flags())
                .containsExactly("OFF_TOPIC_DROPPED:3", "OUTDATED_SOURCES");
        assertThat(reply.citations()).containsExactly(new LlmCitation(
                "Decizia 1",
                "https://cmc.md/1",
                "10 lei",
                "d1",
                "S1",
                "e1",
                "v1",
                "decizia-1.pdf",
                Map.of("page", 2),
                "Consiliul Municipal Chișinău",
                "2019-03-14",
                true
        ));
    }

    @Test
    void parsesNotFoundReply() {
        server.expect(requestTo("http://llm.test/v1/chat"))
                .andRespond(withSuccess("""
                        {
                          "mode": "rag",
                          "status": "NOT_FOUND",
                          "answer": "Nu am găsit informația în documentele municipale.",
                          "citations": [],
                          "clarificationChoices": null,
                          "reason": "NO_RELEVANT_EVIDENCE",
                          "flags": []
                        }
                        """, MediaType.APPLICATION_JSON));

        LlmReply reply = client.chat(chatId, "cine a castigat meciul?", List.of());

        assertThat(reply.status()).isEqualTo("NOT_FOUND");
        assertThat(reply.reason()).isEqualTo("NO_RELEVANT_EVIDENCE");
        assertThat(reply.citationsOrEmpty()).isEmpty();
        assertThat(reply.flagsOrEmpty()).isEmpty();
    }

    @Test
    void serviceUnavailableCarriesDetail() {
        server.expect(requestTo("http://llm.test/v1/chat"))
                .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"detail\": \"Qdrant unreachable\"}"));

        assertThatThrownBy(() -> client.chat(chatId, "x", List.of()))
                .isInstanceOf(LlmUnavailableException.class)
                .hasMessageContaining("503")
                .hasMessageContaining("Qdrant unreachable");
    }

    @Test
    void clientErrorIsUnavailable() {
        server.expect(requestTo("http://llm.test/v1/chat"))
                .andRespond(withStatus(HttpStatus.UNPROCESSABLE_CONTENT)
                        .body("not json"));

        assertThatThrownBy(() -> client.chat(chatId, "x", List.of()))
                .isInstanceOf(LlmUnavailableException.class)
                .hasMessageContaining("422");
    }

    @Test
    void unparseableBodyIsUnavailable() {
        server.expect(requestTo("http://llm.test/v1/chat"))
                .andRespond(withSuccess("<html>oops</html>", MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.chat(chatId, "x", List.of()))
                .isInstanceOf(LlmUnavailableException.class);
    }

    @Test
    void emptyBodyIsUnavailable() {
        server.expect(requestTo("http://llm.test/v1/chat"))
                .andRespond(withSuccess());

        assertThatThrownBy(() -> client.chat(chatId, "x", List.of()))
                .isInstanceOf(LlmUnavailableException.class);
    }
}
