package smart_city.backend.Llm.dto;

public record LlmSourceView(
        String title,
        String link,
        String quote
) {

    static final String DEFAULT_TITLE = "Sursă";

    public static LlmSourceView from(LlmCitation citation) {
        return new LlmSourceView(
                firstNonBlank(
                        citation.title(),
                        citation.documentId(),
                        DEFAULT_TITLE
                ),
                citation.url(),
                citation.exactQuote()
        );
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }
}
