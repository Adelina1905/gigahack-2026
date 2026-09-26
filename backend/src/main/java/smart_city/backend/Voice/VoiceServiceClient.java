package smart_city.backend.Voice;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import smart_city.backend.Llm.dto.LlmErrorBody;

import java.io.IOException;
import java.util.Base64;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import static org.springframework.http.HttpStatus.*;

@Component
public class VoiceServiceClient {
    static final long MAX_AUDIO_BYTES = 10L * 1024 * 1024;
    private static final Set<String> FORMATS = Set.of("aac", "flac", "m4a", "mp3", "mp4", "ogg", "wav", "webm");
    private static final Map<String, String> MIME_FORMATS = Map.ofEntries(
            Map.entry("audio/aac", "aac"),
            Map.entry("audio/flac", "flac"),
            Map.entry("audio/x-flac", "flac"),
            Map.entry("audio/mp4", "mp4"),
            Map.entry("audio/x-m4a", "m4a"),
            Map.entry("audio/mpeg", "mp3"),
            Map.entry("audio/mp3", "mp3"),
            Map.entry("audio/ogg", "ogg"),
            Map.entry("audio/wav", "wav"),
            Map.entry("audio/x-wav", "wav"),
            Map.entry("audio/webm", "webm")
    );

    private final RestClient llmRestClient;

    public VoiceServiceClient(RestClient llmRestClient) {
        this.llmRestClient = llmRestClient;
    }

    public TranscriptionView transcribe(MultipartFile audio) {
        if (audio == null || audio.isEmpty()) {
            throw new ResponseStatusException(BAD_REQUEST, "Audio recording is empty");
        }
        if (audio.getSize() > MAX_AUDIO_BYTES) {
            throw new ResponseStatusException(PAYLOAD_TOO_LARGE, "Audio recording exceeds 10 MB");
        }
        String format = resolveFormat(audio);
        try {
            byte[] bytes = audio.getBytes();
            return llmRestClient.post()
                    .uri("/v1/audio/transcriptions")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(new TranscriptionRequest(
                            new InputAudio(Base64.getEncoder().encodeToString(bytes), format)))
                    .retrieve()
                    .body(TranscriptionView.class);
        } catch (IOException exception) {
            throw new ResponseStatusException(BAD_REQUEST, "Audio recording could not be read", exception);
        } catch (RestClientResponseException exception) {
            throw providerFailure(exception);
        } catch (RestClientException exception) {
            throw new ResponseStatusException(SERVICE_UNAVAILABLE, "Speech service is unavailable", exception);
        }
    }

    public SpeechResult synthesize(String text) {
        try {
            ResponseEntity<byte[]> response = llmRestClient.post()
                    .uri("/v1/audio/speech")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.valueOf("audio/mpeg"))
                    .body(new SpeechRequest(text))
                    .retrieve()
                    .toEntity(byte[].class);
            byte[] body = response.getBody();
            MediaType contentType = response.getHeaders().getContentType();
            if (body == null || body.length == 0 || contentType == null
                    || !"audio".equalsIgnoreCase(contentType.getType())) {
                throw new ResponseStatusException(SERVICE_UNAVAILABLE,
                        "Speech service returned invalid audio");
            }
            return new SpeechResult(body, contentType.toString());
        } catch (RestClientResponseException exception) {
            throw providerFailure(exception);
        } catch (RestClientException exception) {
            throw new ResponseStatusException(SERVICE_UNAVAILABLE, "Speech service is unavailable", exception);
        }
    }

    private String resolveFormat(MultipartFile audio) {
        String contentType = audio.getContentType();
        if (contentType != null) {
            String normalized = contentType.toLowerCase(Locale.ROOT).split(";", 2)[0].trim();
            String mapped = MIME_FORMATS.get(normalized);
            if (mapped != null) return mapped;
        }
        String filename = audio.getOriginalFilename();
        if (filename != null && filename.contains(".")) {
            String extension = filename.substring(filename.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
            if (FORMATS.contains(extension)) return extension;
        }
        throw new ResponseStatusException(UNSUPPORTED_MEDIA_TYPE, "Unsupported audio format");
    }

    private ResponseStatusException providerFailure(RestClientResponseException exception) {
        int status = exception.getStatusCode().value();
        var mapped = switch (status) {
            case 400 -> BAD_REQUEST;
            case 413 -> PAYLOAD_TOO_LARGE;
            case 415 -> UNSUPPORTED_MEDIA_TYPE;
            case 429 -> TOO_MANY_REQUESTS;
            case 504 -> GATEWAY_TIMEOUT;
            default -> SERVICE_UNAVAILABLE;
        };
        String detail = "Speech service request failed";
        try {
            LlmErrorBody body = exception.getResponseBodyAs(LlmErrorBody.class);
            if (body != null && body.detail() != null && !body.detail().isBlank()) detail = body.detail();
        } catch (RuntimeException ignored) {
            // Never expose an unexpected upstream response body.
        }
        return new ResponseStatusException(mapped, detail, exception);
    }

    private record InputAudio(String data, String format) {}
    private record TranscriptionRequest(InputAudio inputAudio) {}
    private record SpeechRequest(String text) {}
    public record SpeechResult(byte[] data, String contentType) {}
}
