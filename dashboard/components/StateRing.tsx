type AgentState = "idle" | "listening" | "thinking" | "executing";

const STATE_COLOR: Record<AgentState, string> = {
  idle: "#7C8CFF",
  listening: "#2DD4BF",
  thinking: "#F5A623",
  executing: "#2DD4BF",
};

const STATE_LABEL: Record<AgentState, string> = {
  idle: "Idle",
  listening: "Listening",
  thinking: "Thinking",
  executing: "Executing",
};

/**
 * Deliberately the same visual language as the desktop agent's floating
 * bubble (ui/bubble.py) — a ring whose color reflects the assistant's
 * current state. Reinforces that the web dashboard and the desktop agent
 * are views onto the same assistant, not two separate products.
 */
export function StateRing({ state = "idle", size = 14 }: { state?: AgentState; size?: number }) {
  const color = STATE_COLOR[state];
  return (
    <div className="flex items-center gap-2" title={STATE_LABEL[state]}>
      <span
        className="inline-block rounded-full"
        style={{
          width: size,
          height: size,
          border: `2px solid ${color}`,
          boxShadow: state !== "idle" ? `0 0 8px ${color}` : undefined,
        }}
      />
      <span className="text-xs text-muted font-mono uppercase tracking-wide">{STATE_LABEL[state]}</span>
    </div>
  );
}
