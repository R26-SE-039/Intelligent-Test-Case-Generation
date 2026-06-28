"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Eye,
  EyeOff,
  GitBranch,
  Loader2,
  Plug,
  RefreshCcw,
  Trash2,
  Unplug,
  Zap,
} from "lucide-react";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import { useProject } from "@/lib/project-context";
import {
  connectGitHub,
  disconnectGitHub,
  getGitHubConnection,
  pingGitHubConnection,
  reinstallGitHubWorkflow,
  validateGitHubToken,
  type GitHubConnection,
  type GitHubConnectResponse,
  type GitHubPingResponse,
  type GitHubRepo,
  type GitHubValidateResponse,
} from "@/lib/api";

const TOKEN_HELP_URL =
  "https://github.com/settings/tokens/new?scopes=repo,workflow&description=NextGen+QA+Test+Runner";

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const min = Math.round(diff / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return d.toLocaleString();
}

export default function GitHubConnectPage() {
  const { activeProject } = useProject();

  const [connection, setConnection] = useState<GitHubConnection | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Connect flow state
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<GitHubValidateResponse | null>(null);
  const [selectedRepoFull, setSelectedRepoFull] = useState<string>("");
  const [connecting, setConnecting] = useState(false);
  const [connectResult, setConnectResult] = useState<GitHubConnectResponse | null>(null);

  // Disconnect / ping state
  const [reinstalling, setReinstalling] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [pingResult, setPingResult] = useState<GitHubPingResponse | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  const loadConnection = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    setError(null);
    try {
      const c = await getGitHubConnection(activeProject.id);
      setConnection(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load connection");
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    void loadConnection();
  }, [loadConnection]);

  // Reset the connect form whenever we switch projects.
  useEffect(() => {
    setToken("");
    setValidation(null);
    setSelectedRepoFull("");
    setConnectResult(null);
    setPingResult(null);
  }, [activeProject?.id]);

  const selectedRepo: GitHubRepo | null = useMemo(() => {
    if (!validation) return null;
    return validation.repos.find((r) => r.full_name === selectedRepoFull) ?? null;
  }, [validation, selectedRepoFull]);

  const handleValidate = async () => {
    if (!token.trim()) return;
    setValidating(true);
    setError(null);
    setValidation(null);
    setSelectedRepoFull("");
    try {
      const v = await validateGitHubToken(token.trim());
      setValidation(v);
      if (v.repos.length > 0) setSelectedRepoFull(v.repos[0].full_name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Token validation failed");
    } finally {
      setValidating(false);
    }
  };

  const handleConnect = async (force = false) => {
    if (!activeProject || !selectedRepo || !token.trim()) return;
    setConnecting(true);
    setError(null);
    setConnectResult(null);
    try {
      const resp = await connectGitHub(activeProject.id, {
        token: token.trim(),
        owner: selectedRepo.owner,
        repo: selectedRepo.name,
        default_branch: selectedRepo.default_branch,
        force_workflow_overwrite: force,
      });
      setConnectResult(resp);
      setConnection(resp.connection);
      if (resp.workflow_status !== "conflict") {
        // Clear the entry form on a successful connect.
        setToken("");
        setValidation(null);
        setSelectedRepoFull("");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connect failed");
    } finally {
      setConnecting(false);
    }
  };

  const handleReinstall = async () => {
    if (!activeProject) return;
    setReinstalling(true);
    setError(null);
    try {
      const resp = await reinstallGitHubWorkflow(activeProject.id);
      setConnection(resp.connection);
      setConnectResult(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reinstall failed");
    } finally {
      setReinstalling(false);
    }
  };

  const handlePing = async () => {
    if (!activeProject) return;
    setPinging(true);
    setError(null);
    setPingResult(null);
    try {
      const r = await pingGitHubConnection(activeProject.id);
      setPingResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ping failed");
    } finally {
      setPinging(false);
    }
  };

  const handleDisconnect = async () => {
    if (!activeProject) return;
    if (!confirm("Disconnect this project from GitHub? The workflow file on the repo will be left in place.")) return;
    setDisconnecting(true);
    setError(null);
    try {
      await disconnectGitHub(activeProject.id);
      setConnection(null);
      setConnectResult(null);
      setPingResult(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Disconnect failed");
    } finally {
      setDisconnecting(false);
    }
  };

  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm border-b border-slate-200 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full tracking-wider">
                GH
              </span>
              <span className="text-xs text-slate-500">Project Integrations</span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900">GitHub Connect</h1>
            <p className="text-slate-600 text-sm mt-0.5">
              Wire this project to a GitHub repo so test runs execute on GitHub Actions instead of the local fallback.
            </p>
          </div>
        </div>
      </div>

      <div className="p-6 max-w-4xl mx-auto space-y-5">
        {!activeProject && (
          <div className="p-4 rounded-xl border border-amber-200 bg-amber-50 text-amber-800 text-sm">
            Select a project from the sidebar before configuring a GitHub connection.
          </div>
        )}

        {error && (
          <div className="p-3 rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Current connection card */}
        {loading ? (
          <div className="p-6 rounded-xl border border-slate-200 bg-white animate-pulse h-32" />
        ) : connection ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                {connection.github_user_avatar_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={connection.github_user_avatar_url}
                    alt={connection.github_user_login ?? "user"}
                    className="w-12 h-12 rounded-full border border-emerald-300"
                  />
                )}
                <div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    <p className="text-sm font-semibold text-emerald-800">Connected</p>
                  </div>
                  <p className="text-lg font-bold text-slate-900 mt-0.5">
                    {connection.repo_full}
                  </p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-600">
                    <span className="inline-flex items-center gap-1">
                      <GitBranch className="w-3 h-3" /> {connection.default_branch}
                    </span>
                    {connection.github_user_login && (
                      <span>as @{connection.github_user_login}</span>
                    )}
                    <span className="font-mono">{connection.token_preview}</span>
                  </div>
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <a
                  href={`https://github.com/${connection.repo_full}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-purple-700 hover:text-purple-900 underline"
                >
                  Open on GitHub <ExternalLink className="w-3 h-3" />
                </a>
                <span className="text-[11px] text-slate-500">
                  Last validated {formatRelative(connection.last_validated_at)}
                </span>
              </div>
            </div>

            {/* Workflow status row */}
            <div className="mt-4 p-3 rounded-lg bg-white border border-slate-200 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm">
                {connection.workflow_installed ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    <span className="text-slate-800">
                      Workflow file installed on <code className="text-xs bg-slate-100 px-1 py-0.5 rounded font-mono">.github/workflows/nextgenqa-run.yml</code>
                    </span>
                  </>
                ) : (
                  <>
                    <AlertTriangle className="w-4 h-4 text-amber-600" />
                    <span className="text-slate-800">Workflow file is missing on the default branch.</span>
                  </>
                )}
              </div>
              <button
                onClick={handleReinstall}
                disabled={reinstalling}
                className="text-xs px-3 py-1.5 border border-slate-300 hover:border-slate-400 hover:bg-slate-50 rounded-md transition-all flex items-center gap-1.5 disabled:opacity-50"
                title="Force-reinstall the workflow YAML"
              >
                {reinstalling ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCcw className="w-3 h-3" />}
                Reinstall workflow
              </button>
            </div>

            {/* Actions */}
            <div className="mt-4 flex items-center gap-2">
              <button
                onClick={handlePing}
                disabled={pinging}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-xs font-medium rounded-md transition-all"
              >
                {pinging ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                Test ping
              </button>
              <button
                onClick={handleDisconnect}
                disabled={disconnecting}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-red-300 text-red-700 hover:bg-red-50 text-xs font-medium rounded-md transition-all disabled:opacity-50"
              >
                {disconnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unplug className="w-3.5 h-3.5" />}
                Disconnect
              </button>
              <Link
                href="/dashboard/execution"
                className="ml-auto text-xs text-purple-700 hover:text-purple-900 underline"
              >
                Go to Execution →
              </Link>
            </div>

            {pingResult && (() => {
              const detail = pingResult.detail ?? "";
              // The backend returns "Token decryption failed..." when the
              // stored ciphertext can't be unsealed with the current Fernet
              // key — usually because NEXTGENQA_CRYPTO_KEY changed (or was
              // ephemeral before .env was set). The only recovery is to
              // delete this row and reconnect with a fresh token.
              const isDecryptionError = !pingResult.ok && /decrypt/i.test(detail);

              if (isDecryptionError) {
                return (
                  <div className="mt-3 p-3 rounded-md border border-red-300 bg-red-50 text-xs space-y-2">
                    <div className="flex items-start gap-2 text-red-700">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <div>
                        <p className="font-semibold mb-0.5">Token can no longer be decrypted</p>
                        <p>{detail}</p>
                      </div>
                    </div>
                    <button
                      onClick={handleDisconnect}
                      disabled={disconnecting}
                      className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-semibold rounded-md transition-all"
                    >
                      {disconnecting ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <RefreshCcw className="w-3.5 h-3.5" />
                      )}
                      Reset connection (delete the unreadable record)
                    </button>
                    <p className="text-[11px] text-slate-500 text-center">
                      After resetting, paste a fresh PAT in the form below to reconnect. The
                      workflow file on the repo stays in place.
                    </p>
                  </div>
                );
              }

              return (
                <div className={`mt-3 p-2.5 rounded-md text-xs border ${
                  pingResult.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-red-200 bg-red-50 text-red-700"
                }`}>
                  {pingResult.ok ? (
                    <>
                      OK — authenticated as <strong>@{pingResult.login}</strong>
                      {pingResult.rate_limit_remaining != null && (
                        <> · rate-limit remaining: {pingResult.rate_limit_remaining}</>
                      )}
                      <> · workflow {pingResult.workflow_present ? "present" : "MISSING"}</>
                      {pingResult.detail && <div className="mt-1 text-amber-700">{pingResult.detail}</div>}
                    </>
                  ) : (
                    detail || "Connection check failed"
                  )}
                </div>
              );
            })()}
          </div>
        ) : null}

        {/* Connect / re-connect form */}
        {activeProject && (
          <div className="rounded-xl border border-slate-200 bg-white p-6">
            <div className="flex items-center gap-2 mb-1">
              <Plug className="w-4 h-4 text-purple-600" />
              <h2 className="text-base font-bold text-slate-900">
                {connection ? "Replace connection" : "Connect this project to GitHub"}
              </h2>
            </div>
            <p className="text-xs text-slate-500 mb-4">
              Tokens are encrypted (Fernet) before being stored. The dashboard only ever shows a masked preview.
            </p>

            {/* Step 1 — token */}
            <div className="space-y-2 mb-5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Step 1 · Personal Access Token
                </label>
                <a
                  href={TOKEN_HELP_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-purple-700 hover:text-purple-900 inline-flex items-center gap-1 underline"
                >
                  Create token on GitHub <ExternalLink className="w-3 h-3" />
                </a>
              </div>
              <p className="text-[11px] text-slate-500">
                Scopes required: <code className="font-mono">repo</code> · <code className="font-mono">workflow</code>
              </p>
              <div className="flex items-stretch gap-2">
                <div className="relative flex-1">
                  <input
                    type={showToken ? "text" : "password"}
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                    className="w-full px-3 py-2 pr-10 border border-slate-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <button
                    type="button"
                    onClick={() => setShowToken((s) => !s)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                    aria-label={showToken ? "Hide token" : "Show token"}
                  >
                    {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <button
                  onClick={handleValidate}
                  disabled={validating || !token.trim()}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-900 disabled:opacity-50 text-white text-sm font-medium rounded-md transition-all inline-flex items-center gap-2"
                >
                  {validating ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                  Validate
                </button>
              </div>
            </div>

            {/* Step 2 — pick a repo (only shown after validate) */}
            {validation && (
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                  Step 2 · Pick the repo to receive test runs
                </label>
                <div className="flex items-center gap-3 mb-2">
                  {validation.avatar_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={validation.avatar_url}
                      alt={validation.login}
                      className="w-8 h-8 rounded-full border border-slate-200"
                    />
                  )}
                  <div className="text-sm">
                    <span className="text-slate-900 font-semibold">@{validation.login}</span>
                    {validation.name && <span className="text-slate-500 ml-1">({validation.name})</span>}
                    <span className="text-slate-500 ml-2">· {validation.repo_count} repos</span>
                  </div>
                </div>

                <select
                  value={selectedRepoFull}
                  onChange={(e) => setSelectedRepoFull(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm bg-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  {validation.repos.length === 0 && <option value="">No accessible repos</option>}
                  {validation.repos.map((r) => (
                    <option key={r.full_name} value={r.full_name}>
                      {r.full_name} {r.private ? "(private)" : ""} · default: {r.default_branch}
                    </option>
                  ))}
                </select>

                <div className="pt-3 flex items-center gap-2">
                  <button
                    onClick={() => handleConnect(false)}
                    disabled={!selectedRepo || connecting}
                    className="inline-flex items-center gap-2 px-5 py-2 bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 disabled:opacity-50 text-white text-sm font-semibold rounded-md transition-all shadow-md shadow-purple-600/30"
                  >
                    {connecting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />}
                    Connect &amp; install workflow
                  </button>
                  {selectedRepo && (
                    <span className="text-xs text-slate-500">
                      will push <code className="font-mono">.github/workflows/nextgenqa-run.yml</code> to <code className="font-mono">{selectedRepo.default_branch}</code>
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Conflict resolver */}
            {connectResult?.workflow_status === "conflict" && (
              <div className="mt-4 p-3 rounded-lg border border-amber-300 bg-amber-50 text-sm text-amber-900">
                <div className="flex items-start gap-2 mb-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <p>{connectResult.workflow_message}</p>
                </div>
                <button
                  onClick={() => handleConnect(true)}
                  disabled={connecting}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold rounded-md disabled:opacity-50"
                >
                  {connecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCcw className="w-3.5 h-3.5" />}
                  Overwrite anyway
                </button>
              </div>
            )}

            {/* Success banner */}
            {connectResult && connectResult.workflow_status !== "conflict" && (
              <div className="mt-4 p-3 rounded-lg border border-emerald-200 bg-emerald-50 text-sm text-emerald-800 flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  Connected to <strong>{connectResult.connection.repo_full}</strong>.{" "}
                  Workflow {connectResult.workflow_status === "already_present" ? "was already up to date" : "installed successfully"}.
                </span>
              </div>
            )}
          </div>
        )}

        {/* Token deletion footnote */}
        {connection && (
          <p className="text-[11px] text-slate-500 text-center flex items-center justify-center gap-1.5">
            <Trash2 className="w-3 h-3" />
            Disconnecting only removes the row from the database — the workflow file on your repo is preserved.
          </p>
        )}
      </div>
    </DashboardLayoutWrapper>
  );
}
