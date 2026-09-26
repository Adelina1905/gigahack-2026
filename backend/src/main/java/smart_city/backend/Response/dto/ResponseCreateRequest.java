package smart_city.backend.Response.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public record ResponseCreateRequest(
        @NotBlank
        @Size(max = 8000)
        String text,
        UUID requestId
) {
    public ResponseCreateRequest {
        text = text == null ? null : text.trim();
    }

    public ResponseCreateRequest(String text) {
        this(text, null);
    }
}

