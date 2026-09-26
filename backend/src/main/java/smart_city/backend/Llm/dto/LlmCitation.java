package smart_city.backend.Llm.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public record LlmCitation(
        String title,
        String url,
        String exactQuote,
        String documentId,
        String id,
        String evidenceId,
        String versionId,
        String sourceFile,
        Map<String, Object> locator
) {
    public LlmCitation(String title, String url, String exactQuote, String documentId) {
        this(title, url, exactQuote, documentId, null, null, null, null, null);
    }
}
