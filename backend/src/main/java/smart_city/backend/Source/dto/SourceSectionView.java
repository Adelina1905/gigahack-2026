package smart_city.backend.Source.dto;

import java.util.List;
import java.util.Map;

public record SourceSectionView(
        String id,
        int order,
        List<String> headingPath,
        String text,
        Map<String, Object> locator
) {
}
