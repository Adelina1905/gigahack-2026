package smart_city.backend.Alert.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record AlertFeedbackRequest(

        @NotNull
        @Pattern(regexp = "NOT_RELEVANT")
        String value

) {
}
