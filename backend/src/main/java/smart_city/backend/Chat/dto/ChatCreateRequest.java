package smart_city.backend.Chat.dto;

import jakarta.validation.constraints.Size;

public record ChatCreateRequest(

        @Size(max = 255)
        String name

) {
}