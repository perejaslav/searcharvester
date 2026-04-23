import {
  Search,
  FileText,
  AlertTriangle,
  CheckCircle2,
  Terminal,
  Save,
  Cpu,
  Container as ContainerIcon,
  Info,
  Users,
  MessageSquare,
  BrainCog,
} from "lucide-react";
import { AgentEvent } from "../lib/api";

interface Props {
  events: AgentEvent[];
}

/**
 * Renders typed agent events as a vertical stream. Events come from the
 * orchestrator's normalizer — one SSE event per action the lead agent takes
 * (thought, tool call, tool result, final message, done).
 */
export default function LogTimeline({ events }: Props) {
  if (events.length === 0) {
    return (
      <div className="text-slate-500 text-sm py-2">Awaiting events…</div>
    );
  }

  const toolCallCount = events.filter((e) => e.type === "tool_call").length;
  const agentCount = new Set(events.map((e) => e.agent_id)).size;

  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2 px-2.5 py-1.5 rounded-md bg-base-800/60 border border-base-700 text-xs text-slate-400">
        <Info size={12} className="shrink-0 mt-0.5 text-slate-500" />
        <div className="leading-relaxed">
          <span className="text-slate-300 font-semibold">{events.length}</span>{" "}
          event{events.length === 1 ? "" : "s"} · {" "}
          <span className="text-slate-300">{toolCallCount}</span> tool call
          {toolCallCount === 1 ? "" : "s"} · {" "}
          <span className="text-slate-300">{agentCount}</span> agent
          {agentCount === 1 ? "" : "s"}
        </div>
      </div>

      <ol className="space-y-1.5 text-sm">
        {events.map((ev, i) => (
          <li key={i} className="flex items-start gap-2.5">
            {renderEvent(ev)}
          </li>
        ))}
      </ol>
    </div>
  );
}

function toolCallSubtitle(ev: AgentEvent): string {
  const p = ev.payload as Record<string, unknown>;
  const ri = p.raw_input as Record<string, unknown> | undefined;
  if (!ri) return "";
  // Best-effort: flatten common fields
  if (typeof ri.query === "string") return `query="${truncate(ri.query, 80)}"`;
  if (typeof ri.url === "string") return ri.url as string;
  if (typeof ri.path === "string") return ri.path as string;
  if (typeof ri.command === "string") return truncate(ri.command as string, 90);
  if (typeof ri.name === "string") return ri.name as string;
  return truncate(JSON.stringify(ri), 90);
}

function renderEvent(ev: AgentEvent) {
  const p = ev.payload as Record<string, unknown>;

  switch (ev.type) {
    case "spawn":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-fuchsia-400">
            <ContainerIcon size={14} />
          </div>
          <div className="flex-1 min-w-0">
            <span className="text-fuchsia-400 font-semibold uppercase text-xs mr-2 tracking-wider">
              orchestrator
            </span>
            <span className="text-slate-300">
              spawned agent <span className="font-mono text-slate-400">{ev.agent_id}</span>
              {p.query ? ` · ${truncate(String(p.query), 80)}` : ""}
            </span>
          </div>
        </>
      );

    case "commands":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-slate-500">
            <Cpu size={14} />
          </div>
          <div className="flex-1 min-w-0 text-slate-500 text-xs">
            slash commands loaded:{" "}
            <span className="font-mono text-slate-400">
              {Array.isArray(p.names) ? (p.names as string[]).join(", ") : ""}
            </span>
          </div>
        </>
      );

    case "thought":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-violet-400">
            <BrainCog size={13} />
          </div>
          <div className="flex-1 min-w-0 text-violet-300/80 italic text-xs">
            {truncate(String(p.text ?? ""), 160)}
          </div>
        </>
      );

    case "tool_call": {
      const title = String(p.title ?? "tool");
      const [icon, color] = toolIcon(title);
      return (
        <>
          <div className={`shrink-0 mt-0.5 ${color}`}>{icon}</div>
          <div className="flex-1 min-w-0">
            <div className="text-slate-200">
              <span className={`${color} font-semibold uppercase text-xs mr-2`}>
                {shortTitle(title)}
              </span>
              <span className="font-mono text-slate-300 break-all">
                {truncate(toolCallSubtitle(ev), 160)}
              </span>
            </div>
          </div>
        </>
      );
    }

    case "tool_result": {
      const err = p.status && String(p.status).toLowerCase().includes("error");
      return (
        <>
          <div className={`shrink-0 mt-0.5 ml-4 ${err ? "text-red-400" : "text-emerald-400"}`}>
            {err ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}
          </div>
          <div className="flex-1 min-w-0 text-xs font-mono text-slate-500 break-all">
            {err ? "error · " : ""}
            {truncate(String(p.content ?? "").replace(/\s+/g, " "), 140)}
          </div>
        </>
      );
    }

    case "message":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-sky-400">
            <MessageSquare size={13} />
          </div>
          <div className="flex-1 min-w-0 text-sky-300/90 text-xs">
            {truncate(String(p.text ?? ""), 200)}
          </div>
        </>
      );

    case "plan":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-amber-300">
            <Info size={13} />
          </div>
          <div className="flex-1 min-w-0 text-amber-300/80 text-xs">
            plan updated ({Object.keys(p).length} fields)
          </div>
        </>
      );

    case "note":
      return (
        <>
          <div className="shrink-0 mt-0.5 text-slate-500">
            <Info size={13} />
          </div>
          <div className="flex-1 min-w-0 text-xs text-slate-500">
            {String((p.kind as string | undefined) ?? "note")}
          </div>
        </>
      );

    case "done": {
      const status = String(p.status ?? "done");
      const ok = status === "completed";
      return (
        <>
          <div className={`shrink-0 mt-0.5 ${ok ? "text-emerald-400" : "text-red-400"}`}>
            <CheckCircle2 size={14} />
          </div>
          <div className={`flex-1 font-semibold uppercase tracking-wider text-xs ${
            ok ? "text-emerald-400" : "text-red-400"
          }`}>
            {status}{p.error ? ` · ${String(p.error)}` : ""}
          </div>
        </>
      );
    }
  }
}

function toolIcon(title: string): [JSX.Element, string] {
  const t = title.toLowerCase();
  if (t.includes("delegate")) return [<Users size={14} />, "text-cyan-400"];
  if (t.includes("write") || t.includes("report")) return [<Save size={14} />, "text-emerald-400"];
  if (t.includes("terminal") || t.includes("bash") || t.includes("exec"))
    return [<Terminal size={14} />, "text-slate-400"];
  if (t.includes("extract") || t.includes("fetch") || t.includes("read"))
    return [<FileText size={14} />, "text-sky-400"];
  if (t.includes("search") || t.includes("query"))
    return [<Search size={14} />, "text-accent-400"];
  return [<Terminal size={14} />, "text-slate-400"];
}

function shortTitle(title: string): string {
  // Hermes often titles tool calls as "terminal: <command>" — take first
  // word for the pill.
  const m = title.match(/^([a-z0-9_-]+)/i);
  return (m?.[1] ?? title).slice(0, 14);
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}
