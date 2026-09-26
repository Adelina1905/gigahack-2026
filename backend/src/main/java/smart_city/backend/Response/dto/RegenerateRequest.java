package smart_city.backend.Response.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record RegenerateRequest(
        @NotNull UUID requestId,
        @NotNull @Min(0) Integer expectedGenerationVersion
) {
}
