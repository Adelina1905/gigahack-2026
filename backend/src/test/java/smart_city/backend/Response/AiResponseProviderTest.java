package smart_city.backend.Response;

import org.junit.jupiter.api.Test;

import smart_city.backend.Chat.Chat;
import smart_city.backend.Llm.LlmProperties;
import smart_city.backend.Llm.RecordingLlmGateway;
import smart_city.backend.Llm.dto.LlmTurn;

import java.time.Duration;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class AiResponseProviderTest {

    private final Chat chat = new Chat(UUID.randomUUID());

    private AiResponseProvider provider(int maxHistory) {
        return new AiResponseProvider(
                new RecordingLlmGateway(),
                new LlmProperties(
                        "http://unused",
                        Duration.ofSeconds(1),
                        Duration.ofSeconds(1),
                        Duration.ofMinutes(30),
                        maxHistory
                )
        );
    }

    @Test
    void storedTurnsBecomeUserAndAssistantMessages() {
        List<LlmTurn> history = provider(20).historyFrom(List.of(
                new ChatResponseMessage(chat, "Salut", "Bună!"),
                new ChatResponseMessage(chat, "Cine ești?", "Un asistent.")
        ));

        assertThat(history).containsExactly(
                LlmTurn.user("Salut"),
                LlmTurn.assistant("Bună!"),
                LlmTurn.user("Cine ești?"),
                LlmTurn.assistant("Un asistent.")
        );
    }

    @Test
    void responsesWithoutAPromptAreSkipped() {
        List<LlmTurn> history = provider(20).historyFrom(List.of(
                new ChatResponseMessage(chat, null, "legacy answer"),
                new ChatResponseMessage(chat, "Salut", "Bună!")
        ));

        assertThat(history).containsExactly(
                LlmTurn.user("Salut"),
                LlmTurn.assistant("Bună!")
        );
    }

    @Test
    void keepsOnlyTheMostRecentTurnsAndStartsWithTheUser() {
        List<LlmTurn> history = provider(3).historyFrom(List.of(
                new ChatResponseMessage(chat, "q1", "a1"),
                new ChatResponseMessage(chat, "q2", "a2"),
                new ChatResponseMessage(chat, "q3", "a3")
        ));

        assertThat(history).containsExactly(
                LlmTurn.user("q3"),
                LlmTurn.assistant("a3")
        );
    }
}
