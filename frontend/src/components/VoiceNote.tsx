import { useEffect, useRef, useState } from "react";
import { readVoiceNote, VOICE_MAX_BYTES, VOICE_TYPES, type VoiceNoteCheck } from "../fleetApi";
import { Stamp } from "./Stamp";

// P2a: someone records or uploads a short note about a machine problem; Gemini hears it, code checks it. Nothing is saved.
const MAX_SECONDS = 60;
const RECORD_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
const ISSUES = { hydraulic: "Hydraulics", tyres: "Tyres", engine: "Engine", electrical: "Electrical", other: "Other" };
const SEVERITY = { high: "High: do not use until fixed", medium: "Medium: fix within days", low: "Low: when convenient" };

function recordType(): string | undefined {
  return RECORD_TYPES.find((t) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t));
}

export function VoiceNote() {
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [result, setResult] = useState<VoiceNoteCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const running = useRef<AbortController | null>(null);
  const canRecord = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && !!recordType();

  useEffect(
    () => () => {
      running.current?.abort();
      window.clearTimeout(timer.current);
      if (recorder.current?.state === "recording") recorder.current.stop();
    },
    [],
  );

  const send = async (audio: Blob) => {
    setResult(null);
    setError(null);
    if (!VOICE_TYPES.includes(audio.type.split(";")[0])) return setError("Only a voice recording (WebM, Ogg, M4A, MP3 or WAV) can be read.");
    if (audio.size > VOICE_MAX_BYTES) return setError("The recording is over 2 MB (about a minute). Please record a shorter note.");
    running.current?.abort();
    const ac = new AbortController();
    running.current = ac;
    setBusy(true);
    try {
      setResult(await readVoiceNote(audio, ac.signal));
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : "The voice note could not be read.");
    } finally {
      if (!ac.signal.aborted) setBusy(false);
    }
  };

  const start = async () => {
    setResult(null);
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      return setError("The microphone could not be used. Allow it in the browser, or upload a recording instead.");
    }
    const mime = recordType();
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const parts: Blob[] = [];
    rec.ondataavailable = (e) => e.data.size && parts.push(e.data);
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      window.clearTimeout(timer.current);
      setRecording(false);
      void send(new Blob(parts, { type: rec.mimeType || mime || "audio/webm" }));
    };
    recorder.current = rec;
    rec.start();
    setRecording(true);
    timer.current = window.setTimeout(() => rec.state === "recording" && rec.stop(), MAX_SECONDS * 1000);
  };

  return (
    <div className="rounded-3xl border-2 border-ink p-4 sm:p-6">
      <h3 className="font-display text-2xl font-semibold">Report a machine problem by voice</h3>
      <p className="mt-2 max-w-[70ch] text-ink-soft">
        Say which machine, what is wrong and when it should be fixed, in up to a minute. Gemini listens and fills in a note; code checks the machine
        against the fleet list. Nothing is saved: not the recording, not the note.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        {canRecord && (
          <button
            onClick={() => (recording ? recorder.current?.stop() : void start())}
            disabled={busy}
            aria-pressed={recording}
            className={`min-h-11 border-2 border-ink px-5 font-bold disabled:opacity-60 ${recording ? "bg-ink text-paper" : "btn-outline"}`}
          >
            {recording ? "Stop and read the note" : "Record a voice note"}
          </button>
        )}
        <label className="flex flex-col gap-2 text-sm font-bold">
          {canRecord ? "Or upload a recording" : "Upload a recording"} (WebM, Ogg, M4A, MP3 or WAV, up to 2 MB)
          <input
            type="file"
            accept={VOICE_TYPES.join(",")}
            disabled={busy || recording}
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = ""; // the same recording can be sent again
              if (f) void send(f);
            }}
            className="min-h-11 max-w-full border-2 border-ink bg-paper p-2 font-normal file:mr-3 file:min-h-9 file:border-0 file:bg-ink file:px-3 file:font-bold file:text-paper disabled:opacity-60"
          />
        </label>
      </div>

      <div role="status" aria-live="polite" className="mt-4 font-mono text-xs uppercase tracking-widest text-ink-soft">
        {recording && `Recording... press Stop when you are done (it stops by itself after ${MAX_SECONDS} seconds).`}
        {busy && "Listening to the note... this can take up to a minute."}
        {result && !busy && (result.status === "ready" ? "Note ready." : "Note read, but it needs a check.")}
      </div>
      {error && (
        <p role="alert" className="mt-3 max-w-[70ch] rounded-2xl border-2 border-clay p-3 font-bold">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-4 max-w-[70ch]">
          <p className="flex flex-wrap items-center gap-3 text-lg font-bold">
            <span>
              <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">Status: </span>
              {result.status === "ready" ? "Ready" : "Needs a check"}
            </span>
            <Stamp label={result.label} />
            <span className="text-sm font-normal text-ink-soft">{result.label_note}</span>
          </p>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            <dt className="font-bold">Machine</dt>
            <dd>{result.note.site ? `${result.note.machine}, ${result.note.site}` : result.note.machine}</dd>
            <dt className="font-bold">Problem</dt>
            <dd>{result.note.issue ? ISSUES[result.note.issue] : "Not clear"}</dd>
            <dt className="font-bold">Severity</dt>
            <dd>{result.note.severity ? SEVERITY[result.note.severity] : "Not clear"}</dd>
            <dt className="font-bold">Follow-up</dt>
            <dd>{result.note.follow_up || "None heard"}</dd>
            <dt className="font-bold">Gemini's confidence</dt>
            <dd>{result.note.confidence}</dd>
            <dt className="font-bold">What was heard</dt>
            <dd className="italic">{result.note.transcript || "Nothing"}</dd>
          </dl>
          {result.reasons.length > 0 && (
            <ul className="mt-3 list-disc pl-6">
              {result.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-sm text-ink-soft">
            Not saved anywhere. {result.usage && `Gemini used ${result.usage.total_tokens.toLocaleString("en-GB")} tokens to hear it. `}Source:{" "}
            {result.data_source}
          </p>
        </div>
      )}
    </div>
  );
}
