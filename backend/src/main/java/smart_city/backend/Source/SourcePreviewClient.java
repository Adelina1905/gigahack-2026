package smart_city.backend.Source;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

import smart_city.backend.Source.dto.SourcePreviewView;

@Component
public class SourcePreviewClient {
    private final RestClient llmRestClient;

    public SourcePreviewClient(RestClient llmRestClient) {
        this.llmRestClient = llmRestClient;
    }

    public SourcePreviewView get(String documentId, String versionId, String focusEvidenceId,
                                 Integer start, int limit) {
        try {
            SourcePreviewView result = llmRestClient.get().uri(builder -> {
                builder.path("/v1/sources/{documentId}/preview");
                if (versionId != null && !versionId.isBlank()) builder.queryParam("versionId", versionId);
                if (focusEvidenceId != null && !focusEvidenceId.isBlank()) builder.queryParam("focusEvidenceId", focusEvidenceId);
                if (start != null) builder.queryParam("start", start);
                builder.queryParam("limit", limit);
                return builder.build(documentId);
            }).retrieve().body(SourcePreviewView.class);
            if (result == null) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Source preview is unavailable");
            return result;
        } catch (RestClientResponseException exception) {
            HttpStatus status = exception.getStatusCode().value() == 404
                    ? HttpStatus.NOT_FOUND : HttpStatus.SERVICE_UNAVAILABLE;
            throw new ResponseStatusException(status, "Source preview is unavailable", exception);
        } catch (RestClientException exception) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Source preview is unavailable", exception);
        }
    }
}
