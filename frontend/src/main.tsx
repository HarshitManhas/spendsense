import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileText,
  FolderOpen,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Plus,
  ReceiptText,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Wallet,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  AuthConfig,
  Health,
  uploadReceipt,
  exponents,
  Fields,
  money,
  Page,
  Receipt,
  setCsrf,
  Summary,
  User,
} from "./api";
import "./styles.css";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            nonce: string;
            callback: (result: { credential: string }) => void;
          }) => void;
          renderButton: (element: HTMLElement, config: object) => void;
        };
      };
    };
  }
}
const emptySummary: Summary = {
  currencies: [],
  categories: [],
  months: [],
  pending: 0,
};
const categoryNames: Record<string, string> = {
  uncategorized: "Uncategorized",
  food: "Food & drink",
  groceries: "Groceries",
  travel: "Travel & stays",
  shopping: "Shopping",
  transport: "Transport",
  health: "Health",
  utilities: "Utilities",
  other: "Other",
};

function Logo() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <ReceiptText size={22} />
      </span>
      <span>
        SpendSense<span className="brand-dot">.</span>
      </span>
    </div>
  );
}
function Spinner() {
  return <LoaderCircle className="spin" size={18} />;
}

function App() {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<AuthConfig>("/auth/config")
      .then(async (c) => {
        if (!active) return;
        setCsrf(c.csrfToken);
        setConfig(c);
        try {
          const me = await api<User>("/auth/me");
          if (active) setUser(me);
        } catch {
          /* A signed-out session is normal. */
        }
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    const expired = () => {
      setUser(null);
      setError("Your session expired. Please sign in again.");
    };
    window.addEventListener("session-expired", expired);
    return () => {
      active = false;
      window.removeEventListener("session-expired", expired);
    };
  }, []);
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      setUser(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (loading)
    return (
      <div className="boot">
        <Logo />
        <Spinner />
        <p>Making room for clarity…</p>
      </div>
    );
  if (user) return <Workspace key={user.id} user={user} logout={logout} />;
  return (
    <Login
      config={config}
      error={error}
      setError={setError}
      onLogin={setUser}
    />
  );
}

function Login({
  config,
  error,
  setError,
  onLogin,
}: {
  config: AuthConfig | null;
  error: string;
  setError: (s: string) => void;
  onLogin: (u: User) => void;
}) {
  const googleButton = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!config?.googleClientId) return;
    let active = true;
    const init = () => {
      if (!active || !googleButton.current) return;
      window.google?.accounts.id.initialize({
        client_id: config.googleClientId,
        nonce: config.csrfToken,
        callback: async (result) => {
          setBusy(true);
          setError("");
          try {
            onLogin(
              await api<User>("/auth/google", {
                method: "POST",
                body: JSON.stringify(result),
              }),
            );
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        },
      });
      window.google?.accounts.id.renderButton(googleButton.current, {
        theme: "outline",
        size: "large",
        width: 320,
        text: "continue_with",
      });
    };
    if (window.google) init();
    else {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.onload = init;
      script.onerror = () =>
        setError("Google sign-in could not load. Check your connection.");
      document.head.appendChild(script);
    }
    return () => {
      active = false;
    };
  }, [config]);
  async function localLogin(account: string) {
    setBusy(true);
    setError("");
    try {
      onLogin(
        await api<User>("/auth/development", {
          method: "POST",
          body: JSON.stringify({ account }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <section className="login-story">
        <Logo />
        <div className="story-copy">
          <span className="eyebrow light">
            LESS PAPERWORK. MORE PERSPECTIVE.
          </span>
          <h1>
            A little clarity.
            <br />
            For every
            <br />
            <em>expense.</em>
          </h1>
          <p>
            Turn a pile of receipts into a picture of your spending. You review
            the details. We keep everything organized.
          </p>
          <div className="story-tags">
            <span>
              <Check size={15} /> Your receipts
            </span>
            <span>
              <Check size={15} /> Your approval
            </span>
            <span>
              <Check size={15} /> Your data
            </span>
          </div>
        </div>
        <div className="story-footer">
          Built for the everyday, down to the last detail.
          <span>01 / SPENDSENSE</span>
        </div>
      </section>
      <section className="login-panel">
        <span className="top-note">
          <ShieldCheck size={16} /> A private space for your spending
        </span>
        <div className="login-box">
          <div className="icon-tile">
            <Wallet size={28} />
          </div>
          <span className="eyebrow">WELCOME TO SPENDSENSE</span>
          <h2>Goodbye, receipt pile.</h2>
          <p>
            Sign in to start collecting receipts and understanding where your
            money goes.
          </p>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {config?.googleClientId ? (
            <div ref={googleButton} className="google-button" />
          ) : config ? (
            <div className="setup-note">
              <ShieldCheck size={18} />
              <span>
                Google sign-in will be available once your Google client ID is
                connected.
              </span>
            </div>
          ) : null}
          {config?.devLogin && (
            <div className="local-login">
              <span className="eyebrow">LOCAL DEVELOPMENT</span>
              <p>Try the working app with an isolated local account.</p>
              <button
                className="primary full"
                disabled={busy}
                onClick={() => localLogin("alex")}
              >
                {busy ? (
                  <Spinner />
                ) : (
                  <>
                    Open Alex's workspace <ArrowRight size={17} />
                  </>
                )}
              </button>
              <button
                className="text-button full"
                disabled={busy}
                onClick={() => localLogin("sam")}
              >
                Open Sam's separate workspace
              </button>
              <small>
                Local test accounts. No Google identity is simulated.
              </small>
            </div>
          )}
          <div className="login-steps">
            <span>01 Upload</span>
            <ChevronRight size={13} />
            <span>02 Review</span>
            <ChevronRight size={13} />
            <span>03 Understand</span>
          </div>
        </div>
        <div className="login-bottom">
          Your data stays in your own workspace.<span>Spend thoughtfully.</span>
        </div>
      </section>
    </main>
  );
}

function Workspace({ user, logout }: { user: User; logout: () => void }) {
  const [page, setPage] = useState("overview");
  const [summary, setSummary] = useState<Summary>(emptySummary);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [expenses, setExpenses] = useState<Receipt[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [receiptCursor, setReceiptCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<Receipt | null>(null);
  const [currency, setCurrency] = useState("INR");
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    start: "",
    end: "",
    merchant: "",
    category: "",
    currency: "",
  });
  const picker = useRef<HTMLInputElement>(null);
  const query = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v),
  ).toString();
  const currentQuery = useRef(query);
  currentQuery.current = query;
  async function refresh() {
    const requestedQuery = query;
    const [s, r, e, h] = await Promise.all([
      api<Summary>("/analytics/summary"),
      api<Page>("/receipts"),
      api<Page>(`/expenses?${query}`),
      api<Health>("/health"),
    ]);
    setSummary(s);
    setReceipts(r.items);
    setReceiptCursor(r.nextCursor);
    setHealth(h);
    if (requestedQuery === currentQuery.current) {
      setExpenses(e.items);
      setCursor(e.nextCursor);
    }
  }
  useEffect(() => {
    let active = true;
    setLoading(true);
    refresh()
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [query]);
  useEffect(() => {
    if (!receipts.some((r) => ["queued", "processing"].includes(r.status)))
      return;
    const timer = window.setInterval(
      () => refresh().catch((e) => setError(e.message)),
      4000,
    );
    return () => window.clearInterval(timer);
  }, [receipts, query]);
  async function upload(files: FileList | File[] | null) {
    if (!files?.length || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    let count = 0;
    try {
      for (const file of Array.from(files)) {
        if (!health) throw new Error("Upload service is still loading. Please try again.");
        const result = await uploadReceipt(file, health.maxUploadMb);
        count += result.receipts.length;
      }
      setMessage(
        `${count} receipt${count === 1 ? "" : "s"} ready in your inbox.`,
      );
      setPage("receipts");
    } catch (e) {
      setError(
        `${count ? `${count} receipt(s) uploaded. ` : ""}${(e as Error).message}`,
      );
    } finally {
      await refresh().catch((e) => setError(e.message));
      setBusy(false);
      if (picker.current) picker.current.value = "";
    }
  }
  async function loadMore() {
    try {
      const result = await api<Page>(
        `/expenses?${query}&cursor=${encodeURIComponent(cursor || "")}`,
      );
      setExpenses((old) => [...old, ...result.items]);
      setCursor(result.nextCursor);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const total = summary.currencies.find((c) => c._id === currency);
  const chart = summary.months
    .filter((m) => m._id.currency === currency)
    .map((m) => ({
      month: m._id.month,
      amount: m.totalMinor / 10 ** exponents[currency],
    }));
  const categories = summary.categories
    .filter((c) => c._id.currency === currency)
    .sort((a, b) => b.totalMinor - a.totalMinor);
  const count = summary.currencies.reduce((a, c) => a + c.count, 0);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Logo />
        <span className="nav-label">YOUR WORKSPACE</span>
        <nav>
          {[
            ["overview", "Overview", LayoutDashboard],
            ["receipts", "Receipt inbox", ReceiptText],
            ["expenses", "All expenses", FolderOpen],
            ["analytics", "Analytics", BarChart3],
          ].map(([id, label, Icon]) => {
            const I = Icon as typeof LayoutDashboard;
            return (
              <button
                key={id as string}
                aria-label={label as string}
                aria-current={page === id ? "page" : undefined}
                className={page === id ? "nav-item active" : "nav-item"}
                onClick={() => setPage(id as string)}
              >
                <I size={19} />
                <span>{label as string}</span>
                {id === "receipts" && summary.pending > 0 && (
                  <b>{summary.pending}</b>
                )}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="side-tip">
            <span className="tiny-spark">
              <Sparkles size={18} />
            </span>
            <strong>A habit worth keeping.</strong>
            <p>
              A quick review today.
              <br />A clearer picture tomorrow.
            </p>
          </div>
          <button
            className={`nav-item ${page === "settings" ? "active" : ""}`}
            onClick={() => setPage("settings")}
          >
            <Settings2 size={18} />
            Settings
          </button>
          <div className="profile">
            <span className="avatar">{user.name[0]}</span>
            <div>
              <strong>{user.name}</strong>
              <small>
                {user.id.startsWith("dev:")
                  ? "Local workspace"
                  : "Personal workspace"}
              </small>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={logout}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>
              {
                {
                  overview: "Overview",
                  receipts: "Receipt inbox",
                  expenses: "All expenses",
                  analytics: "Analytics",
                  settings: "Settings",
                }[page]
              }
            </strong>
          </div>
          <div className="topbar-right">
            <span className="private-badge">
              <span /> Private workspace
            </span>
            <button
              className="icon-button"
              aria-label="About this workspace"
              onClick={() => setPage("settings")}
            >
              <CircleHelp size={19} />
            </button>
            <span className="avatar small">{user.name[0]}</span>
          </div>
        </header>
        <main className="content">
          <input
            hidden
            ref={picker}
            type="file"
            accept="image/jpeg,image/png,application/pdf"
            multiple
            onChange={(e) => upload(e.target.files)}
          />
          {error && (
            <div className="error dismissible" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {message && (
            <div className="success dismissible" role="status">
              <span>
                <Check size={16} />
                {message}
              </span>
              <button
                aria-label="Dismiss message"
                onClick={() => setMessage("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {page === "overview"
                  ? "YOUR MONEY, AT A GLANCE"
                  : "A PLACE FOR EVERY DETAIL"}
              </span>
              <h1>
                {
                  {
                    overview: `Hello, ${user.name.split(" ")[0]}.`,
                    receipts: "From paper to perspective.",
                    expenses: "Every expense, accounted for.",
                    analytics: "See the bigger picture.",
                    settings: "Your workspace. Your way.",
                  }[page]
                }
              </h1>
              <p>
                {
                  {
                    overview:
                      "A clear view of what you spend. A little less to think about.",
                    receipts:
                      "Upload, check the details, and give each receipt your approval.",
                    expenses:
                      "Your approved expenses, organized and easy to find.",
                    analytics:
                      "Understand your patterns, one approved receipt at a time.",
                    settings:
                      "Your account, connection, and extraction status.",
                  }[page]
                }
              </p>
            </div>
            {page !== "settings" && (
              <button
                className="primary"
                disabled={busy}
                onClick={() => picker.current?.click()}
              >
                {busy ? <Spinner /> : <Plus size={18} />}
                {busy ? "Uploading…" : "Add receipt"}
              </button>
            )}
          </div>
          {loading && (
            <div className="loading-strip">
              <Spinner /> Updating your workspace…
            </div>
          )}
          {(page === "overview" || page === "analytics") && (
            <>
              <div className="summary-toolbar">
                <span>
                  <span className="status-dot" /> Based on approved expenses
                </span>
                <div>
                  <span>All time</span>
                  <select
                    aria-label="Dashboard currency"
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                  >
                    {Object.keys(exponents).map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </div>
              </div>
              <section className="stats-grid">
                <div className="stat-card primary-stat">
                  <div className="stat-title">
                    Total spending <Wallet size={18} />
                  </div>
                  <strong>{money(total?.totalMinor || 0, currency)}</strong>
                  <span>
                    {total?.count || 0} approved {currency} expenses{" "}
                    <ArrowUpRight size={15} />
                  </span>
                </div>
                <div className="stat-card">
                  <div className="stat-title">
                    Expenses recorded <CheckCheck size={18} />
                  </div>
                  <strong>{count.toString().padStart(2, "0")}</strong>
                  <span>Across all your currencies</span>
                </div>
                <div className="stat-card">
                  <div className="stat-title">
                    Waiting for review <Clock3 size={18} />
                  </div>
                  <strong>{summary.pending.toString().padStart(2, "0")}</strong>
                  <button
                    className="text-link"
                    onClick={() => setPage("receipts")}
                  >
                    {summary.pending
                      ? "Let’s take a look"
                      : "You’re all caught up"}{" "}
                    <ArrowRight size={14} />
                  </button>
                </div>
              </section>
              {page === "overview" && (
                <section
                  className="upload-banner"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    upload(e.dataTransfer.files);
                  }}
                >
                  <div className="upload-icon">
                    <UploadCloud size={28} />
                  </div>
                  <div>
                    <h3>A receipt today. An insight tomorrow.</h3>
                    <p>Drop your receipts here, or upload an image or PDF.</p>
                    <small>JPG, PNG, PDF{health && ` · Up to ${health.maxUploadMb} MB · ${health.maxPdfPages} pages per PDF`}</small>
                  </div>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => picker.current?.click()}
                  >
                    {busy ? <Spinner /> : "Browse files"}{" "}
                    <ArrowRight size={15} />
                  </button>
                </section>
              )}
              <section className="charts-grid">
                <div className="panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Spending over time</h3>
                      <p>Your monthly rhythm in {currency}</p>
                    </div>
                    <span className="soft-badge">All time</span>
                  </div>
                  {chart.length ? (
                    <div className="chart">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chart}>
                          <defs>
                            <linearGradient
                              id="spendFill"
                              x1="0"
                              y1="0"
                              x2="0"
                              y2="1"
                            >
                              <stop
                                offset="0%"
                                stopColor="#3b725f"
                                stopOpacity={0.2}
                              />
                              <stop
                                offset="100%"
                                stopColor="#3b725f"
                                stopOpacity={0}
                              />
                            </linearGradient>
                          </defs>
                          <CartesianGrid vertical={false} stroke="#eceee8" />
                          <XAxis
                            dataKey="month"
                            tickLine={false}
                            axisLine={false}
                            tick={{ fontSize: 11 }}
                          />
                          <YAxis
                            tickLine={false}
                            axisLine={false}
                            tick={{ fontSize: 11 }}
                            width={48}
                          />
                          <Tooltip
                            formatter={(v) => [
                              new Intl.NumberFormat("en", {
                                style: "currency",
                                currency,
                              }).format(Number(v)),
                              "Spending",
                            ]}
                          />
                          <Area
                            type="monotone"
                            dataKey="amount"
                            stroke="#3b725f"
                            strokeWidth={2.5}
                            dot={{ r: 4, fill: "#3b725f", strokeWidth: 0 }}
                            fill="url(#spendFill)"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <Empty
                      icon={BarChart3}
                      title="Your story starts with a receipt"
                      text="Approve an expense to see your spending take shape."
                      compact
                    />
                  )}
                </div>
                <div className="panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Where it goes</h3>
                      <p>Spending by category</p>
                    </div>
                    <span className="currency-tag">{currency}</span>
                  </div>
                  {categories.length ? (
                    <div className="category-list">
                      {categories.map((c, i) => (
                        <div key={c._id.category}>
                          <div className="category-row">
                            <span>
                              <i
                                style={{
                                  background: [
                                    "#345c4d",
                                    "#9cae80",
                                    "#cca56b",
                                    "#9eaca9",
                                  ][i % 4],
                                }}
                              />
                              {categoryNames[c._id.category]}
                            </span>
                            <strong>{money(c.totalMinor, currency)}</strong>
                          </div>
                          <div className="category-track">
                            <div
                              style={{
                                width: `${total?.totalMinor ? (c.totalMinor / total.totalMinor) * 100 : 0}%`,
                              }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <Empty
                      icon={Wallet}
                      title="Room for a little insight"
                      text="Your categories will appear here after approval."
                      compact
                    />
                  )}
                </div>
              </section>
              {page === "overview" && (
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Recent expenses</h3>
                      <p>The little things, all in one place.</p>
                    </div>
                    <button
                      className="text-link"
                      onClick={() => setPage("expenses")}
                    >
                      View all expenses <ArrowRight size={15} />
                    </button>
                  </div>
                  <ExpenseTable
                    rows={expenses.slice(0, 5)}
                    onSelect={setSelected}
                  />
                </section>
              )}
            </>
          )}
          {page === "receipts" && (
            <>
              <div className="inbox-note">
                <ShieldCheck size={18} />
                <span>
                  {health?.extraction === "manual_only"
                    ? "Manual review is ready. Automatic extraction is currently unavailable."
                    : "AI predictions always need your review. Nothing is counted until you approve it."}
                </span>
              </div>
              {receipts.length ? (
                <div className="receipt-grid">
                  {receipts.map((r) => (
                    <button
                      className="receipt-card"
                      key={r.id}
                      disabled={["queued", "processing"].includes(r.status)}
                      onClick={() => setSelected(r)}
                    >
                      <div className="receipt-thumb">
                        <img
                          src={`/api/receipts/${r.id}/preview`}
                          alt={`Receipt preview: ${r.filename}`}
                        />
                      </div>
                      <div className="receipt-card-body">
                        <span className="soft-badge">
                          {r.status.replace("_", " ")}
                        </span>
                        <h3>{r.fields.merchant || r.filename}</h3>
                        <p>
                          Page {r.page} ·{" "}
                          {r.source === "manual"
                            ? "Manual entry"
                            : r.source === "pdf_text" ? "PDF text" : r.source === "paddleocr" ? "Local OCR" : "AI extraction"}
                        </p>
                        <span className="text-link">
                          Review receipt <ArrowRight size={15} />
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="panel inbox-empty">
                  <Empty
                    icon={ReceiptText}
                    title={count ? "You're all caught up" : "A fresh start for your receipts"}
                    text={count ? "Every receipt has been reviewed. Add another whenever you're ready." : "Upload your first receipt. Review it at your own pace."}
                  />
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => picker.current?.click()}
                  >
                    <Plus size={17} /> {count ? "Add another receipt" : "Add your first receipt"}
                  </button>
                </div>
              )}
              {receiptCursor && (
                <button
                  className="secondary load-more"
                  onClick={async () => {
                    try {
                      const next = await api<Page>(
                        `/receipts?before=${receiptCursor}`,
                      );
                      setReceipts((old) => [...old, ...next.items]);
                      setReceiptCursor(next.nextCursor);
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Load more receipts
                </button>
              )}
            </>
          )}
          {page === "expenses" && (
            <section className="panel">
              <div className="filter-bar">
                <label className="search-field">
                  <Search size={16} />
                  <input
                    placeholder="Exact merchant name"
                    value={filters.merchant}
                    onChange={(e) =>
                      setFilters({ ...filters, merchant: e.target.value })
                    }
                  />
                </label>
                <input
                  aria-label="From date"
                  type="date"
                  value={filters.start}
                  onChange={(e) =>
                    setFilters({ ...filters, start: e.target.value })
                  }
                />
                <input
                  aria-label="To date"
                  type="date"
                  value={filters.end}
                  onChange={(e) =>
                    setFilters({ ...filters, end: e.target.value })
                  }
                />
                <select
                  aria-label="Category"
                  value={filters.category}
                  onChange={(e) =>
                    setFilters({ ...filters, category: e.target.value })
                  }
                >
                  <option value="">All categories</option>
                  {Object.entries(categoryNames).map(([v, name]) => (
                    <option key={v} value={v}>
                      {name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Expense currency"
                  value={filters.currency}
                  onChange={(e) =>
                    setFilters({ ...filters, currency: e.target.value })
                  }
                >
                  <option value="">All currencies</option>
                  {Object.keys(exponents).map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
                <a
                  className="secondary"
                  href={`/api/expenses/export.csv?${query}`}
                >
                  <ArrowDownToLine size={16} /> Export
                </a>
              </div>
              <ExpenseTable rows={expenses} onSelect={setSelected} />
              {cursor && (
                <button className="secondary load-more" onClick={loadMore}>
                  Load more
                </button>
              )}
            </section>
          )}
          {page === "settings" && (
            <div className="settings-grid">
              <section className="panel settings-panel">
                <div className="icon-tile">
                  <ShieldCheck size={24} />
                </div>
                <h3>Personal workspace</h3>
                <p>
                  {user.name}
                  <br />
                  {user.email}
                </p>
                <div className="setting-row">
                  <span>Database</span>
                  <strong>MongoDB + GridFS</strong>
                </div>
                <div className="setting-row">
                  <span>Data access</span>
                  <strong>Only your account</strong>
                </div>
                <div className="setting-row">
                  <span>Authentication</span>
                  <strong>
                    {user.id.startsWith("dev:")
                      ? "Local development account"
                      : "Google"}
                  </strong>
                </div>
                <button className="secondary" onClick={logout}>
                  <LogOut size={16} /> Sign out
                </button>
              </section>
              <section className="panel settings-panel">
                <div className="icon-tile">
                  <Sparkles size={24} />
                </div>
                <h3>Thoughtful automation</h3>
                <p>
                  {health?.extraction === "manual_only"
                    ? "Receipt upload, review, approval, and analytics are available. Automatic extraction is currently unavailable."
                    : health?.extraction === "paddleocr_available"
                      ? "Local OCR suggests merchant, date, totals, and item rows. Check every value and choose a category before approval."
                      : "An experimental CNN + Transformer model is installed. Check the extracted details before approval."}
                </p>
                <div className="setting-row">
                  <span>Human review</span>
                  <strong>Always required</strong>
                </div>
                <div className="setting-row">
                  <span>Training on your data</span>
                  <strong>Off</strong>
                </div>
                <small>
                  Uploaded receipts are not automatically used to train the
                  model.
                </small>
                <p>Download your approved merchant, item names, dates, and categories to prepare your own category training data. Uncategorized expenses are excluded.</p>
                <a className="secondary" href="/api/expenses/category-labels.jsonl">
                  <ArrowDownToLine size={16} /> Download category examples
                </a>
              </section>
            </div>
          )}
          <footer className="workspace-footer">
            <span>
              <ShieldCheck size={14} /> Your receipts. Your approval. Your data.
            </span>
            <span>Made for a clearer everyday.</span>
          </footer>
        </main>
      </div>
      {selected && (
        <Review
          receipt={selected}
          close={() => setSelected(null)}
          changed={async (text) => {
            setMessage(text);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function Empty({
  icon: Icon,
  title,
  text,
  compact = false,
}: {
  icon: typeof Wallet;
  title: string;
  text: string;
  compact?: boolean;
}) {
  return (
    <div className={`empty ${compact ? "compact" : ""}`}>
      <span className="empty-icon">
        <Icon size={26} strokeWidth={1.4} />
      </span>
      <h4>{title}</h4>
      <p>{text}</p>
    </div>
  );
}
function ExpenseTable({
  rows,
  onSelect,
}: {
  rows: Receipt[];
  onSelect: (r: Receipt) => void;
}) {
  if (!rows.length)
    return (
      <Empty
        icon={FileText}
        title="Nothing to tally up just yet"
        text="Approved expenses will appear here. Your first receipt is a good place to start."
      />
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Merchant</th>
            <th>Date</th>
            <th>Category</th>
            <th>Status</th>
            <th className="amount-cell">Amount</th>
            <th>
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <button className="merchant-button" onClick={() => onSelect(r)}>
                  <span className="merchant-icon">
                    {r.expense?.merchant[0]}
                  </span>
                  <span>
                    {r.expense?.merchant}
                    <small>Receipt #{r.id.slice(0, 6)}</small>
                  </span>
                </button>
              </td>
              <td>{r.expense?.expenseDate}</td>
              <td>{categoryNames[r.expense?.category || "uncategorized"]}</td>
              <td>
                <span className="approved-badge">
                  <Check size={12} /> Approved
                </span>
              </td>
              <td className="amount-cell">
                {r.expense && money(r.expense.totalMinor, r.expense.currency)}
              </td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`Open ${r.expense?.merchant}`}
                  onClick={() => onSelect(r)}
                >
                  <ArrowUpRight size={17} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Review({
  receipt,
  close,
  changed,
}: {
  receipt: Receipt;
  close: () => void;
  changed: (message: string) => Promise<void>;
}) {
  const [record, setRecord] = useState(receipt);
  const [fields, setFields] = useState<Fields>({ ...receipt.fields });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmWarnings, setConfirmWarnings] = useState(false);
  useEffect(() => setConfirmWarnings(false), [fields]);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  const approved = record.status === "approved";
  const taxWarning =
    fields.tax && fields.total && Number(fields.tax) > Number(fields.total);
  const itemWarning = (fields.items || []).some((item) => {
    if (!item.quantity || !item.unit_price || !item.line_total || !fields.currency) return false;
    const factor = 10 ** (exponents[fields.currency] ?? 2);
    return Math.abs(Math.round(Number(item.quantity) * Math.round(Number(item.unit_price) * factor)) - Math.round(Number(item.line_total) * factor)) > 1;
  });
  async function action(kind: string) {
    setBusy(true);
    setError("");
    try {
      const route =
        kind === "edit"
          ? `/expenses/${record.id}`
          : `/receipts/${record.id}${kind === "delete" ? "" : `/${kind}`}`;
      const result = await api<Receipt>(route, {
        method:
          kind === "delete"
            ? "DELETE"
            : ["review", "edit"].includes(kind)
              ? "PATCH"
              : "POST",
        body: JSON.stringify(
          ["reject", "delete", "extract"].includes(kind)
            ? { revision: record.revision }
            : {
                revision: record.revision,
                fields,
                confirm_warnings: confirmWarnings,
              },
        ),
      });
      setRecord(result);
      await changed(
        {
          approve: "Expense approved. Your dashboard is up to date.",
          review: "Review saved. Approve when you’re ready.",
          edit: "Expense updated.",
          reject: "Receipt rejected.",
          delete: "Expense and receipt removed.",
          extract: "Reading the receipt again. Review it when extraction finishes.",
        }[kind] || "Saved.",
      );
      if (kind !== "review") close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      className="review-dialog"
      ref={dialog}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) close();
      }}
    >
      <div className="review-header">
        <div>
          <span className="eyebrow">
            {approved ? "APPROVED EXPENSE" : "A QUICK SECOND LOOK"}
          </span>
          <h2>{approved ? "Expense details" : "Review your receipt"}</h2>
        </div>
        <button
          className="icon-button"
          disabled={busy}
          aria-label="Close review"
          onClick={close}
        >
          <X size={22} />
        </button>
      </div>
      <div className="review-body">
        <div className="preview-pane">
          <span>
            {record.filename} · Page {record.page}
          </span>
          <a
            href={`/api/receipts/${record.id}/preview`}
            target="_blank"
            rel="noreferrer"
            title="Open full-size receipt"
          >
            <img
              src={`/api/receipts/${record.id}/preview`}
              alt="Full receipt for review"
            />
          </a>
          <small>Click the receipt to open it at full size.</small>
        </div>
        <form
          className="review-form"
          onSubmit={(e) => {
            e.preventDefault();
            action(approved ? "edit" : "approve");
          }}
        >
          {!approved && (
            <div className="review-notice">
              <ShieldCheck size={18} />
              <p>
                {record.source === "manual"
                  ? "Enter the values from your receipt. Nothing is added to your spending until you approve."
                  : "Check each prediction against the receipt and correct anything that needs attention."}
              </p>
            </div>
          )}
          {record.warnings?.map((w) => (
            <p className="warning" key={w}>
              {w}
            </p>
          ))}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <label>
            Merchant
            <input
              required
              maxLength={200}
              value={fields.merchant || ""}
              placeholder="Name on the receipt"
              onChange={(e) =>
                setFields({ ...fields, merchant: e.target.value })
              }
            />
          </label>
          <label>
            Receipt date
            <input
              required
              type="date"
              value={fields.date || ""}
              onChange={(e) => setFields({ ...fields, date: e.target.value })}
            />
          </label>
          <div className="form-row">
            <label>
              Total
              <input
                required
                inputMode="decimal"
                value={fields.total || ""}
                placeholder="0.00"
                onChange={(e) =>
                  setFields({ ...fields, total: e.target.value })
                }
              />
            </label>
            <label>
              Currency
              <select
                required
                value={fields.currency || ""}
                onChange={(e) =>
                  setFields({ ...fields, currency: e.target.value })
                }
              >
                <option value="">Choose</option>
                {Object.keys(exponents).map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="form-row">
            <label>
              Tax <span>optional</span>
              <input
                inputMode="decimal"
                value={fields.tax || ""}
                placeholder="Unknown"
                onChange={(e) =>
                  setFields({ ...fields, tax: e.target.value || null })
                }
              />
            </label>
            <label>
              Category
              <select
                value={fields.category}
                onChange={(e) =>
                  setFields({ ...fields, category: e.target.value })
                }
              >
                {Object.entries(categoryNames).map(([v, name]) => (
                  <option key={v} value={v}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <section className="receipt-items" aria-label="Receipt items">
            <div className="item-heading">
              <h3>Items & prices</h3>
              <button type="button" className="secondary" disabled={busy || (fields.items?.length || 0) >= 200}
                onClick={() => setFields({ ...fields, items: [...(fields.items || []), { name: "", quantity: null, unit_price: null, line_total: null }] })}>
                <Plus size={15} /> Add item
              </button>
            </div>
            <p className="item-help">Leave quantities or prices blank when they are not shown. Item totals may exclude tax, fees, or discounts.</p>
            {(fields.items || []).map((item, index) => (
              <div className="receipt-item" key={index}>
                <label>Item {index + 1}
                  <input maxLength={300} value={item.name} placeholder="Name on the receipt"
                    onChange={(e) => setFields({ ...fields, items: (fields.items || []).map((value, i) => i === index ? { ...value, name: e.target.value } : value) })} />
                </label>
                <div className="item-prices">
                  {([['quantity', 'Quantity'], ['unit_price', 'Unit price'], ['line_total', 'Line total']] as const).map(([key, title]) => (
                    <label key={key}>{title}<input inputMode="decimal" maxLength={32} value={item[key] || ''} placeholder="Unknown"
                      onChange={(e) => setFields({ ...fields, items: (fields.items || []).map((value, i) => i === index ? { ...value, [key]: e.target.value || null } : value) })} /></label>
                  ))}
                </div>
                <button type="button" className="secondary" disabled={busy} aria-label={`Remove item ${index + 1}`}
                  onClick={() => setFields({ ...fields, items: (fields.items || []).filter((_, i) => i !== index) })}>Remove</button>
              </div>
            ))}
          </section>
          <label>
            Notes <span>optional</span>
            <textarea
              maxLength={1000}
              value={fields.notes}
              placeholder="Anything you’d like to remember"
              onChange={(e) => setFields({ ...fields, notes: e.target.value })}
            />
          </label>
          {record.prediction && (
            <details>
              <summary>Original AI prediction</summary>
              <pre>{JSON.stringify(record.prediction, null, 2)}</pre>
            </details>
          )}
          {(taxWarning || itemWarning) && (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={confirmWarnings}
                onChange={(e) => setConfirmWarnings(e.target.checked)}
              />
              I checked the tax and item-price differences against the receipt and confirm the adjustments.
            </label>
          )}
          <div className="review-actions">
            <button className="primary" disabled={busy} type="submit">
              {busy ? <Spinner /> : <Check size={17} />}
              {approved ? "Save changes" : "Approve expense"}
            </button>
            {!approved && (
              <button
                className="secondary"
                disabled={busy}
                type="button"
                onClick={() => action("review")}
              >
                Save draft
              </button>
            )}
            {!approved && (
              <button className="secondary" type="button" disabled={busy}
                onClick={() => {
                  if (window.confirm("Read this receipt again? This replaces the current draft values with new extraction results.")) action("extract");
                }}>Re-extract</button>
            )}
          </div>
          <button
            className="text-button danger"
            disabled={busy}
            type="button"
            onClick={() => {
              if (
                window.confirm(
                  approved
                    ? "Delete this expense and its receipt? This cannot be undone."
                    : "Reject this receipt? It will not count toward your expenses.",
                )
              )
                action(approved ? "delete" : "reject");
            }}
          >
            {approved ? "Delete expense" : "Reject receipt"}
          </button>
        </form>
      </div>
    </dialog>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
