package smart_city.backend.Alert;

import java.util.UUID;

/** What an alert subscription follows: a project (all its chats) or a single chat. Exactly one id is set. */
public record AlertScope(
        UUID projectId,
        UUID chatId
) {

    public AlertScope {
        if ((projectId == null) == (chatId == null)) {
            throw new IllegalArgumentException("An alert scope is either a project or a chat");
        }
    }

    public static AlertScope project(UUID projectId) {
        return new AlertScope(projectId, null);
    }

    public static AlertScope chat(UUID chatId) {
        return new AlertScope(null, chatId);
    }

    public boolean isProject() {
        return projectId != null;
    }
}
