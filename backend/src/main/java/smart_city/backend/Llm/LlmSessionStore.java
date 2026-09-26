package smart_city.backend.Llm;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import smart_city.backend.Llm.dto.LlmTurn;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.locks.ReentrantLock;

/**
 * In-memory conversation history for ephemeral LLM chats.
 * Nothing here is persisted; idle sessions are evicted after the TTL.
 */
@Component
public class LlmSessionStore {

    private final ConcurrentMap<UUID, Session> sessions =
            new ConcurrentHashMap<>();
    private final Duration sessionTtl;
    private final int maxHistory;
    private final Clock clock;

    public LlmSessionStore(
            LlmProperties properties,
            Clock clock
    ) {
        this.sessionTtl = properties.sessionTtl();
        this.maxHistory = properties.maxHistory();
        this.clock = clock;
    }

    /**
     * Returns the chat's session with its lock held by the caller.
     * The caller must call {@link Session#release()} when done.
     */
    public Session acquire(UUID chatId) {
        while (true) {
            Session session = sessions.computeIfAbsent(
                    chatId,
                    id -> new Session()
            );
            session.lock.lock();

            // Eviction may have removed the session before we got the lock.
            if (sessions.get(chatId) == session) {
                session.touch();
                return session;
            }

            session.lock.unlock();
        }
    }

    public void clear(UUID chatId) {
        sessions.remove(chatId);
    }

    public int size() {
        return sessions.size();
    }

    @Scheduled(fixedDelay = 60_000)
    public void evictExpired() {
        Instant cutoff = clock.instant().minus(sessionTtl);

        sessions.forEach((chatId, session) -> {
            // Skip sessions that are busy with an in-flight turn.
            if (!session.lock.tryLock()) {
                return;
            }
            try {
                if (session.lastAccess.isBefore(cutoff)) {
                    sessions.remove(chatId, session);
                }
            } finally {
                session.lock.unlock();
            }
        });
    }

    public final class Session {

        private final ReentrantLock lock = new ReentrantLock();
        private final Deque<LlmTurn> history = new ArrayDeque<>();
        private Instant lastAccess = clock.instant();

        private Session() {
        }

        public List<LlmTurn> history() {
            return List.copyOf(history);
        }

        public void append(LlmTurn turn) {
            history.addLast(turn);
            while (history.size() > maxHistory) {
                history.removeFirst();
            }
        }

        public void release() {
            touch();
            lock.unlock();
        }

        private void touch() {
            lastAccess = clock.instant();
        }
    }
}
