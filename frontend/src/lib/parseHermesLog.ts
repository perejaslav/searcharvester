/**
 * Turns Hermes stdout into a timeline of structured events.
 *
 * Hermes without --quiet prints a lot of stuff (banner, tool list, skills
 * list, query echo, box-drawn answer envelope, exit summary). The interesting
 * parts while a job is running are:
 *
 *   ┊ 💻 $  python3 .../search.py --query "..." --max-results N   1.2s
 *   ┊ 💻 $  python3 .../extract.py --url "..." --size m            0.3s
 *   ┊ 💻 $  python3 ... ... [error]                                 0.5s
 *   ┊ 💻 $  cat > /workspace/report.md << 'EOF' ... EOF             0.2s
 *   ⚠️  API call failed (attempt 1/3): APIError
 *   ⏳ Retrying in 2.3s ...
 *   REPORT_SAVED: /workspace/report.md
 *
 * We parse those into typed events.
 */

export type LogEvent =
  | { kind: "search"; query: string; maxResults?: number; duration?: string; error?: boolean }
  | { kind: "extract"; url: string; size?: string; duration?: string; error?: boolean }
  | { kind: "write_report"; duration?: string }
  | { kind: "other_tool"; cmd: string; duration?: string; error?: boolean }
  | { kind: "api_retry"; attempt: number; of: number; error: string }
  | { kind: "waiting_retry"; seconds: number }
  | { kind: "report_saved" }
  | { kind: "note"; text: string };

const SEARCH_RE =
  /^\s*┊\s*💻\s*\$\s*python3\s+\S*searcharvester-search\S*\s*--query\s+"([^"]+)"(?:\s+--max-results\s+(\d+))?(?:[^\n]*?(\[error\]))?[^\n]*?(\d+(?:\.\d+)?s)?\s*$/;
const EXTRACT_RE =
  /^\s*┊\s*💻\s*\$\s*python3\s+\S*searcharvester-extract\S*\s*--url\s+"([^"]+)"(?:\s+--size\s+(\w))?(?:[^\n]*?(\[error\]))?[^\n]*?(\d+(?:\.\d+)?s)?\s*$/;
const WRITE_REPORT_RE =
  /^\s*┊\s*💻\s*\$\s*cat\s*>\s*\/workspace\/report\.md[^\n]*?(\d+(?:\.\d+)?s)?\s*$/;
const OTHER_TOOL_RE =
  /^\s*┊\s*💻\s*\$\s*(.+?)(?:\s+(\[error\]))?\s*(\d+(?:\.\d+)?s)?\s*$/;
const API_RETRY_RE =
  /^⚠️\s*API call failed \(attempt (\d+)\/(\d+)\):\s*(.+?)\s*$/;
const WAITING_RETRY_RE =
  /^⏳\s*Retrying in (\d+(?:\.\d+)?)s/;

export function parseHermesLog(raw: string): LogEvent[] {
  if (!raw) return [];
  const out: LogEvent[] = [];
  const lines = raw.split("\n");

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Ignore Hermes banner / preparing lines / empty.
    if (!line.trim()) continue;
    if (line.includes("preparing terminal")) continue;
    if (line.includes("preparing searcharvester")) continue;

    // Order matters: specific tool shapes before OTHER_TOOL fallback.
    let m = line.match(SEARCH_RE);
    if (m) {
      out.push({
        kind: "search",
        query: m[1],
        maxResults: m[2] ? parseInt(m[2], 10) : undefined,
        duration: m[4],
        error: !!m[3],
      });
      continue;
    }

    m = line.match(EXTRACT_RE);
    if (m) {
      out.push({
        kind: "extract",
        url: m[1],
        size: m[2],
        duration: m[4],
        error: !!m[3],
      });
      continue;
    }

    m = line.match(WRITE_REPORT_RE);
    if (m) {
      out.push({ kind: "write_report", duration: m[1] });
      continue;
    }

    m = line.match(OTHER_TOOL_RE);
    if (m) {
      // Skip lines that are just `preparing terminal...` collapsed forms.
      const cmd = m[1].trim();
      if (cmd && !cmd.startsWith("preparing")) {
        out.push({ kind: "other_tool", cmd, duration: m[3], error: !!m[2] });
      }
      continue;
    }

    m = line.match(API_RETRY_RE);
    if (m) {
      out.push({
        kind: "api_retry",
        attempt: parseInt(m[1], 10),
        of: parseInt(m[2], 10),
        error: m[3],
      });
      continue;
    }

    m = line.match(WAITING_RETRY_RE);
    if (m) {
      out.push({ kind: "waiting_retry", seconds: parseFloat(m[1]) });
      continue;
    }

    if (line.startsWith("REPORT_SAVED:")) {
      out.push({ kind: "report_saved" });
      continue;
    }
  }
  return out;
}
