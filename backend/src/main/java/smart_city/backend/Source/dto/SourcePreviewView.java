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
        String previewImageUrl,
        String screenshotUrl,
        int totalSections,
        int start,
        Integer focusIndex,
        String focusSectionId,
        boolean hasPrevious,
        boolean hasNext,
        List<SourceSectionView> sections
) {
    public SourcePreviewView withPreviewImageUrl(String value) {
        return new SourcePreviewView(documentId, versionId, title, sourceUrl, sourceFile,
                sourceKind, publishedDate, value, screenshotUrl, totalSections, start, focusIndex,
                focusSectionId, hasPrevious, hasNext, sections);
    }

    public SourcePreviewView withScreenshotUrl(String value) {
        return new SourcePreviewView(documentId, versionId, title, sourceUrl, sourceFile,
                sourceKind, publishedDate, previewImageUrl, value, totalSections, start,
                focusIndex, focusSectionId, hasPrevious, hasNext, sections);
    }
}
