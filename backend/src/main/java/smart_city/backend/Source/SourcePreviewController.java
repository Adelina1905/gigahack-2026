package smart_city.backend.Source;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import smart_city.backend.Source.dto.SourcePreviewView;

@Validated
@RestController
@RequestMapping("/api/sources")
public class SourcePreviewController {
    private final SourcePreviewClient client;

    public SourcePreviewController(SourcePreviewClient client) {
        this.client = client;
    }

    @GetMapping("/{documentId}/preview")
    public SourcePreviewView preview(
            @PathVariable @Size(min = 1, max = 256) String documentId,
            @RequestParam(required = false) String versionId,
            @RequestParam(required = false) String focusEvidenceId,
            @RequestParam(required = false) @Min(0) Integer start,
            @RequestParam(defaultValue = "40") @Min(1) @Max(100) int limit
    ) {
        return client.get(documentId, versionId, focusEvidenceId, start, limit);
    }
}
