package smart_city.backend.Project.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ProjectCreateRequest(

        @NotBlank
        @Size(max = 255)
        String name

) {
}
