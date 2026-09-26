package smart_city.backend.Alert.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AlertTopicRequest(

        @NotBlank
        @Size(max = 80)
        String label

) {
}
