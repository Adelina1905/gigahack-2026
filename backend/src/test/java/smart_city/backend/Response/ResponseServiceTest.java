package smart_city.backend.Response;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.transaction.annotation.Transactional;

import smart_city.backend.Chat.Chat;
import smart_city.backend.Chat.ChatRepository;
import smart_city.backend.Document.dto.DocumentView;
import smart_city.backend.Llm.RecordingLlmGateway;
import smart_city.backend.Llm.dto.LlmCitation;
import smart_city.backend.Llm.dto.LlmClarificationChoice;
import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.Llm.dto.LlmTurn;
import smart_city.backend.Llm.exceptions.LlmUnavailableException;
import smart_city.backend.Response.dto.ResponseCreateRequest;
import smart_city.backend.Response.dto.ResponseView;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.tuple;

// Runs against the compose Postgres; every test rolls back.
@SpringBootTest
@Transactional
class ResponseServiceTest {

    @TestConfiguration
    static class Fakes {

        @Bean
        @Primary
        RecordingLlmGateway recordingLlmGateway() {
            return new RecordingLlmGateway();
        }
    }

    @Autowired
    private ResponseService responseService;

    @Autowired
    private ChatRepository chatRepository;

    @Autowired
    private RecordingLlmGateway gateway;

    private final UUID clientId = UUID.randomUUID();
    private UUID chatId;

    @BeforeEach
    void setUp() {
        gateway.calls.clear();
        gateway.setFailing(false);
        chatId = chatRepository.save(new Chat(clientId)).getId();
    }

    private ResponseView send(String text) {
        return responseService.createResponse(
                clientId,
                chatId,
                new ResponseCreateRequest(text)
        );
    }

    private static LlmReply llmReply(String answer) {
        return new LlmReply("llm", "LLM", answer, List.of(), null);
    }

    @Test
    void sendsEarlierTurnsOfTheChatAsHistory() {
        gateway.replyWith(llmReply("Bună, Ion!"));
        send("Mă numesc Ion.");
        gateway.replyWith(llmReply("Te cheamă Ion."));

        ResponseView view = send("  Cum mă cheamă?  ");

        assertThat(gateway.calls).hasSize(2);
        RecordingLlmGateway.Call second = gateway.calls.get(1);
        assertThat(second.chatId()).isEqualTo(chatId);
        assertThat(second.message()).isEqualTo("Cum mă cheamă?");
        assertThat(second.history()).containsExactly(
                LlmTurn.user("Mă numesc Ion."),
                LlmTurn.assistant("Bună, Ion!")
        );
        assertThat(view.prompt()).isEqualTo("Cum mă cheamă?");
        assertThat(view.text()).isEqualTo("Te cheamă Ion.");
        assertThat(chatRepository.findById(chatId).orElseThrow().getName())
                .isEqualTo("Mă numesc Ion.");
    }

    @Test
    void storesCitationsAsDocumentsOncePerDistinctSource() {
        gateway.replyWith(new LlmReply(
                "rag",
                "SUPPORTED",
                "Taxa este 10 lei.",
                List.of(
                        new LlmCitation("Decizia 1", "https://cmc.md/1", "q1", "d1"),
                        new LlmCitation("Decizia 1", "https://cmc.md/1", "q2", "d1"),
                        new LlmCitation(null, null, "q3", "doc-2")
                ),
                null
        ));

        ResponseView created = send("Cât costă?");
        ResponseView again = send("Și din nou?");

        assertThat(created.documents())
                .extracting(DocumentView::title, DocumentView::documentLink)
                .containsExactly(
                        tuple("Decizia 1", "https://cmc.md/1"),
                        tuple("doc-2", "")
                );
        assertThat(again.documents())
                .extracting(DocumentView::id)
                .containsExactlyElementsOf(
                        created.documents().stream().map(DocumentView::id).toList()
                );
        assertThat(responseService.getAllResponses(clientId, chatId).getFirst().documents())
                .hasSize(2);
    }

    @Test
    void clarificationChoicesAreListedUnderTheAnswer() {
        gateway.replyWith(new LlmReply(
                "rag",
                "NEEDS_CLARIFICATION",
                "Care document?",
                List.of(),
                List.of(
                        new LlmClarificationChoice("a", "Decizia A"),
                        new LlmClarificationChoice("b", "Decizia B")
                )
        ));

        assertThat(send("Taxa?").text())
                .isEqualTo("Care document?\n- Decizia A\n- Decizia B");
    }

    @Test
    void failedCallStoresNothing() {
        gateway.setFailing(true);

        assertThatThrownBy(() -> send("Salut"))
                .isInstanceOf(LlmUnavailableException.class);

        assertThat(responseService.getAllResponses(clientId, chatId)).isEmpty();
        assertThat(chatRepository.findById(chatId).orElseThrow().getName())
                .isEqualTo("New chat");
    }

    @Test
    void regenerateUsesOnlyTheTurnsBeforeTheResponse() {
        gateway.replyWith(llmReply("a1"));
        ResponseView first = send("q1");
        gateway.replyWith(llmReply("a2"));
        send("q2");
        gateway.calls.clear();
        gateway.replyWith(new LlmReply(
                "rag",
                "SUPPORTED",
                "a1 again",
                List.of(new LlmCitation("Decizia 1", "https://cmc.md/1", "q", "d1")),
                null
        ));

        ResponseView regenerated = responseService.regenerateResponse(
                clientId,
                chatId,
                first.id()
        );

        assertThat(gateway.calls).singleElement().satisfies(call -> {
            assertThat(call.message()).isEqualTo("q1");
            assertThat(call.history()).isEmpty();
        });
        assertThat(regenerated.id()).isEqualTo(first.id());
        assertThat(regenerated.text()).isEqualTo("a1 again");
        assertThat(regenerated.documents()).hasSize(1);
        assertThat(responseService.getAllResponses(clientId, chatId))
                .extracting(ResponseView::text)
                .containsExactly("a1 again", "a2");
    }
}
