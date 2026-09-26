package smart_city.backend.Source.dto;

import java.util.List;

public record SourcePreviewView(
        String documentId,
        String versionId,
        String title,
        String sourceUrl,
        String sourceFile,
        String sourceKind,
        String publishedDate,
        int totalSections,
        int start,
        Integer focusIndex,
        String focusSectionId,
        boolean hasPrevious,
        boolean hasNext,
        List<SourceSectionView> sections
) {
}
