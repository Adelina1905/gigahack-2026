package smart_city.backend.Llm;

import org.junit.jupiter.api.Test;

import smart_city.backend.Llm.dto.LlmTurn;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class LlmSessionStoreTest {

    private final MutableClock clock =
            new MutableClock(Instant.parse("2026-01-01T00:00:00Z"));

    private LlmSessionStore store(int maxHistory) {
        return new LlmSessionStore(
                new LlmProperties(
                        "http://unused",
                        Duration.ofSeconds(1),
                        Duration.ofSeconds(1),
                        Duration.ofMinutes(30),
                        maxHistory
                ),
                clock
        );
    }

    @Test
    void trimsOldestTurnsBeyondMaxHistory() {
        LlmSessionStore store = store(3);
        UUID chatId = UUID.randomUUID();

        LlmSessionStore.Session session = store.acquire(chatId);
        for (int i = 1; i <= 5; i++) {
            session.append(LlmTurn.user("m" + i));
        }
        session.release();

        LlmSessionStore.Session again = store.acquire(chatId);
        assertThat(again.history())
                .extracting(LlmTurn::content)
                .containsExactly("m3", "m4", "m5");
        again.release();
    }

    @Test
    void evictsSessionsIdleLongerThanTtl() {
        LlmSessionStore store = store(10);
        UUID stale = UUID.randomUUID();
        UUID fresh = UUID.randomUUID();

        LlmSessionStore.Session staleSession = store.acquire(stale);
        staleSession.append(LlmTurn.user("old"));
        staleSession.release();

        clock.advance(Duration.ofMinutes(20));
        store.acquire(fresh).release();

        clock.advance(Duration.ofMinutes(11));
        store.evictExpired();

        assertThat(store.size()).isEqualTo(1);
        LlmSessionStore.Session recreated = store.acquire(stale);
        assertThat(recreated.history()).isEmpty();
        recreated.release();
    }

    @Test
    void keepsSessionsWithinTtlAndClearRemovesThem() {
        LlmSessionStore store = store(10);
        UUID chatId = UUID.randomUUID();

        LlmSessionStore.Session session = store.acquire(chatId);
        session.append(LlmTurn.user("hi"));
        session.release();

        clock.advance(Duration.ofMinutes(29));
        store.evictExpired();
        assertThat(store.size()).isEqualTo(1);

        store.clear(chatId);
        store.clear(chatId);
        assertThat(store.size()).isZero();
    }
}
