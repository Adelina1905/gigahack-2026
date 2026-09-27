package smart_city.backend.Llm;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

import smart_city.backend.Llm.dto.LlmCitation;
import smart_city.backend.Llm.dto.LlmClarificationChoice;
import smart_city.backend.Llm.dto.LlmReply;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

// LlmReply is stored as JSONB in responses.ai_reply, so it must round-trip
// with and without the fields newer LLM services add.
class LlmReplyJsonTest {

    private final JsonMapper mapper = JsonMapper.builder().build();

    @Test
    void replyWithNewFieldsRoundTrips() {
        LlmReply reply = new LlmReply(
                "rag",
                "SUPPORTED",
                "Taxa este 10 lei.",
                List.of(new LlmCitation(
                        "Decizia 1",
                        "https://cmc.md/1",
                        "q",
                        "d1",
                        "S1",
                        "e1",
                        "v1",
                        "decizia-1.pdf",
                        Map.of("page", 3),
                        "Consiliul Municipal Chișinău",
                        "2024-05-01",
                        true
                )),
                List.of(new LlmClarificationChoice("d1", "Decizia 1")),
                null,
                List.of("OUTDATED_SOURCES", "CLAIMS_REJECTED:2/5")
        );

        LlmReply copy = mapper.readValue(mapper.writeValueAsString(reply), LlmReply.class);

        assertThat(copy).isEqualTo(reply);
        assertThat(copy.citations().getFirst().outdated()).isTrue();
        assertThat(copy.flagsOrEmpty()).containsExactly("OUTDATED_SOURCES", "CLAIMS_REJECTED:2/5");
    }

    @Test
    void notFoundReasonRoundTrips() {
        LlmReply reply = new LlmReply(
                "rag", "NOT_FOUND", "Nu am găsit.", List.of(), null,
                "NO_RELEVANT_EVIDENCE", List.of()
        );

        assertThat(mapper.readValue(mapper.writeValueAsString(reply), LlmReply.class))
                .isEqualTo(reply);
    }

    @Test
    void replyStoredBeforeTheNewFieldsStillReads() {
        LlmReply reply = mapper.readValue("""
                {
                  "mode": "rag",
                  "status": "SUPPORTED",
                  "answer": "Taxa este 10 lei.",
                  "citations": [
                    {"title": "Decizia 1", "url": "https://cmc.md/1", "exactQuote": "q",
                     "documentId": "d1", "id": "S1", "evidenceId": "e1", "versionId": "v1",
                     "sourceFile": "decizia-1.pdf", "locator": {"page": 3}}
                  ],
                  "clarificationChoices": null
                }
                """, LlmReply.class);

        assertThat(reply.reason()).isNull();
        assertThat(reply.flags()).isNull();
        assertThat(reply.flagsOrEmpty()).isEmpty();
        LlmCitation citation = reply.citations().getFirst();
        assertThat(citation.publisher()).isNull();
        assertThat(citation.publishedDate()).isNull();
        assertThat(citation.outdated()).isFalse();
        assertThat(citation.locator()).containsEntry("page", 3);
        assertThat(reply.displayText()).isEqualTo("Taxa este 10 lei.");
    }

    @Test
    void outdatedIsNeverNull() {
        assertThat(new LlmCitation("T", null, "q", "d").outdated()).isFalse();
        assertThat(new LlmCitation(
                "T", null, "q", "d", null, null, null, null, null, null, null, null
        ).outdated()).isFalse();
    }
}
