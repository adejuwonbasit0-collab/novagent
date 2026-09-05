"use client";

import { useEffect, useRef, useState } from "react";
import { api, VoiceSample, VoiceProfile, APIError } from "@/lib/api";

const TONE_PRESETS = [
  { value: "warm", label: "Warm", description: "Friendly, approachable delivery" },
  { value: "professional", label: "Professional", description: "Steady, measured, formal" },
  { value: "energetic", label: "Energetic", description: "Upbeat, expressive, faster-feeling" },
  { value: "calm", label: "Calm", description: "Slow, soothing, minimal variation" },
  { value: "custom", label: "Custom", description: "Fine-tune the sliders yourself" },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function VoicePage() {
  const [samples, setSamples] = useState<VoiceSample[] | null>(null);
  const [profile, setProfile] = useState<VoiceProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [training, setTraining] = useState(false);
  const [consent, setConsent] = useState(false);
  const [voiceName, setVoiceName] = useState("My Voice");
  const [previewText, setPreviewText] = useState("Hello, this is a preview of my trained voice.");
  const [previewing, setPreviewing] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const [s, p] = await Promise.all([api.listVoiceSamples(), api.getVoiceProfile()]);
      setSamples(s);
      setProfile(p);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to load voice data.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadVoiceSample(file);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser does not support microphone recording.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      recordedChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) recordedChunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
        const blob = new Blob(recordedChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        setUploading(true);
        try {
          const extension = recorder.mimeType.includes("mp4") ? "m4a" : "webm";
          await api.uploadVoiceSample(new File([blob], `recording-${Date.now()}.${extension}`, { type: blob.type }));
          await load();
        } catch (err) {
          setError(err instanceof APIError ? err.message : "Recording upload failed.");
        } finally {
          setUploading(false);
        }
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
      setRecordingSeconds(0);
      recordingTimerRef.current = setInterval(() => setRecordingSeconds((value) => value + 1), 1000);
    } catch {
      setError("Microphone permission was denied or unavailable.");
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setRecording(false);
  }

  async function handleDeleteSample(id: string) {
    try {
      await api.deleteVoiceSample(id);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to delete sample.");
    }
  }

  async function handleTrain() {
    if (!consent) {
      setError("You need to confirm consent before training a voice from your samples.");
      return;
    }
    setTraining(true);
    setError(null);
    try {
      await api.trainVoice(voiceName, true);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Training failed.");
    } finally {
      setTraining(false);
    }
  }

  async function handleToneChange(tone: string) {
    try {
      const updated = await api.updateVoiceTone(tone, {
        stability: profile?.custom_stability,
        similarity: profile?.custom_similarity,
        style: profile?.custom_style,
      });
      setProfile(updated);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to update tone.");
    }
  }

  async function handleCustomSliderChange(field: "stability" | "similarity" | "style", value: number) {
    try {
      const updated = await api.updateVoiceTone("custom", { [field]: value });
      setProfile(updated);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to update tone.");
    }
  }

  async function handlePreview() {
    setPreviewing(true);
    setError(null);
    try {
      const blob = await api.synthesizeSpeech(previewText);
      const url = URL.createObjectURL(blob);
      if (audioRef.current) {
        audioRef.current.src = url;
        await audioRef.current.play();
      }
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Preview failed.");
    } finally {
      setPreviewing(false);
    }
  }

  const untrainedSamples = samples?.filter((s) => s.status === "uploaded") ?? [];
  const isReady = profile?.status === "ready";

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-1">Voice</h1>
      <p className="text-muted mb-6">
        This page trains Nova&apos;s spoken reply voice. It does not teach Nova to understand your
        voice; desktop listening uses the microphone and speech-to-text controls in the desktop agent.
      </p>

      {error && (
        <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2 mb-4">
          {error}
        </p>
      )}

      {/* Provider notice */}
      <div className="card mb-6 border-pending/40">
        <p className="text-sm text-pending font-medium mb-1">Voice output provider: mock (default)</p>
        <p className="text-xs text-muted">
          Without a real voice-cloning provider configured on the backend (e.g.
          <code className="font-mono"> VOICE_PROVIDER=elevenlabs</code> + an API key), training and
          preview use a stand-in that proves the whole pipeline works but does not produce your
          actual voice — the audio you&apos;ll hear below is silent. See{" "}
          <code className="font-mono">backend/README.md</code> for how to connect a real provider.
        </p>
      </div>

      {/* Samples */}
      <div className="card mb-4">
        <div className="flex items-center justify-between mb-3">
          <p className="font-medium text-sm">Voice samples</p>
          <label className="btn-secondary text-sm cursor-pointer">
            {uploading ? "Uploading…" : "Upload sample"}
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*"
              onChange={handleUpload}
              disabled={uploading}
              className="hidden"
            />
          </label>
          {recording ? (
            <button type="button" onClick={stopRecording} className="btn-danger text-sm ml-2">
              Stop recording ({recordingSeconds}s)
            </button>
          ) : (
            <button type="button" onClick={startRecording} disabled={uploading} className="btn-secondary text-sm ml-2">
              Record from microphone
            </button>
          )}
        </div>

        {samples === null ? (
          <p className="text-muted text-sm">Loading…</p>
        ) : samples.length === 0 ? (
          <p className="text-muted text-sm">
            No samples yet. Upload a few short recordings of your own voice (WAV works best) to
            train from.
          </p>
        ) : (
          <div className="space-y-2">
            {samples.map((s) => (
              <div key={s.id} className="flex items-center justify-between text-sm">
                <div className="min-w-0">
                  <span className="truncate">{s.original_filename}</span>
                  <span className="text-muted text-xs ml-2">
                    {s.duration_seconds ? `${s.duration_seconds.toFixed(1)}s · ` : ""}
                    {formatBytes(s.size_bytes)} · {s.status}
                  </span>
                </div>
                <button onClick={() => handleDeleteSample(s.id)} className="text-danger text-xs shrink-0 ml-2">
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Train */}
      <div className="card mb-4">
        <p className="font-medium text-sm mb-3">
          Train a voice {profile && `— currently ${profile.status}`}
        </p>

        <input
          value={voiceName}
          onChange={(e) => setVoiceName(e.target.value)}
          className="input-field w-full mb-3"
          placeholder="Voice name"
        />

        <label className="flex items-start gap-2 text-xs text-muted mb-3">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5" />
          <span>
            I consent to Nova using my uploaded voice samples to create a synthetic version of my
            voice for this assistant.
          </span>
        </label>

        <button
          onClick={handleTrain}
          disabled={training || untrainedSamples.length === 0 || !consent}
          className="btn-primary text-sm"
        >
          {training ? "Training…" : `Train from ${untrainedSamples.length} sample${untrainedSamples.length === 1 ? "" : "s"}`}
        </button>

        {profile?.status === "failed" && (
          <p className="text-danger text-xs mt-2">Last attempt failed: {profile.failure_reason}</p>
        )}
      </div>

      {/* Tone */}
      {isReady && (
        <div className="card mb-4">
          <p className="font-medium text-sm mb-3">Tone</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3">
            {TONE_PRESETS.map((t) => (
              <button
                key={t.value}
                onClick={() => handleToneChange(t.value)}
                className={`text-left p-2 rounded border text-xs ${
                  profile?.tone_preset === t.value
                    ? "border-accent bg-accent/10"
                    : "border-border hover:border-accent/50"
                }`}
              >
                <p className="font-medium">{t.label}</p>
                <p className="text-muted mt-0.5">{t.description}</p>
              </button>
            ))}
          </div>

          {profile?.tone_preset === "custom" && (
            <div className="space-y-3 pt-2 border-t border-border">
              <SliderRow
                label="Stability"
                value={profile.custom_stability}
                onChange={(v) => handleCustomSliderChange("stability", v)}
              />
              <SliderRow
                label="Similarity"
                value={profile.custom_similarity}
                onChange={(v) => handleCustomSliderChange("similarity", v)}
              />
              <SliderRow
                label="Style / expressiveness"
                value={profile.custom_style}
                onChange={(v) => handleCustomSliderChange("style", v)}
              />
            </div>
          )}
        </div>
      )}

      {/* Preview */}
      {isReady && (
        <div className="card">
          <p className="font-medium text-sm mb-3">Preview</p>
          <textarea
            value={previewText}
            onChange={(e) => setPreviewText(e.target.value)}
            className="input-field w-full mb-3 h-20 resize-none"
          />
          <button onClick={handlePreview} disabled={previewing} className="btn-primary text-sm">
            {previewing ? "Generating…" : "Play preview"}
          </button>
          <audio ref={audioRef} className="w-full mt-3" controls />
        </div>
      )}
    </div>
  );
}

function SliderRow({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-muted mb-1">
        <span>{label}</span>
        <span>{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full"
      />
    </div>
  );
}
