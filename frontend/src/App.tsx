import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Github } from "lucide-react";
import ResearchForm from "./components/ResearchForm";
import JobStatusCard from "./components/JobStatusCard";
import ReportView from "./components/ReportView";
import DebugDrawer from "./components/DebugDrawer";
import {
  API_URL,
  EventPayload,
  JobStatus,
  SSESubscription,
  cancelJob,
  checkHealth,
  createResearch,
  subscribeToJob,
} from "./lib/api";

interface ActiveJob {
  jobId: string;
  query: string;
}

function useHealth() {
  const [healthy, setHealthy] = useState<"ok" | "degraded" | "down">("down");
  useEffect(() => {
    const tick = async () => {
      try {
        const h = await checkHealth();
        setHealthy(h.orchestrator === "available" ? "ok" : "degraded");
      } catch {
        setHealthy("down");
      }
    };
    tick();
    const id = window.setInterval(tick, 15000);
    return () => clearInterval(id);
  }, []);
  return healthy;
}

/** Restore / persist current job_id via URL hash so reloading keeps it alive. */
function useHashJob(): [
  ActiveJob | null,
  (j: ActiveJob | null) => void
] {
  const [job, setJob] = useState<ActiveJob | null>(null);

  // read once
  useEffect(() => {
    const parseHash = () => {
      const raw = window.location.hash.replace(/^#/, "");
      const params = new URLSearchParams(raw);
      const id = params.get("job");
      const q = params.get("q");
      if (id && q) setJob({ jobId: id, query: q });
      else setJob(null);
    };
    parseHash();
    window.addEventListener("hashchange", parseHash);
    return () => window.removeEventListener("hashchange", parseHash);
  }, []);

  const writeJob = useCallback((j: ActiveJob | null) => {
    if (j) {
      const p = new URLSearchParams({ job: j.jobId, q: j.query });
      window.location.hash = p.toString();
    } else {
      history.replaceState(null, "", window.location.pathname);
    }
    setJob(j);
  }, []);

  return [job, writeJob];
}

export default function App() {
  const healthy = useHealth();
  const [job, setJob] = useHashJob();
  const [latest, setLatest] = useState<EventPayload | null>(null);
  const [finalStatus, setFinalStatus] = useState<JobStatus | null>(null);
  const subRef = useRef<SSESubscription | null>(null);

  // (Re-)subscribe when the active job changes (includes page-reload restore).
  useEffect(() => {
    subRef.current?.close();
    subRef.current = null;
    setLatest(null);
    setFinalStatus(null);

    if (!job) return;

    const sub = subscribeToJob(
      job.jobId,
      (kind, payload) => {
        setLatest(payload);
        if (kind !== "status") {
          setFinalStatus(payload.status);
        }
      },
      (e) => {
        console.error("SSE error", e);
      }
    );
    subRef.current = sub;

    return () => {
      sub.close();
      subRef.current = null;
    };
  }, [job?.jobId]);

  const onSubmit = async (query: string) => {
    try {
      const res = await createResearch(query);
      setJob({ jobId: res.job_id, query });
    } catch (e) {
      alert(`Failed to start research: ${(e as Error).message}`);
    }
  };

  const onCancel = async () => {
    if (!job) return;
    await cancelJob(job.jobId);
  };

  const onRunAgain = () => setJob(null);

  const isRunning = job !== null && finalStatus === null;
  const report = latest?.report ?? null;

  return (
    <div className="min-h-full pb-24">
      {/* Header */}
      <header className="border-b border-base-800">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-2xl">🌾</div>
            <div>
              <h1 className="text-lg font-semibold text-slate-100">Searcharvester</h1>
              <div className="text-xs text-slate-500">Self-hosted deep research</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div
              className={`flex items-center gap-1.5 text-xs ${
                healthy === "ok"
                  ? "text-emerald-400"
                  : healthy === "degraded"
                  ? "text-amber-400"
                  : "text-red-400"
              }`}
              title={`API: ${API_URL}`}
            >
              <Activity size={12} className={healthy === "ok" ? "animate-pulse" : ""} />
              {healthy === "ok" ? "API connected" : healthy === "degraded" ? "orchestrator offline" : "API down"}
            </div>
            <a
              href="https://github.com/vakovalskii/searcharvester"
              target="_blank"
              rel="noreferrer"
              className="text-slate-500 hover:text-slate-300 transition-colors"
              aria-label="GitHub"
            >
              <Github size={16} />
            </a>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-4xl mx-auto px-4 pt-8 space-y-5">
        {!job && <ResearchForm onSubmit={onSubmit} disabled={healthy === "down"} />}

        {job && (
          <JobStatusCard
            query={job.query}
            jobId={job.jobId}
            latest={latest}
            finalStatus={finalStatus}
            onCancel={onCancel}
          />
        )}

        {report && <ReportView report={report} onRunAgain={onRunAgain} />}

        {job && finalStatus && !report && (
          <div className="text-center">
            <button
              onClick={onRunAgain}
              className="text-slate-400 hover:text-slate-100 underline text-sm"
            >
              Start a new research
            </button>
          </div>
        )}
      </main>

      <DebugDrawer jobId={job?.jobId ?? null} isRunning={isRunning} />
    </div>
  );
}
