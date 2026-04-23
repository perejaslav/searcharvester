import { useState } from "react";
import { ChevronDown, ChevronUp, Terminal } from "lucide-react";
import LogTimeline from "./LogTimeline";
import { AgentEvent } from "../lib/api";

interface Props {
  jobId: string | null;
  events: AgentEvent[];
  isRunning: boolean;
}

/**
 * Collapsible drawer showing the live agent event stream. Events are pushed
 * from the parent via SSE, so this component is pure rendering — no
 * polling, no log parsing.
 */
export default function DebugDrawer({ jobId, events, isRunning }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-0 left-0 right-0 z-20">
      <div className="max-w-4xl mx-auto px-4 pb-4">
        <div className="rounded-t-xl border border-base-700 bg-base-900 border-b-0 shadow-2xl">
          <div className="w-full px-4 py-2.5 flex items-center justify-between">
            <button
              onClick={() => setOpen(!open)}
              className="flex-1 flex items-center gap-2 text-slate-400 hover:text-slate-200 transition-colors text-left"
            >
              <Terminal size={14} />
              <span className="font-semibold uppercase tracking-wider text-xs">
                Agent activity
              </span>
              {jobId && (
                <span className="text-slate-600 font-mono text-xs">
                  · {isRunning ? "live" : "final"} · {events.length} event
                  {events.length === 1 ? "" : "s"}
                </span>
              )}
              <div className="ml-auto text-slate-600">
                {open ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
              </div>
            </button>
          </div>
          {open && (
            <div className="border-t border-base-700 max-h-72 overflow-y-auto">
              <div className="px-4 py-2 border-b border-base-800 text-xs text-slate-500">
                typed agent event stream (SSE)
              </div>

              <div className="p-4">
                {!jobId ? (
                  <div className="text-slate-500 text-sm">No job running.</div>
                ) : events.length === 0 ? (
                  <div className="text-slate-500 text-sm">
                    Waiting for the agent to produce events…
                  </div>
                ) : (
                  <LogTimeline events={events} />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
