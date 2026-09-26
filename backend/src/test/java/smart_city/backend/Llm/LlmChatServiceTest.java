package smart_city.backend.Llm;

import org.junit.jupiter.api.Test;

import smart_city.backend.Llm.dto.LlmCitation;
import smart_city.backend.Llm.dto.LlmClarificationChoice;
import smart_city.backend.Llm.dto.LlmMessageView;
import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.Llm.dto.LlmSourceView;
import smart_city.backend.Llm.dto.LlmTurn;
import smart_city.backend.Llm.exceptions.LlmUnavailableException;

import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class LlmChatServiceTest {

    private static final Instant NOW = Instant.parse("2026-01-01T10:00:00Z");

    private final MutableClock clock = new MutableClock(NOW);
    private final RecordingLlmGateway gateway = new RecordingLlmGateway();
    private final LlmChatService service = new LlmChatService(
            new LlmSessionStore(
                    new LlmProperties(
                            "http://unused",
                            Duration.ofSeconds(1),
                            Duration.ofSeconds(1),
                            Duration.ofMinutes(30),
                            20
                    ),
                    clock
            ),
            gateway,
            clock
    );
    private final UUID chatId = UUID.randomUUID();

    @Test
    void accumulatesHistoryAcrossTurnsInOrder() {
        service.send(chatId, "  first  ");
        service.send(chatId, "second");
        service.send(chatId, "third");

        assertThat(gateway.calls).hasSize(3);
        assertThat(gateway.calls.get(0).history()).isEmpty();
        assertThat(gateway.calls.get(0).message()).isEqualTo("first");
        assertThat(gateway.calls.get(2).chatId()).isEqualTo(chatId);
        assertThat(gateway.calls.get(2).history()).containsExactly(
                LlmTurn.user("first"),
                LlmTurn.assistant("answer to first"),
                LlmTurn.user("second"),
                LlmTurn.assistant("answer to second")
        );
    }

    @Test
    void failureLeavesHistoryUnchanged() {
        service.send(chatId, "first");

        gateway.setFailing(true);
        assertThatThrownBy(() -> service.send(chatId, "lost"))
                .isInstanceOf(LlmUnavailableException.class);

        gateway.setFailing(false);
        service.send(chatId, "retry");

        assertThat(gateway.calls.get(2).history()).containsExactly(
                LlmTurn.user("first"),
                LlmTurn.assistant("answer to first")
        );
    }

    @Test
    void clearForgetsHistory() {
        service.send(chatId, "first");
        service.clear(chatId);
        service.send(chatId, "again");

        assertThat(gateway.calls.get(1).history()).isEmpty();
    }

    @Test
    void mapsCitationsToSourcesWithTitleFallback() {
        gateway.replyWith(new LlmReply(
                "rag",
                "SUPPORTED",
                "Taxa este 10 lei.",
                List.of(
                        new LlmCitation("Decizia 1", "https://x/1", "q1", "doc-1"),
                        new LlmCitation(null, null, "q2", "doc-2"),
                        new LlmCitation(" ", null, null, null)
                ),
                null
        ));

        LlmMessageView view = service.send(chatId, "cat costa?");

        assertThat(view.chatId()).isEqualTo(chatId);
        assertThat(view.text()).isEqualTo("Taxa este 10 lei.");
        assertThat(view.mode()).isEqualTo("rag");
        assertThat(view.status()).isEqualTo("SUPPORTED");
        assertThat(view.createdAt())
                .isEqualTo(OffsetDateTime.ofInstant(NOW, ZoneOffset.UTC));
        assertThat(view.sources()).containsExactly(
                new LlmSourceView("Decizia 1", "https://x/1", "q1"),
                new LlmSourceView("doc-2", null, "q2"),
                new LlmSourceView("Sursă", null, null)
        );
    }

    @Test
    void appendsClarificationChoicesToText() {
        gateway.replyWith(new LlmReply(
                "rag",
                "NEEDS_CLARIFICATION",
                "Care document?",
                List.of(),
                List.of(
                        new LlmClarificationChoice("a", "Regulament A"),
                        new LlmClarificationChoice("b", "Regulament B")
                )
        ));

        LlmMessageView view = service.send(chatId, "regulament");

        assertThat(view.text())
                .isEqualTo("Care document?\n- Regulament A\n- Regulament B");
        assertThat(view.sources()).isEmpty();
        // History stores the raw answer, not the formatted choices.
        service.send(chatId, "A");
        assertThat(gateway.calls.get(1).history().get(1))
                .isEqualTo(LlmTurn.assistant("Care document?"));
    }
}
