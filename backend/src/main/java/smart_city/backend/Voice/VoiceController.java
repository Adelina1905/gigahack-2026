package smart_city.backend.Voice;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import smart_city.backend.Chat.AnonymousClientCookie;
import smart_city.backend.Response.GenerationStatus;
import smart_city.backend.Response.ResponseService;
import smart_city.backend.Response.dto.ResponseView;
import smart_city.backend.config.ApiConflictException;

import java.util.UUID;

@RestController
@RequestMapping("/api")
public class VoiceController {
    private final VoiceServiceClient voice;
    private final ResponseService responses;
    private final AnonymousClientCookie anonymousClientCookie;

    public VoiceController(VoiceServiceClient voice, ResponseService responses,
                           AnonymousClientCookie anonymousClientCookie) {
        this.voice = voice;
        this.responses = responses;
        this.anonymousClientCookie = anonymousClientCookie;
    }

    @PostMapping(value = "/voice/transcriptions", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public TranscriptionView transcribe(@RequestParam("audio") MultipartFile audio) {
        TranscriptionView result = voice.transcribe(audio);
        if (result == null || result.text() == null || result.text().isBlank()) {
            throw new ResponseStatusException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,
                    "Speech service returned an empty transcript");
        }
        return result;
    }

    @PostMapping("/chats/{chatId}/responses/{responseId}/speech")
    public ResponseEntity<byte[]> speech(
            @PathVariable UUID chatId,
            @PathVariable Long responseId,
            @CookieValue(name = AnonymousClientCookie.COOKIE_NAME, required = false) String clientCookie,
            HttpServletResponse servletResponse
    ) {
        UUID clientId = anonymousClientCookie.resolve(clientCookie, servletResponse);
        ResponseView response = responses.getResponse(clientId, chatId, responseId);
        if (response.generationStatus() != GenerationStatus.COMPLETED
                || response.text() == null || response.text().isBlank()) {
            throw new ApiConflictException("RESPONSE_NOT_READY",
                    "Only completed assistant responses can be spoken.");
        }
        VoiceServiceClient.SpeechResult result = voice.synthesize(response.text());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .contentType(MediaType.parseMediaType(result.contentType()))
                .body(result.data());
    }
}
