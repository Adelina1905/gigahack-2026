package smart_city.backend.Voice;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class VoiceServiceClientTest {
    private final RestClient.Builder builder = RestClient.builder().baseUrl("http://llm.test");
    private final MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    private final VoiceServiceClient client = new VoiceServiceClient(builder.build());

    @Test
    void forwardsAudioAsBase64AndParsesTranscript() {
        byte[] bytes = "recording".getBytes(StandardCharsets.UTF_8);
        server.expect(requestTo("http://llm.test/v1/audio/transcriptions"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().json("""
                        {"inputAudio":{"data":"%s","format":"webm"}}
                        """.formatted(Base64.getEncoder().encodeToString(bytes)), JsonCompareMode.STRICT))
                .andRespond(withSuccess("""
                        {"text":"Salut","language":"ro","durationSeconds":1.25}
                        """, MediaType.APPLICATION_JSON));

        TranscriptionView result = client.transcribe(
                new MockMultipartFile("audio", "recording.webm", "audio/webm;codecs=opus", bytes));

        server.verify();
        assertThat(result).isEqualTo(new TranscriptionView("Salut", "ro", 1.25));
    }

    @Test
    void returnsRawSpeechBytes() {
        server.expect(requestTo("http://llm.test/v1/audio/speech"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().json("{\"text\":\"Answer\"}", JsonCompareMode.STRICT))
                .andRespond(withSuccess(new byte[]{1, 2, 3}, MediaType.valueOf("audio/mpeg")));

        VoiceServiceClient.SpeechResult result = client.synthesize("Answer");

        server.verify();
        assertThat(result.data()).containsExactly(1, 2, 3);
        assertThat(result.contentType()).startsWith("audio/mpeg");
    }

    @Test
    void validatesEmptyOversizedAndUnsupportedAudioBeforeNetwork() {
        assertThatThrownBy(() -> client.transcribe(new MockMultipartFile("audio", new byte[0])))
                .isInstanceOf(ResponseStatusException.class)
                .extracting(error -> ((ResponseStatusException) error).getStatusCode().value())
                .isEqualTo(400);
        assertThatThrownBy(() -> client.transcribe(new MockMultipartFile(
                "audio", "recording.bin", "application/octet-stream",
                new byte[(int) VoiceServiceClient.MAX_AUDIO_BYTES + 1])))
                .isInstanceOf(ResponseStatusException.class)
                .extracting(error -> ((ResponseStatusException) error).getStatusCode().value())
                .isEqualTo(413);
        assertThatThrownBy(() -> client.transcribe(new MockMultipartFile(
                "audio", "recording.bin", "application/octet-stream", new byte[]{1})))
                .isInstanceOf(ResponseStatusException.class)
                .extracting(error -> ((ResponseStatusException) error).getStatusCode().value())
                .isEqualTo(415);
    }

    @Test
    void preservesSafeProviderStatusAndDetail() {
        server.expect(requestTo("http://llm.test/v1/audio/speech"))
                .andRespond(withStatus(HttpStatus.TOO_MANY_REQUESTS)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"detail\":\"The speech provider is rate limited\"}"));

        assertThatThrownBy(() -> client.synthesize("Answer"))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> {
                    var response = (ResponseStatusException) error;
                    assertThat(response.getStatusCode().value()).isEqualTo(429);
                    assertThat(response.getReason()).isEqualTo("The speech provider is rate limited");
                });
    }
}
