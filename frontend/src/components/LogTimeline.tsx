import { LogEvent, parseHermesLog } from "../lib/parseHermesLog";
import {
  Search,
  FileText,
  AlertTriangle,
  Clock,
  CheckCircle2,
  Terminal,
  Save,
} from "lucide-react";

interface Props {
  rawLog: string;
}

/**
 * Cleans up Hermes stdout into a vertical event stream.
 * Shows what the single agent inside the Hermes container is doing:
 * searches, extracts, report writes, LLM retries.
 */
export default function LogTimeline({ rawLog }: Props) {
  const events = parseHermesLog(rawLog);

  if (events.length === 0) {
    return (
      <div className="text-slate-500 text-sm py-2">
        No activity yet. The agent is booting…
      </div>
    );
  }

  return (
    <ol className="space-y-1.5 text-sm">
      {events.map((ev, i) => (
        <li key={i} className="flex items-start gap-2.5">
          {renderEvent(ev)}
        </li>
      ))}
    </ol>
  );
}

function renderEvent(ev: LogEvent) {
  switch (ev.kind) {
    case "search":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-accent-400">
            <Search size={14} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-slate-200">
              <span className="text-accent-400 font-semibold uppercase text-xs mr-2">
                search
              </span>
              <span className="font-mono text-slate-300">"{ev.query}"</span>
              {ev.maxResults && (
                <span className="text-slate-500 ml-2 text-xs">
                  · max {ev.maxResults}
                </span>
              )}
            </div>
          </div>
          {renderDuration(ev.duration, ev.error)}
        </>
      );
    case "extract":
      return (
        <>
          <div className={`shrink-0 mt-0.5 ${ev.error ? "text-red-400" : "text-sky-400"}`}>
            <FileText size={14} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-slate-200">
              <span
                className={`${
                  ev.error ? "text-red-400" : "text-sky-400"
                } font-semibold uppercase text-xs mr-2`}
              >
                extract
                {ev.size ? ` ${ev.size.toUpperCase()}` : ""}
              </span>
              <span className="font-mono text-slate-300 break-all">{ev.url}</span>
            </div>
          </div>
          {renderDuration(ev.duration, ev.error)}
        </>
      );
    case "write_report":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-emerald-400">
            <Save size={14} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-slate-200">
              <span className="text-emerald-400 font-semibold uppercase text-xs mr-2">
                write
              </span>
              <span className="font-mono text-slate-300">/workspace/report.md</span>
            </div>
          </div>
          {renderDuration(ev.duration)}
        </>
      );
    case "other_tool":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-slate-500">
            <Terminal size={14} />
          </div>
          <div className="flex-1 min-w-0 text-slate-400 font-mono text-xs break-all">
            <span className="uppercase text-xs font-semibold mr-2">$</span>
            {ev.cmd}
          </div>
          {renderDuration(ev.duration, ev.error)}
        </>
      );
    case "api_retry":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-amber-400">
            <AlertTriangle size={14} />
          </div>
          <div className="flex-1 text-amber-300/90 text-sm">
            LLM error{" "}
            <span className="text-slate-500">
              (attempt {ev.attempt}/{ev.of})
            </span>
            <span className="font-mono text-slate-500 ml-2 text-xs">{ev.error}</span>
          </div>
        </>
      );
    case "waiting_retry":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-slate-500">
            <Clock size={14} />
          </div>
          <div className="flex-1 text-slate-400 text-xs">
            retrying in {ev.seconds}s…
          </div>
        </>
      );
    case "report_saved":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-emerald-400">
            <CheckCircle2 size={14} />
          </div>
          <div className="flex-1 text-emerald-400 font-semibold">
            REPORT_SAVED · handing off to orchestrator
          </div>
        </>
      );
    case "note":
      return <div className="text-slate-400">{ev.text}</div>;
  }
}

function renderDuration(duration: string | undefined, error?: boolean) {
  if (!duration && !error) {
    // Even with no duration we want to show a status pill.
    return (
      <div className="shrink-0 flex items-center gap-1.5 text-xs">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.6)]" />
        <span className="text-emerald-400 font-semibold uppercase tracking-wider">ok</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="shrink-0 flex items-center gap-2 text-xs font-mono">
        <span className="text-slate-500">{duration}</span>
        <span className="flex items-center gap-1 text-red-400">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.6)]" />
          <span className="font-semibold uppercase tracking-wider">fail</span>
        </span>
      </div>
    );
  }
  return (
    <div className="shrink-0 flex items-center gap-2 text-xs font-mono">
      <span className="text-slate-500">{duration}</span>
      <span className="flex items-center gap-1 text-emerald-400">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.6)]" />
        <span className="font-semibold uppercase tracking-wider">ok</span>
      </span>
    </div>
  );
}
