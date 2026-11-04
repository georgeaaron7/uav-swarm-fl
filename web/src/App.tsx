import { useEffect, useState, useCallback, useRef } from "react";
import type { LucideIcon } from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { Link, NavLink, Route, Routes, useParams } from "react-router-dom";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronRight,
  CircleHelp,
  Clipboard,
  Database,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Terminal,
  X,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, download, getToken, setToken } from "./api";

type Entity = { id: string; data: Record<string, any>; [key: string]: any };
type User = { id: string; role: string; username: string };
const short = (id?: string) => (id ? id.slice(0, 10) : "—");
const when = (t?: number) => (t ? new Date(t * 1000).toLocaleString() : "—");
const number = (v: unknown, digits = 1) =>
  typeof v === "number"
    ? v.toLocaleString(undefined, { maximumFractionDigits: digits })
    : "—";
const pct = (v: unknown) =>
  typeof v === "number" ? number(v * 100, 2) + "%" : "—";
const statuses: Record<string, string> = {
  SUCCEEDED: "success",
  DIVERGED: "diverged",
  FAILED: "danger",
  NEEDS_ATTENTION: "danger",
  RUNNING: "running",
  ONLINE_BUSY: "running",
  ONLINE_IDLE: "success",
  OFFLINE: "muted",
  INCOMPATIBLE: "danger",
  PAUSED: "muted",
  DRAINING: "diverged",
};
function Status({ value }: { value: string }) {
  return (
    <span className={"status " + (statuses[value] || "muted")}>
      <span className="status-dot" />
      {value.replaceAll("_", " ").toLowerCase()}
    </span>
  );
}
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function ErrorBox({ error }: { error: string }) {
  return error ? (
    <div className="error" role="alert">
      {error}
    </div>
  ) : null;
}
function useData<T>(path: string) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState("");
  const reload = useCallback(() => {
    api(path)
      .then(setData)
      .then(() => setError(""))
      .catch((e) => setError(e.message));
  }, [path]);
  useEffect(() => {
    setData(null);
    reload();
    const id = setInterval(reload, 10000);
    window.addEventListener("swarm-refresh", reload);
    return () => {
      clearInterval(id);
      window.removeEventListener("swarm-refresh", reload);
    };
  }, [reload]);
  return { data, error, reload };
}
function useLive() {
  const [live, setLive] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let retry: ReturnType<typeof setTimeout>;
    async function connect() {
      try {
        const r = await fetch("/api/v1/stream", {
          headers: { Authorization: "Bearer " + getToken() },
          signal: controller.signal,
        });
        if (!r.ok || !r.body) throw new Error();
        setLive(true);
        const reader = r.body.getReader();
        while (true) {
          const { done } = await reader.read();
          if (done) break;
          window.dispatchEvent(new Event("swarm-refresh"));
        }
      } catch {
        setLive(false);
      } finally {
        if (!controller.signal.aborted) {
          setLive(false);
          retry = setTimeout(connect, 10000);
        }
      }
    }
    connect();
    return () => {
      controller.abort();
      clearTimeout(retry);
    };
  }, []);
  return live;
}
function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      const r = await api("/auth/login", "POST", {
        username: f.get("username"),
        password: f.get("password"),
      });
      setToken(r.token);
      onLogin(await api("/auth/me"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <div className="login-brand">
        <Activity size={28} />
        <span>SwarmCompute</span>
      </div>
      <div className="login-panel">
        <h1>Sign in to your cluster</h1>
        <p>Independent experiments. Shared progress.</p>
        <form onSubmit={submit}>
          <label>
            Username
            <input name="username" autoComplete="username" required autoFocus />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          <ErrorBox error={error} />
          <button disabled={busy} className="primary">
            {busy ? "Signing in…" : "Sign in"}
            <ArrowRight size={16} />
          </button>
        </form>
      </div>
      <p className="login-note">
        Your coordinator runs on your network. Use Tailscale or HTTPS on shared
        networks.
      </p>
    </main>
  );
}
function PageHead({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </header>
  );
}
function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
}) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
      {sub && <small>{sub}</small>}
    </div>
  );
}
function Events({ events }: { events: Entity[] }) {
  return (
    <div className="event-list">
      {events.map((e) => (
        <div className="event" key={e.id}>
          <span className="event-mark" />
          <div>
            <strong>{e.kind.replaceAll("_", " ")}</strong>
            <span>
              {short(e.data.job_id || e.data.worker_id || e.data.study_id)}
              {e.data.reason ? " · " + e.data.reason : ""}
            </span>
          </div>
          <time>{when(e.created)}</time>
        </div>
      ))}
    </div>
  );
}
function StudyPanel() {
  const { data, error, reload } = useData<Entity[]>("/studies"),
    [review, setReview] = useState<Entity | null>(null),
    [show, setShow] = useState(false),
    [failure, setFailure] = useState(""),
    [busy, setBusy] = useState(false);
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setFailure("");
    const f = new FormData(e.currentTarget);
    try {
      await api("/studies", "POST", {
        name: f.get("name"),
        profile: f.get("profile"),
        aggs: String(f.get("aggs"))
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
        data_dir: f.get("data_dir"),
        trace_path: f.get("trace_path"),
      });
      setShow(false);
      reload();
      window.dispatchEvent(new Event("swarm-refresh"));
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function control(id: string, action: string) {
    try {
      await api(`/studies/${id}/${action}`, "POST");
      reload();
      setFailure("");
    } catch (e) {
      setFailure((e as Error).message);
    }
  }
  return (
    <section className="section">
      <div className="section-head">
        <h2>Studies</h2>
        <button onClick={() => setShow(!show)}>
          <Plus size={15} />
          Create study
        </button>
      </div>
      <ErrorBox error={failure || error} />
      {show && (
        <form className="inline-form" onSubmit={create}>
          <div className="form-grid">
            <label>
              Study name
              <input
                name="name"
                required
                placeholder="laptop-pilot"
                pattern="[A-Za-z0-9_-]+"
              />
            </label>
            <label>
              Profile
              <select name="profile">
                <option value="pilot">Pilot · 2 rounds, 2 seeds</option>
                <option value="final">Final · 100 rounds, 10 seeds</option>
              </select>
            </label>
            <label>
              Aggregators (comma separated)
              <input name="aggs" defaultValue="bp_fresh,bp_reuse" required />
            </label>
            <label>
              Prepared data directory on coordinator
              <input name="data_dir" defaultValue="data" required />
            </label>
            <label>
              Prepared channel trace on coordinator
              <input
                name="trace_path"
                defaultValue="data/channel_traces/deepsense23.npz"
                required
              />
            </label>
          </div>
          <p className="hint">
            Configurations are generated by the existing study planner. Review
            the manifest before starting. Keep bp_fresh and bp_reuse in a
            separate study from the six-method context study.
          </p>
          <div className="actions">
            <button className="primary" disabled={busy}>
              {busy ? "Validating & planning…" : "Plan study"}
            </button>
            <button type="button" onClick={() => setShow(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {!data ? (
        <p className="hint">Loading studies…</p>
      ) : data.length === 0 ? (
        <Empty title="Start with a pilot study">
          Prepare the datasets, plan a study, and review its jobs before
          starting workers.
        </Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Study</th>
                <th>Profile</th>
                <th>Experiments</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id}>
                  <td>
                    <strong>{s.name}</strong>
                    <small>{short(s.id)}</small>
                  </td>
                  <td>{s.data.manifest.profile}</td>
                  <td>{s.data.manifest.jobs.length}</td>
                  <td>
                    <Status value={s.data.status} />
                  </td>
                  <td>
                    <div className="actions">
                      <button onClick={() => setReview(s)}>
                        Review manifest
                      </button>
                      {s.data.status === "RUNNING" ? (
                        <button onClick={() => control(s.id, "pause")}>
                          <Pause size={14} />
                          Pause queue
                        </button>
                      ) : (
                        <button
                          onClick={() =>
                            control(
                              s.id,
                              s.data.status === "PENDING" ? "start" : "resume",
                            )
                          }
                        >
                          <Play size={14} />
                          {s.data.status === "PENDING"
                            ? "Start study"
                            : "Resume queue"}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {review && (
        <ManifestReview study={review} onClose={() => setReview(null)} />
      )}
    </section>
  );
}
function ManifestReview({
  study,
  onClose,
}: {
  study: Entity;
  onClose: () => void;
}) {
  const manifest = study.data.manifest;
  return (
    <section className="inline-form manifest-review">
      <div className="section-head">
        <h2>Frozen manifest · {study.name}</h2>
        <button onClick={onClose}>Close review</button>
      </div>
      <p>
        {manifest.jobs.length} independent experiments · {manifest.rounds}{" "}
        rounds · seeds {manifest.seeds.join(", ")}.
      </p>
      <dl className="facts">
        <dt>Scientific source</dt>
        <dd>
          <code>{manifest.source_sha256}</code>
        </dd>
        <dt>Dataset fingerprint</dt>
        <dd>
          <code>{manifest.dataset_sha256}</code>
        </dd>
        <dt>Trace fingerprint</dt>
        <dd>
          <code>{manifest.trace_sha256 || "Not required"}</code>
        </dd>
      </dl>
      <details>
        <summary>
          Inspect all frozen configurations ({manifest.jobs.length} jobs)
        </summary>
        <pre>{JSON.stringify(manifest, null, 2)}</pre>
      </details>
      <Link to="/experiments">
        Inspect planned jobs
        <ArrowRight size={15} />
      </Link>
    </section>
  );
}
function CopyAddress({ url, kind }: { url: string; kind: string }) {
  const [feedback, setFeedback] = useState("");
  async function copy() {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(url);
      setFeedback("Address copied");
    } catch {
      setFeedback(
        "Select and copy the address above; automatic copying is unavailable on this connection.",
      );
    }
  }
  return (
    <div className="address">
      <span>{kind}</span>
      <a href={url}>{url}</a>
      <button
        title="Copy address"
        aria-label={"Copy " + kind + " address"}
        onClick={copy}
      >
        <Clipboard size={14} />
      </button>
      {feedback && <small role="status">{feedback}</small>}
    </div>
  );
}
function Overview({ user }: { user: User }) {
  const { data: d, error, reload } = useData<any>("/overview");
  return (
    <>
      <PageHead
        title="Cluster overview"
        description="A shared queue. Every experiment accounted for."
        action={
          <button onClick={reload}>
            <RefreshCw size={15} />
            Refresh
          </button>
        }
      />
      <ErrorBox error={error} />
      {!d ? (
        <p className="hint">Loading cluster state…</p>
      ) : (
        <>
          {d.disk_warning && (
            <div className="error">
              Storage is running low: {number(d.free_disk_bytes / 1024 ** 3)}{" "}
              GiB available. New assignments stop at the configured critical
              threshold.
            </div>
          )}
          <section className="study-progress">
            <div className="progress-title">
              <div>
                <h2>Study progress</h2>
                <p>
                  Successful and scientifically diverged runs count as terminal.
                </p>
              </div>
              <span>
                <strong>{d.terminal}</strong> / {d.total} terminal
              </span>
            </div>
            <progress
              aria-label="Terminal experiments"
              value={d.terminal}
              max={d.total || 1}
            />
            <div className="outcomes">
              <span>
                <i className="success-bg" />
                {d.jobs.SUCCEEDED || 0} succeeded
              </span>
              <span>
                <i className="diverged-bg" />
                {d.jobs.DIVERGED || 0} diverged
              </span>
              <span>
                <i className="running-bg" />
                {(d.jobs.RUNNING || 0) + (d.jobs.LEASED || 0)} active
              </span>
              <span>
                <i className="muted-bg" />
                {(d.jobs.QUEUED || 0) +
                  (d.jobs.PENDING || 0) +
                  (d.jobs.RETRY_WAIT || 0)}{" "}
                waiting
              </span>
              <span>
                <i className="danger-bg" />
                {(d.jobs.FAILED || 0) + (d.jobs.NEEDS_ATTENTION || 0)} need
                attention
              </span>
            </div>
          </section>
          <section className="stats">
            <Stat
              label="Workers online"
              value={
                <>
                  {d.online}
                  <em> / {d.workers}</em>
                </>
              }
              sub={`${d.busy} training · ${d.workers - d.online} offline`}
            />
            <Stat
              label="Available GPUs"
              value={d.gpu_count}
              sub={`${number(d.vram_mb / 1024)} GiB reported VRAM`}
            />
            <Stat
              label="Throughput"
              value={
                d.throughput_per_hour === null
                  ? "—"
                  : number(d.throughput_per_hour, 2)
              }
              sub="terminal experiments / hour"
            />
            <Stat
              label="Estimated remaining"
              value={d.eta_hours === null ? "—" : number(d.eta_hours) + " h"}
              sub={
                d.eta_hours === null
                  ? "Waiting for measured completions"
                  : "Projection from observed throughput"
              }
            />
          </section>
          {user.role === "admin" && <StudyPanel />}
          <div className="overview-columns">
            <section className="section">
              <div className="section-head">
                <h2>Recent activity</h2>
                {user.role === "admin" && (
                  <Link to="/logs">
                    All events
                    <ChevronRight size={14} />
                  </Link>
                )}
              </div>
              {d.events.length ? (
                <Events events={d.events} />
              ) : (
                <Empty title="No activity yet">
                  Worker connections, assignments and recovery events will
                  appear here.
                </Empty>
              )}
            </section>
            <section className="section connection">
              <h2>Connect to this coordinator</h2>
              <p>Open a detected address from a reachable device.</p>
              {d.addresses.map((a: any) => (
                <CopyAddress key={a.url} kind={a.kind} url={a.url} />
              ))}
              <div className="help-note">
                <ShieldCheck size={17} />
                <p>
                  Use a trusted LAN, Tailscale or HTTPS. The coordinator must
                  stay awake. Check firewall rules if another laptop cannot
                  connect.
                </p>
              </div>
              <Link to="/help">
                Setup & power guidance
                <ArrowRight size={15} />
              </Link>
            </section>
          </div>
        </>
      )}
    </>
  );
}
function EnrollForm() {
  const [show, setShow] = useState(false),
    [value, setValue] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    const f = new FormData(e.currentTarget);
    try {
      setValue(
        await api("/enrollment-codes", "POST", { owner: f.get("owner") }),
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className="primary"
        onClick={() => {
          setShow(!show);
          setValue(null);
        }}
      >
        <Plus size={15} />
        Add worker
      </button>
      {show && (
        <div className="enrollment">
          <div className="section-head">
            <h2>Enroll a laptop</h2>
            <button
              aria-label="Close enrollment"
              onClick={() => {
                setShow(false);
                setValue(null);
              }}
            >
              <X size={16} />
            </button>
          </div>
          <p>
            Create a code for the laptop owner. It expires in 10 minutes and can
            be used once.
          </p>
          <form onSubmit={submit}>
            <label>
              Owner username
              <input name="owner" required placeholder="aaron" maxLength={80} />
            </label>
            <button disabled={busy}>Generate code</button>
          </form>
          <ErrorBox error={error} />
          {value && (
            <>
              <label>
                One-time code<code className="pairing-code">{value.code}</code>
              </label>
              <p>
                Share this privately with the owner. Install the worker, then
                run:
              </p>
              <pre>swarm join --server {window.location.origin}</pre>
              <p className="hint">
                The command asks for the code privately. New owner login
                credentials are shown to the owner once during enrollment.
              </p>
            </>
          )}
        </div>
      )}
    </>
  );
}
function Workers({ user }: { user: User }) {
  const { data, error } = useData<Entity[]>("/workers");
  return (
    <>
      <PageHead
        title="Workers"
        description="Voluntary participation. One independent experiment per laptop by default."
        action={user.role === "admin" ? <EnrollForm /> : undefined}
      />
      <ErrorBox error={error} />
      {!data ? (
        <p>Loading workers…</p>
      ) : !data.length ? (
        <Empty title="No workers enrolled">
          Generate an enrollment code, then let the owner install and join from
          their laptop.
        </Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Laptop</th>
                <th>GPU / memory</th>
                <th>Availability</th>
                <th>GPU load</th>
                <th>CPU / RAM</th>
                <th>Temperature</th>
                <th>Last heartbeat</th>
              </tr>
            </thead>
            <tbody>
              {data.map((w) => (
                <tr key={w.id}>
                  <td>
                    <Link to={"/workers/" + w.id}>
                      {w.data.name}
                      <ChevronRight size={14} />
                    </Link>
                    <small>
                      {short(w.id)} · owner {short(w.owner_id)}
                    </small>
                  </td>
                  <td>
                    {w.data.capabilities.gpu_name || "No NVIDIA GPU reported"}
                    <small>
                      {number(w.data.capabilities.vram_mb / 1024)} GiB ·{" "}
                      {w.data.capabilities.os}
                    </small>
                  </td>
                  <td>
                    <Status value={w.data.status} />
                  </td>
                  <td>
                    {number(w.data.telemetry?.gpu_utilization)}%
                    <small>
                      {number(w.data.telemetry?.gpu_memory_used_mb)} MiB used
                    </small>
                  </td>
                  <td>
                    {number(w.data.telemetry?.cpu_percent)}% /{" "}
                    {number(w.data.telemetry?.ram_percent)}%
                  </td>
                  <td>
                    {w.data.telemetry?.gpu_temperature == null
                      ? "—"
                      : number(w.data.telemetry.gpu_temperature) + " °C"}
                  </td>
                  <td>{when(w.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="help-note">
        <CircleHelp size={17} />
        <p>
          Unknown sensor readings are shown as —. Balanced mode uses one
          training process and two CPU threads.{" "}
          <Link to="/help">Keep laptops powered, ventilated and awake.</Link>
        </p>
      </div>
    </>
  );
}
function WorkerDetail({ user }: { user: User }) {
  const { id } = useParams(),
    { data: w, error, reload } = useData<Entity>("/workers/" + id),
    [failure, setFailure] = useState(""),
    [pending, setPending] = useState("");
  async function control(action: string) {
    setPending(action);
    try {
      await api(`/workers/${id}/control`, "POST", { action });
      reload();
      setFailure("");
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setPending("");
    }
  }
  async function mode(value: string) {
    setPending("preferences");
    try {
      await api(`/workers/${id}/preferences`, "PUT", { mode: value });
      reload();
      setFailure("");
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setPending("");
    }
  }
  const can = (action: string) =>
    w &&
    (user.id === w.owner_id ||
      (w.data.preferences.admin_permissions || []).includes(action));
  return (
    <>
      <PageHead title={w?.data.name || "Worker"} description={"Worker " + id} />
      <ErrorBox error={error || failure} />
      {w && (
        <>
          <div className="detail-toolbar">
            <Status value={w.data.status} />
            <div className="actions">
              {[
                ["drain", "Pause after experiment"],
                ["pause", "Checkpoint & pause"],
                ["resume", "Resume participation"],
                ["leave", "Leave cluster"],
              ].map(([a, label]) => (
                <button
                  key={a}
                  disabled={!can(a) || !!pending}
                  onClick={() => control(a)}
                >
                  {pending === a ? "Requesting…" : label}
                </button>
              ))}
            </div>
          </div>
          <p className="hint">
            Administrative controls require permissions granted by the owner.
            Pause requests are applied at safe boundaries.
          </p>
          <label className="chart-select">
            Participation mode
            <select
              aria-label="Participation mode"
              value={w.data.preferences.mode || "balanced"}
              disabled={!can("preferences") || !!pending}
              onChange={(e) => mode(e.target.value)}
            >
              <option value="light">
                Light · one CPU thread, wait for low activity
              </option>
              <option value="balanced">Balanced · two CPU threads</option>
              <option value="dedicated">
                Dedicated · more CPU threads, one GPU job
              </option>
            </select>
          </label>
          <p className="hint">
            Mode changes apply to the next experiment after the worker
            acknowledges the update.
          </p>
          <div className="stats">
            <Stat
              label="GPU"
              value={w.data.capabilities.gpu_name || "Unknown"}
            />
            <Stat
              label="GPU memory used"
              value={number(w.data.telemetry.gpu_memory_used_mb) + " MiB"}
            />
            <Stat
              label="GPU power"
              value={
                w.data.telemetry.gpu_power_w == null
                  ? "—"
                  : number(w.data.telemetry.gpu_power_w) + " W"
              }
            />
            <Stat
              label="Completed experiments"
              value={
                w.attempts.filter((a: Entity) =>
                  ["SUCCEEDED", "DIVERGED"].includes(a.status),
                ).length
              }
            />
          </div>
          <section className="section">
            <h2>Participation & environment</h2>
            <dl className="facts">
              <dt>Owner</dt>
              <dd>{w.owner_id}</dd>
              <dt>Mode</dt>
              <dd>{w.data.preferences.mode || "balanced"}</dd>
              <dt>GPU / CPU utilization</dt>
              <dd>
                {number(w.data.telemetry.gpu_utilization)}% /{" "}
                {number(w.data.telemetry.cpu_percent)}%
              </dd>
              <dt>RAM / GPU temperature</dt>
              <dd>
                {number(w.data.telemetry.ram_percent)}% /{" "}
                {number(w.data.telemetry.gpu_temperature)} °C
              </dd>
              <dt>Last heartbeat</dt>
              <dd>{when(w.last_seen)}</dd>
              <dt>Joined</dt>
              <dd>{when(w.data.registered)}</dd>
              <dt>Current attempt</dt>
              <dd>{w.data.current_attempt || "—"}</dd>
              <dt>OS</dt>
              <dd>{w.data.capabilities.os}</dd>
            </dl>
            <details>
              <summary>Hardware, preferences and compatibility</summary>
              <pre>
                {JSON.stringify(
                  {
                    capabilities: w.data.capabilities,
                    preferences: w.data.preferences,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </section>
          <section className="section">
            <h2>Execution history</h2>
            {w.attempts.length ? (
              w.attempts.map((a: Entity) => (
                <details key={a.id}>
                  <summary>
                    {short(a.job_id)} · {a.status} · {when(a.data.started)}
                  </summary>
                  <p>Ended: {when(a.data.ended)}</p>
                  <pre>{a.data.logs || "No training logs reported yet."}</pre>
                </details>
              ))
            ) : (
              <Empty title="No attempts yet">
                This worker will appear here after it accepts an eligible job.
              </Empty>
            )}
          </section>
        </>
      )}
    </>
  );
}
const filterFields = [
  ["status", "Status"],
  ["aggregator", "Aggregator"],
  ["attack", "Attack"],
  ["condition", "Channel"],
  ["seed", "Seed"],
  ["worker_id", "Worker"],
] as const;
function Experiments() {
  const [filters, setFilters] = useState<Record<string, string>>({}),
    [search, setSearch] = useState("");
  const query = new URLSearchParams(
    Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
  ).toString();
  const { data, error } = useData<Entity[]>(
      "/experiments" + (query ? "?" + query : ""),
    ),
    { data: all } = useData<Entity[]>("/experiments");
  const choices = (field: string) =>
    Array.from(
      new Set(
        (all || [])
          .map((j) =>
            field === "status"
              ? j.status
              : field === "condition"
                ? j.data.scenario.replace(/^(clean|sign_flip|alie|ipm)_/, "")
                : field === "worker_id"
                  ? j.worker_id
                  : j.data.config[field],
          )
          .filter((v) => v !== null && v !== undefined),
      ),
    ).sort();
  const shown = (data || []).filter((j) =>
    JSON.stringify([j.id, j.data.config.name])
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <>
      <PageHead
        title="Experiments"
        description="Frozen scientific configurations, durable attempts, explicit outcomes."
      />
      <div className="filters">
        <label className="search">
          <Search size={16} />
          <input
            aria-label="Search experiments"
            placeholder="Search ID or experiment name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        {filterFields.map(([key, label]) => (
          <label key={key}>
            {label}
            <select
              value={filters[key] || ""}
              onChange={(e) =>
                setFilters({ ...filters, [key]: e.target.value })
              }
            >
              <option value="">All</option>
              {choices(key).map((x) => (
                <option key={String(x)} value={String(x)}>
                  {String(x)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <ErrorBox error={error} />
      {!data ? (
        <p>Loading experiments…</p>
      ) : !shown.length ? (
        <Empty title="No matching experiments">
          Plan a study from Overview, or adjust the filters.
        </Empty>
      ) : (
        <>
          <p className="hint">{shown.length} experiments</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Experiment</th>
                  <th>Seed</th>
                  <th>Method / attack</th>
                  <th>Channel</th>
                  <th>Status</th>
                  <th>Worker</th>
                  <th>Round</th>
                  <th>Runtime</th>
                  <th>Checkpoint</th>
                  <th>Retries</th>
                  <th>Final accuracy</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((j) => (
                  <tr key={j.id}>
                    <td>
                      <Link to={"/experiments/" + j.id}>
                        {short(j.id)}
                        <ChevronRight size={14} />
                      </Link>
                      <small>{j.data.config.name}</small>
                    </td>
                    <td>{j.data.seed}</td>
                    <td>
                      {j.data.config.aggregator}
                      <small>{j.data.config.attack}</small>
                    </td>
                    <td>
                      {j.data.scenario.replace(
                        /^(clean|sign_flip|alie|ipm)_/,
                        "",
                      )}
                    </td>
                    <td>
                      <Status value={j.status} />
                    </td>
                    <td>
                      {j.worker_id ? (
                        <Link to={"/workers/" + j.worker_id}>
                          {short(j.worker_id)}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <span>
                        {j.data.current_round} / {j.data.config.rounds}
                      </span>
                      <progress
                        aria-label={"Progress " + short(j.id)}
                        max={j.data.config.rounds}
                        value={j.data.current_round}
                      />
                    </td>
                    <td>
                      {j.runtime_s == null
                        ? "—"
                        : number(j.runtime_s / 60) + " min"}
                    </td>
                    <td>{short(j.data.checkpoint)}</td>
                    <td>{j.data.retry_count}</td>
                    <td>{pct(j.data.summary?.final_test_acc)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
const metrics: Record<string, string> = {
  test_acc: "Test accuracy",
  train_loss: "Training loss",
  test_loss: "Test loss",
  mean_pdr: "Packet delivery ratio",
  mean_latency_s: "Communication latency (s)",
  honest_rejection_rate: "Honest rejection rate",
  attacker_acceptance_rate: "Attacker acceptance rate",
};
function ExperimentDetail() {
  const { id } = useParams(),
    { data: j, error } = useData<Entity>("/experiments/" + id),
    [metric, setMetric] = useState("test_acc");
  const attempts: Entity[] = j?.attempts || [];
  const history = j?.history?.length
    ? j.history
    : attempts.at(-1)?.data.metrics || [];
  const latest = history.at(-1) || {};
  return (
    <>
      <PageHead
        title={"Experiment " + short(id)}
        description={j?.data.config.name || "Loading experiment…"}
      />
      <ErrorBox error={error} />
      {j && (
        <>
          <div className="detail-toolbar">
            <Status value={j.status} />
            <span>
              Round {j.data.current_round} / {j.data.config.rounds}
            </span>
            <span>{j.data.retry_count} retries</span>
          </div>
          <div className="stats">
            <Stat label="Latest test accuracy" value={pct(latest.test_acc)} />
            <Stat label="Training loss" value={number(latest.train_loss, 4)} />
            <Stat
              label="Packet delivery ratio"
              value={number(latest.mean_pdr, 3)}
            />
            <Stat
              label="Communication latency"
              value={
                latest.mean_latency_s == null
                  ? "—"
                  : number(latest.mean_latency_s, 3) + " s"
              }
            />
          </div>
          <section className="section">
            <div className="section-head">
              <h2>Round metrics</h2>
              <label className="chart-select">
                Metric
                <select
                  value={metric}
                  onChange={(e) => setMetric(e.target.value)}
                >
                  {Object.entries(metrics).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {history.length ? (
              <div
                className="chart"
                role="img"
                aria-label={metrics[metric] + " by completed round"}
              >
                <ResponsiveContainer width="100%" height={290}>
                  <LineChart data={history}>
                    <CartesianGrid stroke="#303c4d" vertical={false} />
                    <XAxis dataKey="round" stroke="#9aaabe" />
                    <YAxis
                      stroke="#9aaabe"
                      width={65}
                      domain={["auto", "auto"]}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#1b2736",
                        border: "1px solid #40516a",
                        color: "#eef4fc",
                      }}
                    />
                    <Line
                      type="linear"
                      dataKey={metric}
                      stroke="#76b6ee"
                      dot={false}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty title="Waiting for completed rounds">
                Metrics will appear after the worker reports a completed FL
                round.
              </Empty>
            )}
            <p className="hint">
              Scientific values are displayed directly from the simulator. Test
              accuracy and rates use their original 0–1 scale.
            </p>
          </section>
          <section className="section">
            <h2>Configuration & provenance</h2>
            <dl className="facts">
              <dt>Seed / aggregation</dt>
              <dd>
                {j.data.seed} / {j.data.config.aggregator}
              </dd>
              <dt>Attack / channel</dt>
              <dd>
                {j.data.config.attack} / {j.data.scenario}
              </dd>
              <dt>Source fingerprint</dt>
              <dd>
                <code>{j.data.source_sha256}</code>
              </dd>
              <dt>Scientific config hash</dt>
              <dd>
                <code>{j.data.config_hash}</code>
              </dd>
              <dt>Latest checkpoint</dt>
              <dd>
                {j.checkpoints.some((c: Entity) => c.data.valid)
                  ? "Round " +
                    Math.max(
                      ...j.checkpoints
                        .filter((c: Entity) => c.data.valid)
                        .map((c: Entity) => c.round),
                    )
                  : "No valid recovery point"}
              </dd>
            </dl>
            <details>
              <summary>Complete scientific configuration</summary>
              <pre>{JSON.stringify(j.data.config, null, 2)}</pre>
            </details>
            <details>
              <summary>Runtime & data provenance</summary>
              <pre>
                {JSON.stringify(
                  j.runtime || { datasets: j.data.datasets },
                  null,
                  2,
                )}
              </pre>
            </details>
          </section>
          <section className="section">
            <h2>Attempts & execution logs</h2>
            {attempts.length ? (
              attempts.map((a) => (
                <details key={a.id}>
                  <summary>
                    {short(a.id)} · {a.status} · worker {short(a.worker_id)}
                  </summary>
                  <dl className="facts">
                    <dt>Started</dt>
                    <dd>{when(a.data.started)}</dd>
                    <dt>Ended</dt>
                    <dd>{when(a.data.ended)}</dd>
                    <dt>Failure</dt>
                    <dd>{a.data.failure || "—"}</dd>
                  </dl>
                  <pre>
                    {a.data.logs ||
                      a.data.diagnostics ||
                      "No training logs reported yet."}
                  </pre>
                  <details>
                    <summary>Attempt environment</summary>
                    <pre>{JSON.stringify(a.data.runtime, null, 2)}</pre>
                  </details>
                </details>
              ))
            ) : (
              <p>No attempts assigned.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}
function Checkpoints() {
  const { data, error } = useData<Entity[]>("/checkpoints"),
    [failure, setFailure] = useState("");
  async function get(id: string) {
    try {
      await download("/artifacts/" + id + "/download", id + ".zip");
    } catch (e) {
      setFailure((e as Error).message);
    }
  }
  return (
    <>
      <PageHead
        title="Checkpoints"
        description="Validated recovery points, retained with their originating attempts."
      />
      <ErrorBox error={error || failure} />
      {!data ? (
        <p>Loading checkpoints…</p>
      ) : !data.length ? (
        <Empty title="No durable checkpoints yet">
          Workers publish after 10 completed rounds, 180 seconds at a boundary,
          or a graceful pause.
        </Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Experiment</th>
                <th>Round</th>
                <th>Created</th>
                <th>Size</th>
                <th>Validation / retention</th>
                <th>Checksum</th>
                <th>Attempt</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link to={"/experiments/" + c.job_id}>
                      {short(c.job_id)}
                    </Link>
                    <small>{c.data.path}</small>
                  </td>
                  <td>{c.round}</td>
                  <td>{when(c.data.created)}</td>
                  <td>{number(c.data.size / 1024 ** 2, 2)} MiB</td>
                  <td>
                    <Status value={c.data.valid ? "SUCCEEDED" : "FAILED"} />
                    <small>{c.data.retention}</small>
                  </td>
                  <td>
                    <code title={c.data.sha256}>{short(c.data.sha256)}</code>
                  </td>
                  <td>{short(c.attempt_id)}</td>
                  <td>
                    <button
                      aria-label={"Download checkpoint round " + c.round}
                      disabled={!c.data.valid}
                      onClick={() => get(c.id)}
                    >
                      <ArrowDownToLine size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint">
        Checkpoints used by active attempts are protected. Retention maintenance
        keeps the latest two recovery points for inactive jobs.
      </p>
    </>
  );
}
function Logs() {
  const [search, setSearch] = useState(""),
    { data, error } = useData<Entity[]>("/events"),
    [failure, setFailure] = useState("");
  return (
    <>
      <PageHead
        title="Logs & events"
        description="Assignments, scientific outcomes and recovery decisions."
        action={
          <button
            onClick={() =>
              download("/events/download", "events.ndjson").catch((e) =>
                setFailure(e.message),
              )
            }
          >
            <ArrowDownToLine size={15} />
            Download latest 500
          </button>
        }
      />
      <label className="search log-search">
        <Search size={16} />
        <input
          aria-label="Filter events"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by event or entity ID"
        />
      </label>
      <ErrorBox error={error || failure} />
      {data ? (
        <section className="section">
          {data.length ? (
            <Events
              events={data.filter((e) =>
                JSON.stringify(e).toLowerCase().includes(search.toLowerCase()),
              )}
            />
          ) : (
            <Empty title="No events recorded">
              Activity will appear as workers join and jobs run.
            </Empty>
          )}
        </section>
      ) : (
        <p>Loading events…</p>
      )}
    </>
  );
}
const settingNames: Record<string, string> = {
  heartbeat_interval: "Heartbeat interval (seconds)",
  suspect_timeout: "Worker suspect timeout (seconds)",
  lease_timeout: "Lease timeout (seconds)",
  retry_delay: "Initial retry delay (seconds)",
  max_retry_delay: "Maximum retry delay (seconds)",
  max_retries: "Maximum infrastructure retries",
  checkpoint_every_rounds: "Checkpoint frequency (rounds)",
  checkpoint_every_seconds: "Checkpoint interval (seconds)",
  max_workers: "Maximum workers",
  max_concurrent: "Maximum concurrent experiments",
  disk_warning_bytes: "Disk warning threshold (bytes)",
  disk_critical_bytes: "Disk critical threshold (bytes)",
  max_upload_bytes: "Maximum upload size (bytes)",
  checkpoint_keep: "Checkpoints retained per inactive job",
  enrollment_enabled: "Allow worker enrollment",
  automatic_start: "Automatic start policy",
};
function SettingsPage() {
  const { data, error, reload } =
      useData<Record<string, number | boolean>>("/settings"),
    [failure, setFailure] = useState(""),
    [saved, setSaved] = useState(false),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setSaved(false);
    const f = new FormData(e.currentTarget);
    const body = Object.fromEntries(
      Object.entries(data || {}).map(([k, v]) => [
        k,
        typeof v === "boolean" ? f.get(k) === "on" : Number(f.get(k)),
      ]),
    );
    try {
      await api("/settings", "PUT", body);
      setSaved(true);
      setFailure("");
      reload();
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHead
        title="Coordinator settings"
        description="Scheduling, recovery timing and storage policies."
      />
      <ErrorBox error={error || failure} />
      {data && (
        <form className="section" onSubmit={submit}>
          <div className="form-grid settings-grid">
            {Object.entries(data).map(([k, v]) => (
              <label
                className={typeof v === "boolean" ? "checkbox" : ""}
                key={k}
              >
                {typeof v === "boolean" ? (
                  <>
                    <input name={k} type="checkbox" defaultChecked={v} />
                    {settingNames[k] || k}
                  </>
                ) : (
                  <>
                    {settingNames[k] || k}
                    <input
                      name={k}
                      type="number"
                      min="1"
                      required
                      defaultValue={v}
                    />
                  </>
                )}
              </label>
            ))}
          </div>
          <p className="hint">
            Changes take effect on subsequent leases and worker heartbeats.
            Owners grant administrative controls per worker using their local
            preferences. Autostart stays opt-in on each laptop.
          </p>
          <div className="actions">
            <button disabled={busy} className="primary">
              {busy ? "Saving…" : "Save settings"}
            </button>
            {saved && (
              <span className="saved" role="status">
                <Check size={16} />
                Settings saved
              </span>
            )}
          </div>
        </form>
      )}
      <PasswordForm />
    </>
  );
}
function PasswordForm() {
  const [error, setError] = useState(""),
    [saved, setSaved] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api("/auth/password", "POST", {
        current_password: f.get("current"),
        new_password: f.get("next"),
      });
      setSaved(true);
      setError("");
      (e.target as HTMLFormElement).reset();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <form className="section" onSubmit={submit}>
      <h2>Change your password</h2>
      <div className="form-grid">
        <label>
          Current password
          <input
            name="current"
            type="password"
            autoComplete="current-password"
            required
          />
        </label>
        <label>
          New password
          <input
            name="next"
            type="password"
            autoComplete="new-password"
            minLength={12}
            required
          />
        </label>
      </div>
      <ErrorBox error={error} />
      <div className="actions">
        <button>Update password</button>
        {saved && <span role="status">Password updated.</span>}
      </div>
    </form>
  );
}
function Help() {
  return (
    <>
      <PageHead
        title="Setup & participation"
        description="Keep the study running while owners stay in control."
      />
      <div className="help-content">
        <section className="section">
          <h2>Join a reachable coordinator</h2>
          <p>
            Use a trusted router, wired LAN, or an authorized Tailscale tailnet.
            Campus Wi-Fi can block communication between devices even on the
            same SSID. Check the host firewall and open{" "}
            <code>http://HOST_IP:8787/health</code> from the worker.
          </p>
          <p>
            Install with <code>scripts/install-worker.ps1</code> on Windows or{" "}
            <code>bash scripts/install-worker.sh</code> on Linux. Prepare the
            same datasets and trace, then join using a one-time code.
          </p>
          <pre>
            {"swarm join --server " +
              window.location.origin +
              "\nswarm doctor\nswarm start"}
          </pre>
        </section>
        <section className="section">
          <h2>Power, sleep & ventilation</h2>
          <p>
            Connect the correct power adapter, keep ventilation clear, and leave
            the computer awake. Turning off the display is fine; closing the lid
            may suspend training.
          </p>
          <p>
            <strong>Windows 11:</strong> Settings → System → Power & battery →
            Screen, sleep & hibernate timeouts. Choose plugged-in sleep settings
            appropriate for participation. Review lid-close settings in Power
            Options.
          </p>
          <p>
            <strong>Linux:</strong> Review desktop automatic suspend and lid
            behavior. A systemd user service can restart the agent, but cannot
            override every suspend condition.
          </p>
          <p>
            <strong>macOS coordinator:</strong> Keep the lid open and review
            Battery / Lock Screen settings. An explicitly chosen{" "}
            <code>caffeinate -i swarm server start</code> can inhibit idle sleep
            while coordinating.
          </p>
          <p>
            SwarmCompute does not change power settings or GPU drivers
            automatically.
          </p>
        </section>
        <section className="section">
          <h2>Pause, resume or leave</h2>
          <pre>
            {
              "swarm pause                 # drain after experiment\nswarm pause --after-round   # checkpoint and release\nswarm resume\nswarm leave\nswarm autostart disable"
            }
          </pre>
          <p>
            A sudden shutdown recovers from the latest checkpoint already
            validated by the coordinator. An offline worker keeps local files,
            but cannot publish after losing its lease. Numerical divergence
            remains a terminal scientific outcome.
          </p>
        </section>
        <PasswordForm />
      </div>
    </>
  );
}
function Shell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const live = useLive(),
    [open, setOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null),
    menuRef = useRef<HTMLButtonElement>(null);
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width:760px)").matches,
  );
  useEffect(() => {
    const media = window.matchMedia("(max-width:760px)");
    const change = () => setMobile(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (!open || !mobile) return;
    const nav = navRef.current;
    nav?.querySelector<HTMLElement>("a")?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        menuRef.current?.focus();
      }
      if (e.key === "Tab" && nav) {
        const nodes = Array.from(
          nav.querySelectorAll<HTMLElement>("a,button:not(:disabled)"),
        );
        const first = nodes[0],
          last = nodes.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [open, mobile]);
  function closeNav() {
    setOpen(false);
    if (mobile) menuRef.current?.focus();
  }

  const navigation: [string, string, LucideIcon][] = [
    ["/", "Overview", LayoutDashboard],
    ["/workers", "Workers", Monitor],
    ...(user.role === "admin"
      ? ([
          ["/experiments", "Experiments", Activity],
          ["/checkpoints", "Checkpoints", Database],
          ["/logs", "Logs & events", Terminal],
          ["/settings", "Settings", Settings],
        ] as [string, string, LucideIcon][])
      : []),
    ["/help", "Setup & help", CircleHelp],
  ];
  return (
    <div className="app-shell">
      <aside
        id="main-sidebar"
        ref={navRef}
        inert={mobile && !open}
        aria-hidden={mobile && !open}
        className={open ? "sidebar open" : "sidebar"}
      >
        <Link className="brand" to="/">
          <Activity size={24} />
          <span>SwarmCompute</span>
        </Link>
        <nav aria-label="Main navigation">
          {navigation.map(([url, label, Icon]) => (
            <NavLink end={url === "/"} key={url} to={url} onClick={closeNav}>
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="identity">
            <span className="avatar">{user.username[0].toUpperCase()}</span>
            <div>
              <strong>{user.username}</strong>
              <small>
                {user.role === "admin" ? "Administrator" : "Laptop owner"}
              </small>
            </div>
            <button aria-label="Sign out" onClick={onLogout}>
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      {open && (
        <button
          className="nav-scrim"
          aria-label="Close navigation"
          onClick={closeNav}
        />
      )}
      <div className="main-column">
        <div className="topbar">
          <button
            ref={menuRef}
            className="mobile-menu"
            aria-controls="main-sidebar"
            aria-expanded={open}
            aria-label="Open navigation"
            onClick={() => setOpen(!open)}
          >
            <Menu size={20} />
          </button>
          <span>
            Research compute <ChevronRight size={14} />
            <strong>Local coordinator</strong>
          </span>
          <span className="live">
            <span className={"status-dot " + (live ? "online" : "")} />
            {live ? "Live updates" : "Polling every 10s"}
          </span>
        </div>
        <main className="content">
          <Routes>
            <Route path="/" element={<Overview user={user} />} />
            <Route path="/workers" element={<Workers user={user} />} />
            <Route path="/workers/:id" element={<WorkerDetail user={user} />} />
            {user.role === "admin" && (
              <>
                <Route path="/experiments" element={<Experiments />} />
                <Route path="/experiments/:id" element={<ExperimentDetail />} />
                <Route path="/checkpoints" element={<Checkpoints />} />
                <Route path="/logs" element={<Logs />} />
                <Route path="/settings" element={<SettingsPage />} />
              </>
            )}
            <Route path="/help" element={<Help />} />
            <Route
              path="*"
              element={
                <Empty title="Page not found">
                  <Link to="/">Return to cluster overview</Link>
                </Empty>
              }
            />
          </Routes>
          <footer>
            SwarmCompute <span>Independent FL simulations · self-hosted</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
export default function App() {
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(!!getToken());
  useEffect(() => {
    if (getToken())
      api("/auth/me")
        .then(setUser)
        .catch(() => setToken(""))
        .finally(() => setLoading(false));
    const logout = () => setUser(null);
    window.addEventListener("swarm-logout", logout);
    return () => window.removeEventListener("swarm-logout", logout);
  }, []);
  async function logout() {
    try {
      await api("/auth/logout", "POST");
    } finally {
      setToken("");
      setUser(null);
    }
  }
  if (loading)
    return (
      <main className="login">
        <p>Connecting to coordinator…</p>
      </main>
    );
  return user ? (
    <Shell user={user} onLogout={logout} />
  ) : (
    <Login onLogin={setUser} />
  );
}
