import { beforeEach, describe, expect, it } from "vitest";
import * as mockClient from "../src/api/mockClient";

describe("offline source preview examples", () => {
  beforeEach(() => localStorage.clear());

  it("returns cited sample documents without the backend", async () => {
    const chat = await mockClient.createChat("Schools");
    const response = await mockClient.createResponse(chat.id, "Cum au fost evaluate instituțiile de educație?");
    const citation = response.aiReply?.citations[0];

    expect(citation?.documentId).toBe("school-evaluation-2024");
    const preview = await mockClient.getSourcePreview(citation!.documentId!, {
      versionId: citation?.versionId,
      focusEvidenceId: citation?.evidenceId,
    });

    expect(preview.focusSectionId).toBe("school-visits");
    expect(preview.sections.some((section) => section.id === "school-visits")).toBe(true);
    expect(preview.sections).toHaveLength(3);
  });
});
