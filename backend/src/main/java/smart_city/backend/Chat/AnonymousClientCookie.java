package smart_city.backend.Chat;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.UUID;

@Component
public class AnonymousClientCookie {

    public static final String COOKIE_NAME = "smart_city_client_id";

    private static final Duration COOKIE_LIFETIME = Duration.ofDays(365);

    public UUID resolve(String cookieValue, HttpServletResponse response) {
        UUID clientId = parse(cookieValue);

        if (clientId != null) {
            return clientId;
        }

        clientId = UUID.randomUUID();

        ResponseCookie cookie = ResponseCookie.from(
                        COOKIE_NAME,
                        clientId.toString()
                )
                .httpOnly(true)
                .secure(false)
                .sameSite("Lax")
                .path("/")
                .maxAge(COOKIE_LIFETIME)
                .build();

        response.addHeader(
                HttpHeaders.SET_COOKIE,
                cookie.toString()
        );

        return clientId;
    }

    private UUID parse(String cookieValue) {
        if (cookieValue == null || cookieValue.isBlank()) {
            return null;
        }

        try {
            return UUID.fromString(cookieValue);
        } catch (IllegalArgumentException exception) {
            return null;
        }
    }
}

