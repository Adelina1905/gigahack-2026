import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render as renderRaw, screen, waitFor } from "@testing-library/react";
import AssistantMessage from "../src/components/AssistantMessage";
import { transcribeAudio, getResponseSpeech } from "../src/api/client";
import { useVoiceMode } from "../src/hooks/useVoiceMode";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const render = (ui: React.ReactElement) => renderRaw(
  <I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: MESSAGES.en }}>
    {ui}
  </I18nContext.Provider>,
);

function VoiceHarness() {
  const voice = useVoiceMode({ chatId: null, messages: [], onSend: () => null });
  return <>
    <span data-testid="enabled">{String(voice.enabled)}</span>
    <span data-testid="error">{voice.error ?? "none"}</span>
    <button onClick={voice.toggleEnabled}>toggle</button>
    <button onClick={voice.toggleRecording}>record</button>
  </>;
}

describe("voice mode UI", () => {
  it("starts disabled and reports unsupported capture without changing chat", async () => {
    vi.stubGlobal("MediaRecorder", undefined);
    vi.stubGlobal("AudioContext", undefined);
    render(<VoiceHarness />);

    expect(screen.getByTestId("enabled").textContent).toBe("false");
    fireEvent.click(screen.getByText("toggle"));
    expect(screen.getByTestId("enabled").textContent).toBe("true");
    fireEvent.click(screen.getByText("record"));
    await waitFor(() => expect(screen.getByTestId("error").textContent).toBe("unsupported"));
  });

  it("shows play, loading, and stop labels for assistant speech", () => {
    const message = { id: "5", role: "assistant" as const, content: "Answer", createdAt: 1 };
    const toggle = vi.fn();
    const { rerender } = render(<AssistantMessage message={message} onToggleSpeech={toggle} />);
    fireEvent.click(screen.getByRole("button", { name: "Play response" }));
    expect(toggle).toHaveBeenCalledWith(message);

    rerender(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: MESSAGES.en }}>
      <AssistantMessage message={message} onToggleSpeech={toggle} speechState="playing" />
    </I18nContext.Provider>);
    expect(screen.getByRole("button", { name: "Stop playback" })).toBeTruthy();
  });
});

describe("voice API client", () => {
  it("uploads multipart audio without setting a JSON content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ text: "Salut", language: "ro", durationSeconds: 1 }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    vi.stubGlobal("fetch", fetchMock);

    await expect(transcribeAudio(new Blob(["audio"], { type: "audio/webm" }), "webm"))
      .resolves.toMatchObject({ text: "Salut", language: "ro" });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.headers["Content-Type"]).toBeUndefined();
    expect(options.credentials).toBe("include");
  });

  it("returns speech as a blob", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new Uint8Array([1, 2, 3]), {
      status: 200, headers: { "Content-Type": "audio/mpeg" },
    })));
    const result = await getResponseSpeech("chat", 7);
    expect(result.type).toBe("audio/mpeg");
    expect(result.size).toBe(3);
  });
});
