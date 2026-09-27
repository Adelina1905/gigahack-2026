package smart_city.backend.Source;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;

import smart_city.backend.Source.dto.SourcePreviewView;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SourcePreviewControllerTest {
    private final SourcePreviewClient client = mock(SourcePreviewClient.class);
    private final WebsitePreviewService websites = mock(WebsitePreviewService.class);
    private final SourcePreviewController controller = new SourcePreviewController(client, websites);

    @Test
    void suppliesScreenshotFallbackWhenTheStoredWebsiteCannotBeEmbedded() {
        SourcePreviewView source = source("doc 1", "v1", "https://example.com/page", null);
        when(client.get("doc 1", "v1", "e1", null, 40)).thenReturn(source);
        when(websites.canEmbed(source.sourceUrl(), source.sourceKind())).thenReturn(false);

        SourcePreviewView result = controller.preview("doc 1", "v1", "e1", null, 40);

        assertThat(result.previewImageUrl())
                .isEqualTo("/api/sources/doc%201/screenshot?versionId=v1");
        assertThat(result.screenshotUrl())
                .isEqualTo("/api/sources/doc%201/screenshot?versionId=v1");
    }

    @Test
    void screenshotUsesOnlyTheUrlResolvedFromTheStoredDocument() {
        SourcePreviewView source = source("doc", "v1", "https://example.com/page", null);
        when(client.get("doc", "v1", null, null, 1)).thenReturn(source);
        when(websites.capture(source.sourceUrl(), source.sourceKind())).thenReturn(new byte[] {1, 2, 3});

        var response = controller.screenshot("doc", "v1");

        assertThat(response.getBody()).containsExactly(1, 2, 3);
        assertThat(response.getHeaders().getContentType().toString()).isEqualTo("image/png");
        verify(websites).capture("https://example.com/page", "web");
    }

    @Test
    void openServesPdfInlineInsteadOfPreservingTheRemoteAttachmentHeader() {
        SourcePreviewView source = source("doc", "v1", "https://example.com/download/1", null);
        when(client.get("doc", "v1", null, null, 1)).thenReturn(source);
        when(websites.inlinePdf(source.sourceUrl(), source.sourceKind()))
                .thenReturn(Optional.of(new byte[] {1, 2, 3}));

        var response = controller.open("doc", "v1");

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getHeaders().getContentType()).isEqualTo(org.springframework.http.MediaType.APPLICATION_PDF);
        assertThat(response.getHeaders().getFirst("Content-Disposition"))
                .isEqualTo("inline; filename=\"municipal-source.pdf\"");
        assertThat(response.getBody()).containsExactly(1, 2, 3);
    }

    @Test
    void openRedirectsNonPdfWebSources() {
        SourcePreviewView source = source("doc", "v1", "https://example.com/page", null);
        when(client.get("doc", "v1", null, null, 1)).thenReturn(source);
        when(websites.inlinePdf(source.sourceUrl(), source.sourceKind())).thenReturn(Optional.empty());

        var response = controller.open("doc", "v1");

        assertThat(response.getStatusCode().value()).isEqualTo(302);
        assertThat(response.getHeaders().getLocation()).hasToString("https://example.com/page");
    }

    private static SourcePreviewView source(String documentId, String versionId, String url, String image) {
        return new SourcePreviewView(documentId, versionId, "Document", url, "source.html",
                "web", "2026-09-27", image, null, 0, 0, null, null,
                false, false, List.of());
    }
}
