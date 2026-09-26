package smart_city.backend.Llm.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record LlmMessageRequest(
        @NotBlank
        @Size(max = 8000)
        String text
) {
}
