package smart_city.backend.Llm.dto;

public record LlmTurn(
        String role,
        String content
) {

    public static LlmTurn user(String content) {
        return new LlmTurn("user", content);
    }

    public static LlmTurn assistant(String content) {
        return new LlmTurn("assistant", content);
    }
}
