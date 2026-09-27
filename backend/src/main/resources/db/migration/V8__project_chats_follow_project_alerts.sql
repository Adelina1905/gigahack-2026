-- A chat in a project follows the project's alerts: drop the chat's own subscription,
-- with its topics and alerts (ON DELETE CASCADE). Moving a chat into a project does the same.
DELETE FROM alert_subscriptions s
USING chats c
WHERE s.chat_id = c.id
  AND c.project_id IS NOT NULL;
