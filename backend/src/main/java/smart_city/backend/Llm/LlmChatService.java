package smart_city.backend.Llm;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import smart_city.backend.Llm.dto.LlmMessageView;
import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.Llm.dto.LlmSourceView;
import smart_city.backend.Llm.dto.LlmTurn;
import smart_city.backend.Llm.exceptions.LlmUnavailableException;

import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

@Service
public class LlmChatService {

    private static final Logger log =
            LoggerFactory.getLogger(LlmChatService.class);

    private final LlmSessionStore sessionStore;
    private final LlmGateway llmGateway;
    private final Clock clock;

    public LlmChatService(
            LlmSessionStore sessionStore,
            LlmGateway llmGateway,
            Clock clock
    ) {
        this.sessionStore = sessionStore;
        this.llmGateway = llmGateway;
        this.clock = clock;
    }

    public LlmMessageView send(UUID chatId, String text) {
        String message = text.trim();
        LlmSessionStore.Session session = sessionStore.acquire(chatId);

        LlmReply reply;
        try {
            reply = llmGateway.chat(chatId, message, session.history());

            // Only a successful turn is recorded, so a retry starts clean.
            session.append(LlmTurn.user(message));
            session.append(LlmTurn.assistant(reply.answer()));
        } catch (LlmUnavailableException exception) {
            log.warn(
                    "LLM turn failed for chat {}: {}",
                    chatId,
                    exception.getMessage()
            );
            throw exception;
        } finally {
            session.release();
        }

        return new LlmMessageView(
                chatId,
                reply.displayText(),
                reply.mode(),
                reply.status(),
                toSources(reply),
                OffsetDateTime.now(clock)
        );
    }

    public void clear(UUID chatId) {
        sessionStore.clear(chatId);
    }

    private List<LlmSourceView> toSources(LlmReply reply) {
        return reply
                .citationsOrEmpty()
                .stream()
                .map(LlmSourceView::from)
                .toList();
    }
}
