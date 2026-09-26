package smart_city.backend.Response;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
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

// Committed transactions in an explicitly configured isolated database.
@EnabledIfEnvironmentVariable(named = "CHAT_TEST_JDBC_URL", matches = "jdbc:postgresql:.*")
class ResponseServiceTest extends smart_city.backend.IsolatedDatabaseTest {

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

    @Autowired private org.springframework.jdbc.core.JdbcTemplate jdbc;
    @Autowired private smart_city.backend.Chat.ChatService chatService;

    private final UUID clientId = UUID.randomUUID();
    private UUID chatId;

    @BeforeEach
    void setUp() {
        gateway.calls.clear();
        gateway.setFailing(false);
        gateway.replyWith(llmReply("Answer"));
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
        assertThat(responseService.getResponse(clientId, chatId, created.id()).aiReply()).isEqualTo(created.aiReply());
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
    void failedCallPreservesPromptForRetry() {
        gateway.setFailing(true);

        ResponseView failed = send("Salut");
        assertThat(failed.generationStatus()).isEqualTo(GenerationStatus.FAILED);
        assertThat(failed.text()).isNull();
        assertThat(failed.errorCode()).isEqualTo("AI_UNAVAILABLE");
        assertThat(responseService.getAllResponses(clientId, chatId)).hasSize(1);
        assertThat(chatRepository.findById(chatId).orElseThrow().getName())
                .isEqualTo("Salut");
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

    @Test
    void submissionAndRetryAreIdempotent() {
        UUID requestId = UUID.randomUUID();
        var request = new ResponseCreateRequest("Hello", requestId);
        gateway.setFailing(true);
        var first = responseService.submit(clientId, chatId, request);
        assertThat(first.created()).isTrue();
        var replay = responseService.submit(clientId, chatId, request);
        assertThat(replay.created()).isFalse();
        assertThat(replay.response().id()).isEqualTo(first.response().id());
        assertThat(gateway.calls).hasSize(1);
        assertThatThrownBy(() -> responseService.submit(clientId, chatId, new ResponseCreateRequest("different", requestId)))
                .isInstanceOf(smart_city.backend.config.ApiConflictException.class);
        gateway.setFailing(false);
        var retry = new smart_city.backend.Response.dto.RegenerateRequest(UUID.randomUUID(), first.response().generationVersion());
        var completed = responseService.regenerateResponse(clientId, chatId, first.response().id(), retry);
        var retriedAgain = responseService.regenerateResponse(clientId, chatId, first.response().id(), retry);
        assertThat(retriedAgain).isEqualTo(completed);
        assertThat(completed.generationStatus()).isEqualTo(GenerationStatus.COMPLETED);
        assertThat(gateway.calls).hasSize(2);
        assertThat(responseService.getAllResponses(clientId, chatId)).hasSize(1);
        assertThatThrownBy(() -> responseService.regenerateResponse(clientId, chatId, completed.id(),
                new smart_city.backend.Response.dto.RegenerateRequest(UUID.randomUUID(), 0)))
                .isInstanceOf(smart_city.backend.config.ApiConflictException.class);
    }

    @Test
    void failedRegenerationRetainsPreviousAnswerAndSources() {
        gateway.replyWith(new LlmReply("rag", "SUPPORTED", "Original", List.of(
                new LlmCitation("Source", "https://example.com/source", "Exact quote", "d1")), null));
        var first = send("Question");
        gateway.setFailing(true);
        var failed = responseService.regenerateResponse(clientId, chatId, first.id());
        assertThat(failed.generationStatus()).isEqualTo(GenerationStatus.FAILED);
        assertThat(failed.text()).isEqualTo(first.text());
        assertThat(failed.aiReply()).isEqualTo(first.aiReply());
        assertThat(failed.documents()).extracting(DocumentView::id, DocumentView::title, DocumentView::documentLink)
                .containsExactlyElementsOf(first.documents().stream()
                        .map(document -> tuple(document.id(), document.title(), document.documentLink())).toList());
        gateway.setFailing(false);
        send("Follow-up");
        assertThat(gateway.calls.getLast().history()).containsExactly(LlmTurn.user("Question"), LlmTurn.assistant("Original"));
    }

    @Test
    void pendingPromptCommitsBeforeGenerationAndOnlySameChatIsBusy() throws Exception {
        var entered = new java.util.concurrent.CountDownLatch(1);
        var release = new java.util.concurrent.CountDownLatch(1);
        UUID requestId = UUID.randomUUID();
        gateway.replyUsing(message -> {
            assertThat(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            if (message.equals("slow")) {
                entered.countDown();
                try { if (!release.await(10, java.util.concurrent.TimeUnit.SECONDS)) throw new IllegalStateException("test timed out"); }
                catch (InterruptedException e) { throw new RuntimeException(e); }
            }
            return llmReply("Done");
        });
        try (var executor = java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
            var result = executor.submit(() -> responseService.submit(clientId, chatId, new ResponseCreateRequest("slow", requestId)));
            try {
                assertThat(entered.await(5, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
                var pending = responseService.getAllResponses(clientId, chatId).getFirst();
                assertThat(pending.prompt()).isEqualTo("slow");
                assertThat(pending.generationStatus()).isEqualTo(GenerationStatus.PENDING);
                assertThat(pending.text()).isNull();
                assertThat(jdbc.queryForObject("select generation_status from responses where id = ?", String.class, pending.id())).isEqualTo("PENDING");
                assertThat(responseService.submit(clientId, chatId, new ResponseCreateRequest("slow", requestId)).created()).isFalse();
                assertThatThrownBy(() -> send("second"))
                        .isInstanceOf(smart_city.backend.config.ApiConflictException.class).hasMessageContaining("waiting");
                UUID other = chatRepository.save(new Chat(clientId)).getId();
                assertThat(responseService.createResponse(clientId, other, new ResponseCreateRequest("independent")).generationStatus())
                        .isEqualTo(GenerationStatus.COMPLETED);
            } finally { release.countDown(); }
            assertThat(result.get(5, java.util.concurrent.TimeUnit.SECONDS).response().generationStatus()).isEqualTo(GenerationStatus.COMPLETED);
        }
    }

    @Test
    void expiredAttemptCanRetryAndLateCompletionCannotOverwriteIt() throws Exception {
        var entered = new java.util.concurrent.CountDownLatch(1);
        var release = new java.util.concurrent.CountDownLatch(1);
        gateway.replyUsing(message -> {
            entered.countDown();
            try { release.await(10, java.util.concurrent.TimeUnit.SECONDS); }
            catch (InterruptedException e) { throw new RuntimeException(e); }
            return llmReply("Late old answer");
        });
        try (var executor = java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
            var original = executor.submit(() -> send("Pending question"));
            try {
                assertThat(entered.await(5, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
                var pending = responseService.getAllResponses(clientId, chatId).getFirst();
                jdbc.update("update responses set generation_expires_at = current_timestamp - interval '1 second' where id = ?", pending.id());
                responseService.recoverExpiredGenerations();
                assertThat(responseService.getResponse(clientId, chatId, pending.id()).errorCode()).isEqualTo("GENERATION_INTERRUPTED");
                gateway.replyWith(llmReply("Replacement"));
                responseService.regenerateResponse(clientId, chatId, pending.id(),
                        new smart_city.backend.Response.dto.RegenerateRequest(UUID.randomUUID(), pending.generationVersion()));
            } finally { release.countDown(); }
            assertThat(original.get(5, java.util.concurrent.TimeUnit.SECONDS).text()).isEqualTo("Replacement");
            assertThat(responseService.getAllResponses(clientId, chatId)).hasSize(1);
        }
    }

    @Test
    void chatCreationReplaysAfterRenameAndRejectsChangedPayload() {
        var request = new smart_city.backend.Chat.dto.ChatCreateRequest("New chat", UUID.randomUUID());
        var created = chatService.createIdempotent(clientId, request);
        chatService.updateChat(clientId, created.chat().id(), new smart_city.backend.Chat.dto.ChatUpdateRequest("Renamed"));
        var repeated = chatService.createIdempotent(clientId, request);
        assertThat(repeated.created()).isFalse();
        assertThat(repeated.chat().id()).isEqualTo(created.chat().id());
        assertThat(repeated.chat().name()).isEqualTo("Renamed");
        assertThatThrownBy(() -> chatService.createChat(clientId,
                new smart_city.backend.Chat.dto.ChatCreateRequest("Changed", request.requestId())))
                .isInstanceOf(smart_city.backend.config.ApiConflictException.class);
    }

    @Test
    void ownershipAndDeletionRemainEnforced() {
        var response = send("Private message");
        assertThatThrownBy(() -> responseService.getResponse(UUID.randomUUID(), chatId, response.id()))
                .isInstanceOf(smart_city.backend.Response.exceptions.ResponseNotFoundException.class);
        assertThatThrownBy(() -> responseService.submit(UUID.randomUUID(), chatId, new ResponseCreateRequest("Intrusion")))
                .isInstanceOf(smart_city.backend.Chat.exceptions.ChatNotFoundException.class);
        chatService.deleteChat(clientId, chatId);
        assertThat(jdbc.queryForObject("select count(*) from responses where chat_id = ?", Integer.class, chatId)).isZero();
    }

    @Test
    void malformedAnswerIsDurablyFailed() {
        gateway.replyWith(llmReply("   "));
        assertThat(send("Hello").errorCode()).isEqualTo("INVALID_AI_REPLY");
        gateway.replyWith(new LlmReply("rag", "NEEDS_CLARIFICATION", "Choose a document",
                List.of(), java.util.Collections.singletonList(null)));
        assertThat(send("Clarify").errorCode()).isEqualTo("INVALID_AI_REPLY");
    }
}
