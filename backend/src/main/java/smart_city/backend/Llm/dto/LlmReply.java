package smart_city.backend.Llm.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public record LlmReply(
        String mode,
        String status,
        String answer,
        List<LlmCitation> citations,
        List<LlmClarificationChoice> clarificationChoices
) {

    public static final String NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION";

    /** The answer as shown to the user, with clarification choices listed under it. */
    public String displayText() {
        if (!NEEDS_CLARIFICATION.equals(status)
                || clarificationChoices == null
                || clarificationChoices.isEmpty()) {
            return answer;
        }

        StringBuilder text = new StringBuilder(answer);
        for (LlmClarificationChoice choice : clarificationChoices) {
            text.append("\n- ").append(choice.label());
        }
        return text.toString();
    }

    public List<LlmCitation> citationsOrEmpty() {
        return citations == null ? List.of() : citations;
    }
}
