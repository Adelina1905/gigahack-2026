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
}
