package smart_city.backend.Voice;

import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import smart_city.backend.Chat.AnonymousClientCookie;
import smart_city.backend.Response.GenerationStatus;
import smart_city.backend.Response.ResponseService;
import smart_city.backend.Response.dto.ResponseView;
import smart_city.backend.Response.exceptions.ResponseNotFoundException;
import smart_city.backend.config.ApiConflictException;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

class VoiceControllerTest {
    private final VoiceServiceClient voice = mock(VoiceServiceClient.class);
    private final ResponseService responses = mock(ResponseService.class);
    private final AnonymousClientCookie cookies = mock(AnonymousClientCookie.class);
    private final VoiceController controller = new VoiceController(voice, responses, cookies);
    private final HttpServletResponse servletResponse = mock(HttpServletResponse.class);
    private final UUID clientId = UUID.randomUUID();
    private final UUID chatId = UUID.randomUUID();

    @Test
    void transcriptionForwardsMultipartAudio() {
        var file = new MockMultipartFile("audio", "recording.webm", "audio/webm", new byte[]{1});
        when(voice.transcribe(file, "ro")).thenReturn(new TranscriptionView("Salut", "ro", 1.0));

        assertThat(controller.transcribe(file, "ro")).isEqualTo(new TranscriptionView("Salut", "ro", 1.0));
    }

    @Test
    void speechUsesOnlyTheOwnedCompletedStoredAnswer() {
        when(cookies.resolve("cookie", servletResponse)).thenReturn(clientId);
        when(responses.getResponse(clientId, chatId, 7L)).thenReturn(view(GenerationStatus.COMPLETED, "Answer"));
        when(voice.synthesize("Answer")).thenReturn(
                new VoiceServiceClient.SpeechResult(new byte[]{1, 2}, "audio/mpeg"));

        var result = controller.speech(chatId, 7L, "cookie", servletResponse);

        assertThat(result.getStatusCode().value()).isEqualTo(200);
        assertThat(result.getHeaders().getContentType()).isEqualTo(MediaType.valueOf("audio/mpeg"));
        assertThat(result.getHeaders().getCacheControl()).contains("no-store");
        assertThat(result.getBody()).containsExactly(1, 2);
    }

    @Test
    void pendingAndUnownedResponsesNeverReachSynthesis() {
        when(cookies.resolve(any(), same(servletResponse))).thenReturn(clientId);
        when(responses.getResponse(clientId, chatId, 7L)).thenReturn(view(GenerationStatus.PENDING, null));
        assertThatThrownBy(() -> controller.speech(chatId, 7L, null, servletResponse))
                .isInstanceOf(ApiConflictException.class);

        when(responses.getResponse(clientId, chatId, 8L)).thenThrow(new ResponseNotFoundException());
        assertThatThrownBy(() -> controller.speech(chatId, 8L, null, servletResponse))
                .isInstanceOf(ResponseNotFoundException.class);
        verifyNoInteractions(voice);
    }

    private ResponseView view(GenerationStatus status, String text) {
        return new ResponseView(7L, chatId, "Question", text, OffsetDateTime.now(), List.of(),
                UUID.randomUUID(), status, 1, null, null);
    }
}
