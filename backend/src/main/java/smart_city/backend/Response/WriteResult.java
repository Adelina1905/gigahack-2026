package smart_city.backend.Response;

import smart_city.backend.Response.dto.ResponseView;

public record WriteResult(ResponseView response, boolean created) {
}
