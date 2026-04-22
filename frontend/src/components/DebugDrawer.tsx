import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Terminal, List, Code2 } from "lucide-react";
import { getLogs } from "../lib/api";
import LogTimeline from "./LogTimeline";

interface Props {
  jobId: string | null;
  isRunning: boolean;
}

type View = "timeline" | "raw";

/**
 * Collapsible drawer showing what the single agent inside the Hermes container
 * is doing. Default view is a parsed timeline (each tool call / error / retry
 * as its own row). Raw toggle shows the full stdout including Hermes banner.
 *
 * Polls /logs every 3 s while the job is running.
 */
export default function DebugDrawer({ jobId, isRunning }: Props) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("timeline");
  const [logs, setLogs] = useState<string>("");

  useEffect(() => {
    if (!jobId) {
      setLogs("");
      return;
    }

    let cancelled = false;
    let handle: number | null = null;

    const tick = async () => {
      try {
        const l = await getLogs(jobId);
        if (cancelled) return;
        if (l !== null) {
          setLogs(l);
        } else {
          setLogs("");
          if (handle !== null) {
            clearInterval(handle);
            handle = null;
          }
        }
      } catch (e) {
        console.debug("log fetch error", e);
      }
    };

    tick();
    if (isRunning) {
      handle = window.setInterval(tick, 3000);
    }

    return () => {
      cancelled = true;
      if (handle !== null) clearInterval(handle);
    };
  }, [jobId, isRunning]);

  const charCount = logs.length;

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
                  · {isRunning ? "live" : "final"}
                  {charCount > 0 && ` · ${(charCount / 1024).toFixed(1)}kb`}
                </span>
              )}
              <div className="ml-auto text-slate-600">
                {open ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
              </div>
            </button>
          </div>
          {open && (
            <div className="border-t border-base-700 max-h-72 overflow-y-auto">
              <div className="px-4 py-2 border-b border-base-800 flex items-center justify-between">
                <div className="text-xs text-slate-500">
                  {view === "timeline"
                    ? "parsed tool-call timeline"
                    : "raw Hermes stdout"}
                </div>
                <div className="flex rounded-md border border-base-700 overflow-hidden text-xs">
                  <button
                    onClick={() => setView("timeline")}
                    className={`flex items-center gap-1 px-2 py-1 transition-colors ${
                      view === "timeline"
                        ? "bg-base-700 text-slate-100"
                        : "text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    <List size={12} />
                    <span>Timeline</span>
                  </button>
                  <button
                    onClick={() => setView("raw")}
                    className={`flex items-center gap-1 px-2 py-1 transition-colors border-l border-base-700 ${
                      view === "raw"
                        ? "bg-base-700 text-slate-100"
                        : "text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    <Code2 size={12} />
                    <span>Raw</span>
                  </button>
                </div>
              </div>

              <div className="p-4">
                {!jobId ? (
                  <div className="text-slate-500 text-sm">No job running.</div>
                ) : !logs ? (
                  <div className="text-slate-500 text-sm">
                    Waiting for the agent to produce output…
                  </div>
                ) : view === "timeline" ? (
                  <LogTimeline rawLog={logs} />
                ) : (
                  <pre className="log-pane text-xs text-slate-300 font-mono">
                    {logs}
                  </pre>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
