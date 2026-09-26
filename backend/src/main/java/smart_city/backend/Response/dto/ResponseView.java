package smart_city.backend.Response.dto;

import smart_city.backend.Document.dto.DocumentView;
import smart_city.backend.Response.ChatResponseMessage;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public record ResponseView(
        Long id,
        UUID chatId,
        String prompt,
        String text,
        OffsetDateTime createdAt,
        List<DocumentView> documents
) {

    public static ResponseView from(ChatResponseMessage response) {
        return new ResponseView(
                response.getId(),
                response.getChat().getId(),
                response.getPrompt(),
                response.getText(),
                response.getCreatedAt(),
                response
                        .getDocuments()
                        .stream()
                        .map(DocumentView::from)
                        .toList()
        );
    }
}

