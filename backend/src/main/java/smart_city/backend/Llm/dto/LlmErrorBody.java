package smart_city.backend.Llm.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record LlmErrorBody(
        String detail
) {
}
