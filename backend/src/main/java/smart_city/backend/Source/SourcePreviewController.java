package smart_city.backend.Source;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

import java.time.Duration;
import java.net.URI;

import smart_city.backend.Source.dto.SourcePreviewView;

@Validated
@RestController
@RequestMapping("/api/sources")
public class SourcePreviewController {
    private final SourcePreviewClient client;
    private final WebsitePreviewService websitePreviewService;

    public SourcePreviewController(SourcePreviewClient client, WebsitePreviewService websitePreviewService) {
        this.client = client;
        this.websitePreviewService = websitePreviewService;
    }

    @GetMapping("/{documentId}/preview")
    public SourcePreviewView preview(
            @PathVariable @Size(min = 1, max = 256) String documentId,
            @RequestParam(required = false) String versionId,
            @RequestParam(required = false) String focusEvidenceId,
            @RequestParam(required = false) @Min(0) Integer start,
            @RequestParam(defaultValue = "40") @Min(1) @Max(100) int limit
    ) {
        SourcePreviewView result = client.get(documentId, versionId, focusEvidenceId, start, limit);
        if (result.sourceUrl() == null) {
            return result;
        }
        String screenshotUrl = UriComponentsBuilder.fromPath("/api/sources/{documentId}/screenshot")
                .queryParamIfPresent("versionId", java.util.Optional.ofNullable(versionId))
                .buildAndExpand(documentId)
                .encode()
                .toUriString();
        result = result.withScreenshotUrl(screenshotUrl);
        if (result.previewImageUrl() == null
                && !websitePreviewService.canEmbed(result.sourceUrl(), result.sourceKind())) {
            result = result.withPreviewImageUrl(screenshotUrl);
        }
        return result;
    }

    @GetMapping(value = "/{documentId}/screenshot", produces = MediaType.IMAGE_PNG_VALUE)
    public ResponseEntity<byte[]> screenshot(
            @PathVariable @Size(min = 1, max = 256) String documentId,
            @RequestParam(required = false) String versionId
    ) {
        SourcePreviewView source = client.get(documentId, versionId, null, null, 1);
        byte[] image = websitePreviewService.capture(source.sourceUrl(), source.sourceKind());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic())
                .contentType(MediaType.IMAGE_PNG)
                .body(image);
    }

    @GetMapping("/{documentId}/open")
    public ResponseEntity<byte[]> open(
            @PathVariable @Size(min = 1, max = 256) String documentId,
            @RequestParam(required = false) String versionId
    ) {
        SourcePreviewView source = client.get(documentId, versionId, null, null, 1);
        var pdf = websitePreviewService.inlinePdf(source.sourceUrl(), source.sourceKind());
        if (pdf.isPresent()) {
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic())
                    .contentType(MediaType.APPLICATION_PDF)
                    .header("Content-Disposition", "inline; filename=\"municipal-source.pdf\"")
                    .body(pdf.get());
        }
        return ResponseEntity.status(302)
                .location(URI.create(source.sourceUrl()))
                .build();
    }
}
