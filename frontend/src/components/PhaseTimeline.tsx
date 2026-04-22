import { Check, Circle, Dot } from "lucide-react";
import { Phase } from "../lib/api";

const PHASES: { id: Phase; label: string; desc: string }[] = [
  { id: "planning", label: "Plan", desc: "Decomposing the question" },
  { id: "gather", label: "Gather", desc: "Searching + extracting sources" },
  { id: "synthesise", label: "Synthesise", desc: "Writing the report" },
  { id: "verify", label: "Verify", desc: "Checking citations" },
];

interface Props {
  currentPhase: Phase | null;
  finalStatus: "completed" | "failed" | "timeout" | "cancelled" | null;
}

export default function PhaseTimeline({ currentPhase, finalStatus }: Props) {
  const activeIndex = PHASES.findIndex((p) => p.id === currentPhase);
  const isFinal = finalStatus !== null;
  const allDone = finalStatus === "completed";

  return (
    <div className="flex gap-2 items-stretch">
      {PHASES.map((phase, i) => {
        const passed = isFinal && allDone ? true : activeIndex > i;
        const active = !isFinal && i === activeIndex;
        return (
          <div
            key={phase.id}
            className={`flex-1 rounded-lg border px-3 py-2 transition-colors
              ${
                passed
                  ? "border-emerald-600/40 bg-emerald-600/5 text-emerald-300"
                  : active
                  ? "border-accent-500/60 bg-accent-500/10 text-accent-400"
                  : "border-base-700 bg-base-800/40 text-slate-500"
              }`}
          >
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider">
              {passed ? (
                <Check size={14} />
              ) : active ? (
                <Dot size={18} className="animate-pulse" />
              ) : (
                <Circle size={12} />
              )}
              {phase.label}
            </div>
            <div className="text-xs text-slate-400 mt-1 hidden sm:block">
              {phase.desc}
            </div>
          </div>
        );
      })}
    </div>
  );
}
