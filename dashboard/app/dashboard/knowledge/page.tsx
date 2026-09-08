"use client";

import { useEffect, useRef, useState } from "react";
import { api, KnowledgeDocument, APIError } from "@/lib/api";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

function statusLabel(doc: KnowledgeDocument): { text: string; className: string } {
  if (doc.status === "ready") return { text: `Ready · ${doc.chunk_count} chunks`, className: "text-success" };
  if (doc.status === "failed") return { text: doc.error || "Failed", className: "text-danger" };
  return { text: "Processing…", className: "text-muted" };
}

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteContent, setPasteContent] = useState("");
  const [showPasteForm, setShowPasteForm] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      setDocuments(await api.listKnowledgeDocuments());
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to load documents.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.uploadKnowledgeDocument(file);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Upload failed.");
    } finally {
      setSubmitting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handlePasteSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!pasteTitle.trim() || !pasteContent.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createKnowledgeTextDocument(pasteTitle.trim(), pasteContent);
      setPasteTitle("");
      setPasteContent("");
      setShowPasteForm(false);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to save.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteKnowledgeDocument(id);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to delete.");
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-1">Knowledge</h1>
      <p className="text-muted mb-6">
        Upload notes or documents so the assistant can search them when you ask (e.g. &ldquo;what does my lease
        say about pets?&rdquo;). This is keyword-based search, not general knowledge — if you haven&apos;t
        uploaded something covering a topic, it won&apos;t know it.
      </p>

      {error && (
        <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2 mb-4">{error}</p>
      )}

      <div className="card flex flex-wrap gap-3 items-center mb-6">
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.markdown,.csv"
          onChange={handleFileChange}
          disabled={submitting}
          className="hidden"
          id="knowledge-file-input"
        />
        <label htmlFor="knowledge-file-input" className={`btn-primary cursor-pointer ${submitting ? "opacity-60 pointer-events-none" : ""}`}>
          {submitting ? "Uploading…" : "Upload file"}
        </label>
        <span className="text-xs text-muted">.txt, .md, or .csv — PDF/DOCX aren&apos;t supported yet</span>
        <button
          type="button"
          onClick={() => setShowPasteForm((v) => !v)}
          className="btn-secondary ml-auto"
        >
          {showPasteForm ? "Cancel" : "Paste text instead"}
        </button>
      </div>

      {showPasteForm && (
        <form onSubmit={handlePasteSubmit} className="card space-y-3 mb-6">
          <div className="space-y-1">
            <label htmlFor="pasteTitle" className="text-sm text-muted">
              Title
            </label>
            <input
              id="pasteTitle"
              value={pasteTitle}
              onChange={(e) => setPasteTitle(e.target.value)}
              className="input-field w-full"
              placeholder="Apartment lease notes"
              required
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="pasteContent" className="text-sm text-muted">
              Content
            </label>
            <textarea
              id="pasteContent"
              value={pasteContent}
              onChange={(e) => setPasteContent(e.target.value)}
              className="input-field w-full min-h-[160px]"
              placeholder="Paste text here…"
              required
            />
          </div>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? "Saving…" : "Save"}
          </button>
        </form>
      )}

      {documents === null ? (
        <p className="text-muted text-sm">Loading…</p>
      ) : documents.length === 0 ? (
        <p className="text-muted text-sm">Nothing uploaded yet.</p>
      ) : (
        <div className="space-y-2">
          {documents.map((doc) => {
            const status = statusLabel(doc);
            return (
              <div key={doc.id} className="card flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="font-medium truncate">{doc.title}</p>
                  <p className={`text-xs font-mono ${status.className}`}>{status.text}</p>
                  <p className="text-xs text-muted">{formatDate(doc.created_at)}</p>
                </div>
                <button onClick={() => handleDelete(doc.id)} className="btn-danger text-sm shrink-0">
                  Delete
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
