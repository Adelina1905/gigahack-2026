package smart_city.backend.Alert.dto;

import jakarta.validation.constraints.NotNull;

public record AlertSettingsRequest(

        @NotNull
        Boolean enabled

) {
}
