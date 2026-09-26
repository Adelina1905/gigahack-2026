import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ChatMessage } from "../types/chat";

export type VoicePhase =
  | "idle"
  | "requesting"
  | "listening"
  | "transcribing"
  | "waiting"
  | "generating"
  | "speaking";

export type VoiceError =
  | "unsupported"
  | "permissionDenied"
  | "noSpeech"
  | "recordingFailed"
  | "transcriptionFailed"
  | "speechFailed"
  | "autoplayBlocked";

export type SpeechState = "idle" | "loading" | "playing" | "blocked" | "error";

interface UseVoiceModeOptions {
  chatId: string | null;
  messages: ChatMessage[];
  onSend: (text: string) => string | null;
}

const CALIBRATION_MS = 500;
const SILENCE_MS = 1400;
const NO_SPEECH_MS = 10_000;
const MAX_RECORDING_MS = 60_000;
const SAMPLE_MS = 50;

const chooseMimeType = () => {
  const candidates = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"];
  return candidates.find(type => MediaRecorder.isTypeSupported(type)) ?? "";
};

const extensionFor = (mimeType: string) => {
  const type = mimeType.toLowerCase();
  if (type.includes("mp4")) return "mp4";
  if (type.includes("ogg")) return "ogg";
  if (type.includes("wav")) return "wav";
  if (type.includes("mpeg") || type.includes("mp3")) return "mp3";
  if (type.includes("aac")) return "aac";
  if (type.includes("flac")) return "flac";
  return "webm";
};

export function useVoiceMode({ chatId, messages, onSend }: UseVoiceModeOptions) {
  const [enabled, setEnabled] = useState(false);
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [error, setError] = useState<VoiceError | null>(null);
  const [level, setLevel] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [speech, setSpeech] = useState<{ key: string | null; state: SpeechState }>({ key: null, state: "idle" });

  const enabledRef = useRef(false);
  const onSendRef = useRef(onSend);
  const chatIdRef = useRef(chatId);
  const previousChatIdRef = useRef(chatId);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const sampleTimerRef = useRef<number | null>(null);
  const elapsedTimerRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const processRecordingRef = useRef(false);
  const transcriptionTokenRef = useRef(0);
  const pendingRequestRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioKeyRef = useRef<string | null>(null);
  const audioUrlsRef = useRef(new Map<string, string>());
  const playbackTokenRef = useRef(0);

  useEffect(() => { onSendRef.current = onSend; chatIdRef.current = chatId; });

  const clearCaptureResources = useCallback(() => {
    if (sampleTimerRef.current !== null) window.clearInterval(sampleTimerRef.current);
    if (elapsedTimerRef.current !== null) window.clearInterval(elapsedTimerRef.current);
    sampleTimerRef.current = null;
    elapsedTimerRef.current = null;
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    const context = contextRef.current;
    contextRef.current = null;
    if (context && context.state !== "closed") void context.close();
    recorderRef.current = null;
    setLevel(0);
    setElapsedSeconds(0);
  }, []);

  const stopPlayback = useCallback(() => {
    playbackTokenRef.current += 1;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    audioKeyRef.current = null;
    setSpeech({ key: null, state: "idle" });
    setPhase(current => current === "speaking" || current === "generating" ? "idle" : current);
  }, []);

  const stopRecording = useCallback((process: boolean) => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    processRecordingRef.current = process;
    recorder.stop();
  }, []);

  const cancelRecording = useCallback(() => {
    stopRecording(false);
    if (!recorderRef.current || recorderRef.current.state === "inactive") {
      clearCaptureResources();
      setPhase("idle");
    }
  }, [clearCaptureResources, stopRecording]);

  const playMessage = useCallback(async (message: ChatMessage, automatic = false) => {
    const activeChatId = chatIdRef.current;
    const responseId = Number(message.id);
    if (!activeChatId || !Number.isInteger(responseId) || !message.content) return;
    stopPlayback();
    const key = `${activeChatId}:${message.id}:${message.generationVersion ?? 0}`;
    const token = playbackTokenRef.current;
    setSpeech({ key, state: "loading" });
    if (automatic) setPhase("generating");
    try {
      let url = audioUrlsRef.current.get(key);
      if (!url) {
        const blob = await api.getResponseSpeech(activeChatId, responseId);
        if (token !== playbackTokenRef.current) return;
        url = URL.createObjectURL(blob);
        audioUrlsRef.current.set(key, url);
      }
      if (token !== playbackTokenRef.current || (automatic && !enabledRef.current)) return;
      const player = new Audio(url);
      audioRef.current = player;
      audioKeyRef.current = key;
      player.onended = () => {
        if (audioKeyRef.current !== key) return;
        audioRef.current = null;
        audioKeyRef.current = null;
        setSpeech({ key, state: "idle" });
        if (automatic) setPhase("idle");
      };
      player.onerror = () => {
        if (audioKeyRef.current !== key) return;
        audioRef.current = null;
        audioKeyRef.current = null;
        setSpeech({ key, state: "error" });
        setError("speechFailed");
        if (automatic) setPhase("idle");
      };
      try {
        await player.play();
        if (token !== playbackTokenRef.current) return;
        setSpeech({ key, state: "playing" });
        if (automatic) setPhase("speaking");
      } catch {
        audioRef.current = null;
        audioKeyRef.current = null;
        setSpeech({ key, state: "blocked" });
        setError(automatic ? "autoplayBlocked" : "speechFailed");
        if (automatic) setPhase("idle");
      }
    } catch {
      if (token !== playbackTokenRef.current) return;
      setSpeech({ key, state: "error" });
      setError("speechFailed");
      if (automatic) setPhase("idle");
    }
  }, [stopPlayback]);

  const startRecording = useCallback(async () => {
    setError(null);
    stopPlayback();
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined"
        || typeof AudioContext === "undefined") {
      setError("unsupported");
      return;
    }
    setPhase("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      if (!enabledRef.current) {
        stream.getTracks().forEach(track => track.stop());
        setPhase("idle");
        return;
      }
      const mimeType = chooseMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);

      recorderRef.current = recorder;
      streamRef.current = stream;
      contextRef.current = context;
      chunksRef.current = [];
      processRecordingRef.current = false;
      const samples = new Float32Array(analyser.fftSize);
      const startedAt = performance.now();
      let noiseFloor = Number.POSITIVE_INFINITY;
      let threshold = 0.015;
      let loudSamples = 0;
      let heardSpeech = false;
      let silenceStartedAt: number | null = null;

      recorder.ondataavailable = event => { if (event.data.size > 0) chunksRef.current.push(event.data); };
      recorder.onerror = () => {
        processRecordingRef.current = false;
        setError("recordingFailed");
        if (recorder.state !== "inactive") recorder.stop();
        else { clearCaptureResources(); setPhase("idle"); }
      };
      recorder.onstop = () => {
        const shouldProcess = processRecordingRef.current;
        const chunks = chunksRef.current;
        const recordedType = recorder.mimeType || chunks[0]?.type || mimeType || "audio/webm";
        clearCaptureResources();
        if (!shouldProcess || !enabledRef.current) {
          setPhase("idle");
          return;
        }
        const blob = new Blob(chunks, { type: recordedType });
        if (!blob.size) {
          setError("recordingFailed");
          setPhase("idle");
          return;
        }
        const transcriptionToken = ++transcriptionTokenRef.current;
        setPhase("transcribing");
        void api.transcribeAudio(blob, extensionFor(recordedType)).then(result => {
          if (transcriptionToken !== transcriptionTokenRef.current || !enabledRef.current) return;
          const requestId = onSendRef.current(result.text);
          if (!requestId) {
            setError("transcriptionFailed");
            setPhase("idle");
            return;
          }
          pendingRequestRef.current = requestId;
          setPhase("waiting");
        }).catch(() => {
          if (transcriptionToken !== transcriptionTokenRef.current) return;
          setError("transcriptionFailed");
          setPhase("idle");
        });
      };

      recorder.start(250);
      setPhase("listening");
      setElapsedSeconds(0);
      elapsedTimerRef.current = window.setInterval(() => {
        setElapsedSeconds(Math.floor((performance.now() - startedAt) / 1000));
      }, 250);
      sampleTimerRef.current = window.setInterval(() => {
        const now = performance.now();
        analyser.getFloatTimeDomainData(samples);
        let sum = 0;
        for (const sample of samples) sum += sample * sample;
        const rms = Math.sqrt(sum / samples.length);
        if (now - startedAt < CALIBRATION_MS) {
          noiseFloor = Math.min(noiseFloor, rms);
          setLevel(Math.min(1, rms / 0.08));
          return;
        }
        if (Number.isFinite(noiseFloor)) threshold = Math.max(0.015, noiseFloor * 2.5);
        setLevel(Math.min(1, rms / Math.max(threshold * 3, 0.04)));
        if (rms >= threshold) {
          loudSamples += 1;
          silenceStartedAt = null;
          if (loudSamples >= 3) heardSpeech = true;
        } else {
          loudSamples = 0;
          if (heardSpeech) silenceStartedAt ??= now;
        }
        if (heardSpeech && silenceStartedAt !== null && now - silenceStartedAt >= SILENCE_MS) {
          stopRecording(true);
        } else if (!heardSpeech && now - startedAt >= NO_SPEECH_MS) {
          setError("noSpeech");
          stopRecording(false);
        } else if (now - startedAt >= MAX_RECORDING_MS) {
          stopRecording(heardSpeech);
        }
      }, SAMPLE_MS);
    } catch (failure) {
      clearCaptureResources();
      const denied = failure instanceof DOMException && ["NotAllowedError", "SecurityError"].includes(failure.name);
      setError(denied ? "permissionDenied" : "recordingFailed");
      setPhase("idle");
    }
  }, [clearCaptureResources, stopPlayback, stopRecording]);

  const toggleEnabled = useCallback(() => {
    setEnabled(current => {
      const next = !current;
      enabledRef.current = next;
      if (!next) {
        transcriptionTokenRef.current += 1;
        pendingRequestRef.current = null;
        cancelRecording();
        stopPlayback();
        setError(null);
        setPhase("idle");
      }
      return next;
    });
  }, [cancelRecording, stopPlayback]);

  const toggleRecording = useCallback(() => {
    if (phase === "listening") stopRecording(true);
    else if (phase === "idle" && enabled) void startRecording();
  }, [enabled, phase, startRecording, stopRecording]);

  const toggleSpeech = useCallback((message: ChatMessage) => {
    const activeChatId = chatIdRef.current;
    const key = activeChatId ? `${activeChatId}:${message.id}:${message.generationVersion ?? 0}` : null;
    if (key && audioKeyRef.current === key && speech.state === "playing") stopPlayback();
    else void playMessage(message, false);
  }, [playMessage, speech.state, stopPlayback]);

  const speechStateFor = useCallback((message: ChatMessage): SpeechState => {
    const activeChatId = chatIdRef.current;
    const key = activeChatId ? `${activeChatId}:${message.id}:${message.generationVersion ?? 0}` : null;
    return key && speech.key === key ? speech.state : "idle";
  }, [speech]);

  useEffect(() => {
    const requestId = pendingRequestRef.current;
    if (!requestId || !enabled) return;
    const response = messages.find(message => message.role === "assistant" && message.requestId === requestId);
    if (!response || response.generationStatus === "PENDING") return;
    pendingRequestRef.current = null;
    if (response.generationStatus === "COMPLETED" && response.content) void playMessage(response, true);
    else setPhase("idle");
  }, [enabled, messages, playMessage]);

  useEffect(() => {
    const previous = previousChatIdRef.current;
    previousChatIdRef.current = chatId;
    if (previous !== null && previous !== chatId) {
      transcriptionTokenRef.current += 1;
      pendingRequestRef.current = null;
      cancelRecording();
      stopPlayback();
      setPhase("idle");
    }
  }, [cancelRecording, chatId, stopPlayback]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && phase === "listening") cancelRecording();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [cancelRecording, phase]);

  useEffect(() => () => {
    enabledRef.current = false;
    transcriptionTokenRef.current += 1;
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      processRecordingRef.current = false;
      recorder.stop();
    }
    clearCaptureResources();
    stopPlayback();
    for (const url of audioUrlsRef.current.values()) URL.revokeObjectURL(url);
    audioUrlsRef.current.clear();
  }, [clearCaptureResources, stopPlayback]);

  return {
    enabled,
    phase,
    error,
    level,
    elapsedSeconds,
    toggleEnabled,
    toggleRecording,
    cancelRecording,
    dismissError: () => setError(null),
    toggleSpeech,
    speechStateFor,
  };
}
