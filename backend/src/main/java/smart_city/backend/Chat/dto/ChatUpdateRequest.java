package smart_city.backend.Chat.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ChatUpdateRequest(

        @NotBlank
        @Size(max = 255)
        String name

) {
}