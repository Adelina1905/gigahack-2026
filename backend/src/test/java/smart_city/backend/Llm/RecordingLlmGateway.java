package smart_city.backend.Llm;

import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.Llm.dto.LlmTurn;
import smart_city.backend.Llm.exceptions.LlmUnavailableException;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.function.Function;

/** Hand-written gateway that records calls and replies with a canned answer. */
public final class RecordingLlmGateway implements LlmGateway {

    public record Call(UUID chatId, String message, List<LlmTurn> history) {
    }

    public final List<Call> calls = new ArrayList<>();
    private Function<String, LlmReply> replies = message -> new LlmReply(
            "llm",
            "LLM",
            "answer to " + message,
            List.of(),
            null
    );
    private boolean failing;

    public void replyWith(LlmReply reply) {
        replies = message -> reply;
    }

    public void setFailing(boolean failing) {
        this.failing = failing;
    }

    @Override
    public LlmReply chat(UUID chatId, String message, List<LlmTurn> history) {
        calls.add(new Call(chatId, message, List.copyOf(history)));
        if (failing) {
            throw new LlmUnavailableException("service down");
        }
        return replies.apply(message);
    }
}
