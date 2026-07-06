import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import PageAlerts from "../components/PageAlerts.jsx";
import ThresholdSectionEditor from "../components/ThresholdSectionEditor.jsx";
import {
  INTERVALS,
  PREVIEW_SUMMARY_PATHS,
  THRESHOLD_SECTIONS,
  TRADING_STYLES,
} from "../constants/thresholdSections.js";
import {
  cloneConfig,
  diffPatch,
  formatBacktestMetrics,
  formatMetric,
  getNestedValue,
} from "../utils/thresholdConfig.js";
import { withNotice } from "../hooks/usePageLoad.js";

const TABS = [
  ["overview", "Overview"],
  ["editor", "Editor"],
  ["overrides", "Overrides"],
  ["versions", "Versions"],
  ["preview", "Preview"],
  ["backtest", "Backtest"],
  ["advanced", "Advanced JSON"],
];

function TabButton({ active, children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded px-3 py-1.5 text-sm ${
        active
          ? "bg-[#21262d] text-white ring-1 ring-[#2f81f7]"
          : "text-[#8b949e] hover:bg-[#21262d] hover:text-white"
      }`}
    >
      {children}
    </button>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded border border-[#30363d] bg-[#0d1117] p-3">
      <div className="text-[10px] uppercase tracking-wide text-[#8b949e]">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

export default function ThresholdsPage() {
  const [tab, setTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [activePayload, setActivePayload] = useState(null);
  const [versions, setVersions] = useState([]);
  const [overrides, setOverrides] = useState([]);

  const [baselineConfig, setBaselineConfig] = useState({});
  const [draftConfig, setDraftConfig] = useState({});
  const [editorSection, setEditorSection] = useState(THRESHOLD_SECTIONS[0].id);

  const [advancedJson, setAdvancedJson] = useState("{}");
  const [patchNotes, setPatchNotes] = useState("");

  const [resolvePair, setResolvePair] = useState("EURUSD");
  const [resolveInterval, setResolveInterval] = useState("60min");
  const [resolveStyle, setResolveStyle] = useState("intraday");
  const [resolved, setResolved] = useState(null);

  const [overrideSymbol, setOverrideSymbol] = useState("EURUSD");
  const [overrideInterval, setOverrideInterval] = useState("*");
  const [overrideStyle, setOverrideStyle] = useState("*");
  const [overridePatchJson, setOverridePatchJson] = useState(
    '{"decision": {"score_bias_minimum": 62}}',
  );

  const [compareA, setCompareA] = useState("");
  const [compareB, setCompareB] = useState("");
  const [backtestResult, setBacktestResult] = useState(null);
  const [viewVersion, setViewVersion] = useState(null);

  const pendingPatch = useMemo(
    () => diffPatch(baselineConfig, draftConfig),
    [baselineConfig, draftConfig],
  );
  const hasPendingChanges = Boolean(pendingPatch && Object.keys(pendingPatch).length);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [activeRes, histRes, overrideRes] = await Promise.all([
        api("/thresholds/active"),
        api("/thresholds/versions?limit=50"),
        api("/thresholds/overrides"),
      ]);
      setActivePayload(activeRes);
      setVersions(histRes.versions || []);
      setOverrides(overrideRes.overrides || []);
      const cfg = cloneConfig(activeRes.config || {});
      setBaselineConfig(cfg);
      setDraftConfig(cfg);
      setAdvancedJson(JSON.stringify(cfg, null, 2));
      if (activeRes?.version?.id) {
        setCompareA(String(activeRes.version.id));
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function saveEditorChanges() {
    if (!hasPendingChanges) return;
    await withNotice(setNotice, setError, async () => {
      await api("/thresholds/active", {
        method: "PATCH",
        body: JSON.stringify({ patch: pendingPatch, notes: patchNotes || "Updated from threshold editor" }),
      });
      await loadAll();
      return true;
    }, "Threshold changes saved as a new active version");
  }

  async function discardEditorChanges() {
    setDraftConfig(cloneConfig(baselineConfig));
    setAdvancedJson(JSON.stringify(baselineConfig, null, 2));
    setNotice("Discarded unsaved changes");
  }

  async function saveAdvancedJson() {
    await withNotice(setNotice, setError, async () => {
      const config = JSON.parse(advancedJson);
      await api("/thresholds/versions", {
        method: "POST",
        body: JSON.stringify({
          version_tag: `admin-${Date.now()}`,
          config,
          activate: true,
          notes: patchNotes || "Created from advanced JSON editor",
        }),
      });
      await loadAll();
    }, "Full config saved and activated");
  }

  async function handleActivate(id) {
    await withNotice(setNotice, setError, async () => {
      await api(`/thresholds/versions/${id}/activate`, { method: "POST" });
      await loadAll();
    }, `Activated version ${id}`);
  }

  async function handleResolve() {
    await withNotice(setNotice, setError, async () => {
      const res = await api(
        `/thresholds/resolve?pair=${encodeURIComponent(resolvePair)}&interval=${encodeURIComponent(resolveInterval)}&style=${encodeURIComponent(resolveStyle)}`,
      );
      setResolved(res);
      setTab("preview");
    }, "Resolved config loaded");
  }

  async function handleOverrideSave() {
    await withNotice(setNotice, setError, async () => {
      const patch = JSON.parse(overridePatchJson);
      await api(`/thresholds/overrides/${overrideSymbol}`, {
        method: "PATCH",
        body: JSON.stringify({
          patch,
          interval: overrideInterval,
          trading_style: overrideStyle,
        }),
      });
      const overrideRes = await api("/thresholds/overrides");
      setOverrides(overrideRes.overrides || []);
    }, `Override saved for ${overrideSymbol}`);
  }

  async function handleBacktest(compare = false) {
    await withNotice(setNotice, setError, async () => {
      const body = {
        symbol: resolvePair,
        interval: resolveInterval,
        trading_style: resolveStyle,
      };
      if (compare && compareA && compareB) {
        body.version_a_id = Number(compareA);
        body.version_b_id = Number(compareB);
      }
      const res = await api("/thresholds/backtest", { method: "POST", body: JSON.stringify(body) });
      setBacktestResult(res);
      setTab("backtest");
    }, compare ? "Version comparison complete" : "Backtest complete");
  }

  async function loadVersionConfig(id) {
    await withNotice(setNotice, setError, async () => {
      const res = await api(`/thresholds/versions/${id}`);
      setViewVersion(res);
    });
  }

  const activeVersion = activePayload?.version;

  return (
    <div className="space-y-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-white">Threshold management</h1>
          <p className="mt-1 max-w-2xl text-sm text-[#8b949e]">
            Versioned SMC/ICT thresholds with validation, scoped overrides, resolve preview, and backtest comparison.
            Every save creates an immutable version and writes an audit log entry.
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/audit" className="rounded border border-[#30363d] px-3 py-1.5 text-sm text-[#c9d1d9] hover:border-[#8b949e]">
            View audit log
          </Link>
          <Link to="/settings" className="text-sm text-[#2f81f7] hover:underline self-center">
            Settings
          </Link>
        </div>
      </div>

      <PageAlerts error={error} notice={notice} onClearNotice={() => setNotice("")} />
      {loading && <p className="text-sm text-[#8b949e]">Loading threshold configuration…</p>}

      <div className="flex flex-wrap gap-2">
        {TABS.map(([id, label]) => (
          <TabButton key={id} active={tab === id} onClick={() => setTab(id)}>
            {label}
          </TabButton>
        ))}
      </div>

      {tab === "overview" && !loading && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <MetricCard
              label="Active version"
              value={activeVersion ? activeVersion.version_tag : "Defaults only"}
            />
            <MetricCard label="Version ID" value={activeVersion?.id ?? "—"} />
            <MetricCard label="Stored versions" value={versions.length} />
            <MetricCard label="Scoped overrides" value={overrides.length} />
          </div>

          <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-white">Effective preview (EURUSD · 60min · intraday)</h2>
              <button
                type="button"
                onClick={() => {
                  setResolvePair("EURUSD");
                  setResolveInterval("60min");
                  setResolveStyle("intraday");
                  handleResolve();
                }}
                className="rounded border border-[#30363d] px-2 py-1 text-xs hover:border-[#8b949e]"
              >
                Refresh preview
              </button>
            </div>
            <OverviewPreview />
          </section>

          <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <h2 className="mb-2 text-sm font-semibold text-white">Quick actions</h2>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" onClick={() => setTab("editor")} className="rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white">
                Edit thresholds
              </button>
              <button type="button" onClick={() => setTab("overrides")} className="rounded border border-[#30363d] px-3 py-1.5 text-sm">
                Manage overrides
              </button>
              <button type="button" onClick={() => handleBacktest(false)} className="rounded border border-[#30363d] px-3 py-1.5 text-sm">
                Run backtest
              </button>
            </div>
          </section>
        </div>
      )}

      {tab === "editor" && !loading && (
        <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
          <aside className="rounded-lg border border-[#30363d] bg-[#161b22] p-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[#8b949e]">Sections</p>
            <nav className="space-y-1">
              {THRESHOLD_SECTIONS.map((section) => (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setEditorSection(section.id)}
                  className={`block w-full rounded px-2 py-1.5 text-left text-sm ${
                    editorSection === section.id ? "bg-[#21262d] text-white" : "text-[#8b949e] hover:text-white"
                  }`}
                >
                  {section.label}
                </button>
              ))}
            </nav>
          </aside>

          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <ThresholdSectionEditor
              sectionId={editorSection}
              config={draftConfig}
              baseline={baselineConfig}
              onChange={setDraftConfig}
            />
            <div className="mt-6 border-t border-[#30363d] pt-4">
              <label className="mb-1 block text-xs text-[#8b949e]">Change notes (optional)</label>
              <input
                value={patchNotes}
                onChange={(e) => setPatchNotes(e.target.value)}
                placeholder="e.g. Tightened spread limits for majors"
                className="mb-3 w-full rounded border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={!hasPendingChanges}
                  onClick={saveEditorChanges}
                  className="rounded bg-[#238636] px-3 py-1.5 text-sm text-white disabled:opacity-40"
                >
                  Save as new version
                </button>
                <button
                  type="button"
                  disabled={!hasPendingChanges}
                  onClick={discardEditorChanges}
                  className="rounded border border-[#30363d] px-3 py-1.5 text-sm"
                >
                  Discard
                </button>
                {hasPendingChanges && (
                  <span className="self-center text-xs text-[#d29922]">
                    {Object.keys(pendingPatch).length} section(s) modified
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "overrides" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <h2 className="mb-3 text-sm font-semibold text-white">Existing overrides</h2>
            {overrides.length === 0 ? (
              <p className="text-sm text-[#8b949e]">No scoped overrides yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-[#8b949e]">
                    <tr>
                      <th className="py-1 pr-3">Symbol</th>
                      <th className="py-1 pr-3">Interval</th>
                      <th className="py-1 pr-3">Style</th>
                      <th className="py-1">Patch keys</th>
                    </tr>
                  </thead>
                  <tbody className="text-[#c9d1d9]">
                    {overrides.map((row) => (
                      <tr
                        key={`${row.symbol}-${row.interval}-${row.trading_style}`}
                        className="cursor-pointer border-t border-[#21262d] hover:bg-[#21262d]/50"
                        onClick={() => {
                          setOverrideSymbol(row.symbol);
                          setOverrideInterval(row.interval);
                          setOverrideStyle(row.trading_style);
                          setOverridePatchJson(JSON.stringify(row.patch || {}, null, 2));
                        }}
                      >
                        <td className="py-2 pr-3">{row.symbol}</td>
                        <td className="py-2 pr-3">{row.interval}</td>
                        <td className="py-2 pr-3">{row.trading_style}</td>
                        <td className="py-2 font-mono text-xs">{Object.keys(row.patch || {}).join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <h2 className="mb-3 text-sm font-semibold text-white">Add / edit override</h2>
            <div className="mb-3 grid grid-cols-3 gap-2">
              <input
                value={overrideSymbol}
                onChange={(e) => setOverrideSymbol(e.target.value.toUpperCase())}
                placeholder="Symbol (* for global)"
                className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm"
              />
              <select
                value={overrideInterval}
                onChange={(e) => setOverrideInterval(e.target.value)}
                className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm"
              >
                <option value="*">Any interval</option>
                {INTERVALS.map((iv) => (
                  <option key={iv} value={iv}>{iv}</option>
                ))}
              </select>
              <select
                value={overrideStyle}
                onChange={(e) => setOverrideStyle(e.target.value)}
                className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm"
              >
                <option value="*">Any style</option>
                {TRADING_STYLES.map((st) => (
                  <option key={st} value={st}>{st}</option>
                ))}
              </select>
            </div>
            <textarea
              value={overridePatchJson}
              onChange={(e) => setOverridePatchJson(e.target.value)}
              rows={10}
              spellCheck={false}
              className="mb-3 w-full rounded border border-[#30363d] bg-[#0d1117] p-2 font-mono text-xs"
            />
            <button type="button" onClick={handleOverrideSave} className="rounded bg-[#238636] px-3 py-1.5 text-sm text-white">
              Save override
            </button>
          </section>
        </div>
      )}

      {tab === "versions" && (
        <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
          <h2 className="mb-3 text-sm font-semibold text-white">Version history</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[#8b949e]">
                <tr>
                  <th className="py-1 pr-3">ID</th>
                  <th className="py-1 pr-3">Tag</th>
                  <th className="py-1 pr-3">Created</th>
                  <th className="py-1 pr-3">Active</th>
                  <th className="py-1">Actions</th>
                </tr>
              </thead>
              <tbody className="text-[#c9d1d9]">
                {versions.map((v) => (
                  <tr key={v.id} className="border-t border-[#21262d]">
                    <td className="py-2 pr-3">{v.id}</td>
                    <td className="py-2 pr-3">{v.version_tag}</td>
                    <td className="py-2 pr-3 text-xs">{v.created_at ? new Date(v.created_at).toLocaleString() : "—"}</td>
                    <td className="py-2 pr-3">{v.is_active ? "✓" : "—"}</td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-2">
                        {!v.is_active && (
                          <button type="button" onClick={() => handleActivate(v.id)} className="rounded border border-[#30363d] px-2 py-0.5 text-xs">
                            Activate
                          </button>
                        )}
                        <button type="button" onClick={() => loadVersionConfig(v.id)} className="rounded border border-[#30363d] px-2 py-0.5 text-xs">
                          View
                        </button>
                        <button
                          type="button"
                          onClick={() => setCompareB(String(v.id))}
                          className="rounded border border-[#30363d] px-2 py-0.5 text-xs"
                        >
                          Set compare B
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {viewVersion && (
            <div className="mt-4 rounded border border-[#30363d] bg-[#0d1117] p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-white">
                  Version {viewVersion.version?.version_tag} (#{viewVersion.version?.id})
                </span>
                <button type="button" onClick={() => setViewVersion(null)} className="text-xs text-[#8b949e]">Close</button>
              </div>
              <pre className="max-h-64 overflow-auto text-xs">{JSON.stringify(viewVersion.config, null, 2)}</pre>
            </div>
          )}
        </section>
      )}

      {tab === "preview" && (
        <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
          <h2 className="mb-3 text-sm font-semibold text-white">Resolve preview</h2>
          <div className="mb-4 flex flex-wrap gap-2">
            <input
              value={resolvePair}
              onChange={(e) => setResolvePair(e.target.value.toUpperCase())}
              placeholder="Pair"
              className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm"
            />
            <select
              value={resolveInterval}
              onChange={(e) => setResolveInterval(e.target.value)}
              className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm"
            >
              {INTERVALS.map((iv) => (
                <option key={iv} value={iv}>{iv}</option>
              ))}
            </select>
            <select
              value={resolveStyle}
              onChange={(e) => setResolveStyle(e.target.value)}
              className="rounded border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm"
            >
              {TRADING_STYLES.map((st) => (
                <option key={st} value={st}>{st}</option>
              ))}
            </select>
            <button type="button" onClick={handleResolve} className="rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white">
              Resolve
            </button>
          </div>
          {resolved && (
            <>
              <div className="mb-4 grid gap-2 sm:grid-cols-3">
                {PREVIEW_SUMMARY_PATHS.map(([section, key, label]) => (
                  <MetricCard
                    key={`${section}.${key}`}
                    label={label}
                    value={formatMetric(getNestedValue(resolved.config, [section, key]))}
                  />
                ))}
              </div>
              <pre className="max-h-96 overflow-auto rounded bg-[#0d1117] p-3 text-xs">{JSON.stringify(resolved, null, 2)}</pre>
            </>
          )}
        </section>
      )}

      {tab === "backtest" && (
        <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
          <h2 className="mb-3 text-sm font-semibold text-white">Threshold backtest</h2>
          <p className="mb-3 text-xs text-[#8b949e]">
            Uses cached CSV for {resolvePair} · {resolveInterval}. NO_TRADE and WAIT are excluded from loss counts.
          </p>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <input value={compareA} onChange={(e) => setCompareA(e.target.value)} placeholder="Version A" className="w-24 rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" />
            <input value={compareB} onChange={(e) => setCompareB(e.target.value)} placeholder="Version B" className="w-24 rounded border border-[#30363d] bg-[#0d1117] px-2 py-1 text-sm" />
            <button type="button" onClick={() => handleBacktest(false)} className="rounded border border-[#30363d] px-3 py-1 text-sm">Run active</button>
            <button type="button" onClick={() => handleBacktest(true)} className="rounded bg-[#2f81f7] px-3 py-1.5 text-sm text-white">Compare A vs B</button>
          </div>
          {backtestResult && <BacktestResults data={backtestResult} />}
        </section>
      )}

      {tab === "advanced" && (
        <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
          <h2 className="mb-2 text-sm font-semibold text-white">Advanced JSON editor</h2>
          <p className="mb-3 text-xs text-[#8b949e]">
            Full nested config — validated server-side. Creates and activates a new version.
          </p>
          <textarea
            value={advancedJson}
            onChange={(e) => setAdvancedJson(e.target.value)}
            rows={18}
            spellCheck={false}
            className="mb-3 w-full rounded border border-[#30363d] bg-[#0d1117] p-3 font-mono text-xs"
          />
          <button type="button" onClick={saveAdvancedJson} className="rounded bg-[#238636] px-3 py-1.5 text-sm text-white">
            Save & activate full config
          </button>
        </section>
      )}
    </div>
  );
}

function OverviewPreview() {
  const [resolved, setResolved] = useState(null);

  useEffect(() => {
    api("/thresholds/resolve?pair=EURUSD&interval=60min&style=intraday")
      .then(setResolved)
      .catch(() => setResolved(null));
  }, []);

  if (!resolved?.config) {
    return <p className="text-sm text-[#8b949e]">Loading effective thresholds…</p>;
  }

  return (
    <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {PREVIEW_SUMMARY_PATHS.map(([section, key, label]) => (
        <MetricCard
          key={`${section}.${key}`}
          label={label}
          value={formatMetric(getNestedValue(resolved.config, [section, key]))}
        />
      ))}
    </div>
  );
}

function BacktestResults({ data }) {
  if (data.version_a && data.version_b) {
    const rowsA = formatBacktestMetrics(data.version_a.metrics);
    const rowsB = formatBacktestMetrics(data.version_b.metrics);
    return (
      <div className="grid gap-4 md:grid-cols-2">
        {[["A", data.version_a, rowsA], ["B", data.version_b, rowsB]].map(([label, ver, rows]) => (
          <div key={label} className="rounded border border-[#30363d] bg-[#0d1117] p-3">
            <h3 className="mb-2 text-sm font-medium text-white">
              Version {label}: {ver.tag} (#{ver.id})
            </h3>
            {rows ? (
              <dl className="space-y-1 text-sm">
                {rows.map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4">
                    <dt className="text-[#8b949e]">{k}</dt>
                    <dd className="text-[#c9d1d9]">{v}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-[#f85149]">{ver.metrics?.error || "Backtest failed"}</p>
            )}
          </div>
        ))}
        {data.delta && !data.delta.error && (
          <div className="md:col-span-2 rounded border border-[#30363d] bg-[#21262d] p-3 text-sm">
            <h3 className="mb-2 font-medium text-white">Delta (B − A)</h3>
            <pre className="text-xs">{JSON.stringify(data.delta, null, 2)}</pre>
          </div>
        )}
      </div>
    );
  }

  const rows = formatBacktestMetrics(data);
  if (!rows) return <p className="text-sm text-[#f85149]">{data.error || "Backtest failed"}</p>;
  return (
    <dl className="grid max-w-md gap-2 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4 rounded border border-[#30363d] bg-[#0d1117] px-3 py-2">
          <dt className="text-[#8b949e]">{k}</dt>
          <dd className="text-[#c9d1d9]">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
