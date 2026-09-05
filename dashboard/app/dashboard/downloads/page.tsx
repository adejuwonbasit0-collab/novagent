"use client";

interface ClientOption {
  title: string;
  description: string;
  status: "available" | "coming-soon";
  detail: string;
}

const CLIENTS: ClientOption[] = [
  {
    title: "Desktop Agent",
    description:
      "A floating assistant bubble for Windows, macOS, and Linux. Controls apps, files, and your system directly — the only client that can actually act on your machine.",
    status: "available",
    detail: "Requires Python 3.11+. Run `python main.py` after installing — see the desktop-agent README.",
  },
  {
    title: "Browser Extension",
    description:
      "Chat with Nova from any tab. Lightweight — no OS-level control, just conversation and reminders without leaving your browser.",
    status: "available",
    detail: "Chrome/Chromium: open chrome://extensions, enable Developer mode, and Load unpacked.",
  },
  {
    title: "Mobile App",
    description:
      "iOS and Android via Expo. Chat, and reminders, from your phone — the same account, same permissions, same data as everywhere else.",
    status: "available",
    detail: "Requires Node + Expo CLI. Run `npm install && npx expo start` in mobile/, then scan the QR code with Expo Go, or build with EAS for a real device install.",
  },
];

export default function DownloadsPage() {
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-1">Get Nova</h1>
      <p className="text-muted mb-6">
        Nova runs the same way everywhere — same account, same permissions, same reminders. Pick
        however you want to reach it.
      </p>

      <div className="space-y-4">
        {CLIENTS.map((client) => (
          <div key={client.title} className="card">
            <div className="flex items-start justify-between gap-4 mb-2">
              <h2 className="font-medium text-lg">{client.title}</h2>
              {client.status === "coming-soon" && (
                <span className="text-xs px-2 py-0.5 rounded font-mono uppercase bg-border text-muted shrink-0">
                  coming soon
                </span>
              )}
            </div>
            <p className="text-muted text-sm mb-3">{client.description}</p>
            <p className="text-xs text-muted font-mono mb-3">{client.detail}</p>
            <span
              className={`inline-block text-xs px-2 py-1 rounded font-mono ${
                client.status === "available" ? "bg-active/15 text-active" : "bg-border text-muted"
              }`}
            >
              {client.status === "available" ? "included in this project" : "not built yet"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
