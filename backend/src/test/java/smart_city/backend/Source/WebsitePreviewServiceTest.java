package smart_city.backend.Source;

import java.net.URI;
import java.io.ByteArrayOutputStream;

import javax.imageio.ImageIO;

import org.junit.jupiter.api.Test;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class WebsitePreviewServiceTest {
    @Test
    void acceptsPublicHttpUrlsAndRejectsPrivateTargets() {
        assertThat(WebsitePreviewService.publicHttpUri("https://8.8.8.8/source").toString())
                .isEqualTo("https://8.8.8.8/source");
        assertThatThrownBy(() -> WebsitePreviewService.publicHttpUri("http://127.0.0.1/admin"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> WebsitePreviewService.publicHttpUri("file:///etc/passwd"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> WebsitePreviewService.publicHttpUri("https://user:secret@8.8.8.8/"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void detectsPdfSourcesFromMetadataOrTheFinalPath() {
        assertThat(WebsitePreviewService.looksLikePdf(URI.create("https://8.8.8.8/document"), "pdf"))
                .isTrue();
        assertThat(WebsitePreviewService.looksLikePdf(URI.create("https://8.8.8.8/document.PDF?download=1"), "web"))
                .isTrue();
        assertThat(WebsitePreviewService.looksLikePdf(URI.create("https://8.8.8.8/page"), "web"))
                .isFalse();
        assertThat(WebsitePreviewService.looksLikePdf(
                URI.create("https://8.8.8.8/download/123"), "text",
                "application/octet-stream", "attachment; filename=\"municipal-act.pdf\""))
                .isTrue();
        assertThat(WebsitePreviewService.looksLikePdf(
                URI.create("https://8.8.8.8/download/123"), "text",
                "application/pdf", ""))
                .isTrue();
    }

    @Test
    void rendersTheFirstPdfPageToAPng() throws Exception {
        byte[] pdf;
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage(new PDRectangle(200, 300));
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 18);
                content.newLineAtOffset(20, 250);
                content.showText("PDF preview");
                content.endText();
            }
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            document.save(output);
            pdf = output.toByteArray();
        }

        var image = ImageIO.read(new java.io.ByteArrayInputStream(WebsitePreviewService.renderPdf(pdf)));

        assertThat(image).isNotNull();
        assertThat(image.getWidth()).isEqualTo(400);
        assertThat(image.getHeight()).isEqualTo(600);
    }
}
