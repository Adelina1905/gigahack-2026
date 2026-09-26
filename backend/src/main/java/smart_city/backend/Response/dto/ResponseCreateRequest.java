package smart_city.backend.Response.dto;

import jakarta.validation.constraints.NotBlank;

public record ResponseCreateRequest(
        @NotBlank
        String text
) {
}

