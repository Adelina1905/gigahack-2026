package smart_city.backend.Llm;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import smart_city.backend.Llm.dto.LlmCitation;
import smart_city.backend.Llm.dto.LlmReply;
import smart_city.backend.config.SecurityConfig;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(LlmController.class)
@Import({
        SecurityConfig.class,
        LlmChatService.class,
        LlmSessionStore.class,
        LlmControllerTest.Fakes.class
})
class LlmControllerTest {

    private static final String CHAT_ID =
            "11111111-2222-3333-4444-555555555555";

    @TestConfiguration
    static class Fakes {

        @Bean
        RecordingLlmGateway llmGateway() {
            return new RecordingLlmGateway();
        }

        @Bean
        Clock clock() {
            return new MutableClock(Instant.parse("2026-01-01T10:00:00Z"));
        }

        @Bean
        LlmProperties llmProperties() {
            return new LlmProperties(
                    "http://unused",
                    Duration.ofSeconds(1),
                    Duration.ofSeconds(1),
                    Duration.ofMinutes(30),
                    20
            );
        }
    }

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private RecordingLlmGateway gateway;

    @Test
    void returnsMappedReply() throws Exception {
        gateway.setFailing(false);
        gateway.replyWith(new LlmReply(
                "rag",
                "SUPPORTED",
                "Raspuns",
                List.of(new LlmCitation(null, "https://x", "q", "doc-9")),
                null
        ));

        mockMvc.perform(post("/api/llm/chats/" + CHAT_ID + "/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\": \"salut\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.chatId").value(CHAT_ID))
                .andExpect(jsonPath("$.text").value("Raspuns"))
                .andExpect(jsonPath("$.mode").value("rag"))
                .andExpect(jsonPath("$.status").value("SUPPORTED"))
                .andExpect(jsonPath("$.sources[0].title").value("doc-9"))
                .andExpect(jsonPath("$.sources[0].link").value("https://x"))
                .andExpect(jsonPath("$.sources[0].quote").value("q"))
                .andExpect(jsonPath("$.createdAt").value("2026-01-01T10:00:00Z"));
    }

    @Test
    void returns503WhenServiceDown() throws Exception {
        gateway.setFailing(true);

        mockMvc.perform(post("/api/llm/chats/" + CHAT_ID + "/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\": \"salut\"}"))
                .andExpect(status().isServiceUnavailable());
    }

    @Test
    void rejectsBlankText() throws Exception {
        mockMvc.perform(post("/api/llm/chats/" + CHAT_ID + "/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\": \"   \"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsTooLongText() throws Exception {
        String text = "a".repeat(8001);
        mockMvc.perform(post("/api/llm/chats/" + CHAT_ID + "/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\": \"" + text + "\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidChatId() throws Exception {
        mockMvc.perform(post("/api/llm/chats/not-a-uuid/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\": \"salut\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void deleteReturnsNoContent() throws Exception {
        mockMvc.perform(delete("/api/llm/chats/" + CHAT_ID))
                .andExpect(status().isNoContent());
        mockMvc.perform(delete("/api/llm/chats/" + CHAT_ID))
                .andExpect(status().isNoContent());
    }
}
