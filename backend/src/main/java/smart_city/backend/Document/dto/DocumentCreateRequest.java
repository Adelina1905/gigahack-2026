package smart_city.backend.Document.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record DocumentCreateRequest(
        @NotBlank
        @Size(max = 255)
        String title,

        @NotBlank
        String documentLink
) {
}

