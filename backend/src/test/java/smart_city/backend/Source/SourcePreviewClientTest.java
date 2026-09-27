package smart_city.backend.Source;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class SourcePreviewClientTest {
    private final RestClient.Builder builder = RestClient.builder().baseUrl("http://llm.test");
    private final MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    private final SourcePreviewClient client = new SourcePreviewClient(builder.build());

    @Test
    void forwardsIdentifiersAndParsesStoredSections() {
        server.expect(requestTo("http://llm.test/v1/sources/doc%201/preview?versionId=v1&focusEvidenceId=e1&start=0&limit=20"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess("""
                        {
                          "documentId":"doc 1","versionId":"v1","title":"Decision",
                          "sourceUrl":"https://example.com/d.pdf","sourceFile":"d.pdf","sourceKind":"pdf",
                          "publishedDate":"2026-01-02","totalSections":1,"start":0,
                          "focusIndex":0,"focusSectionId":"p1","hasPrevious":false,"hasNext":false,
                          "sections":[{"id":"p1","order":0,"headingPath":["Intro"],
                            "text":"stored text","locator":{"page":2}}]
                        }
                        """, MediaType.APPLICATION_JSON));

        var result = client.get("doc 1", "v1", "e1", 0, 20);

        server.verify();
        assertThat(result.sections()).hasSize(1);
        assertThat(result.sections().getFirst().text()).isEqualTo("stored text");
        assertThat(result.sections().getFirst().locator()).containsEntry("page", 2);
    }

    @Test
    void mapsUnknownDocumentsToNotFound() {
        server.expect(requestTo("http://llm.test/v1/sources/missing/preview?limit=40"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThatThrownBy(() -> client.get("missing", null, null, null, 40))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        error -> assertThat(error.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND));
    }
}
