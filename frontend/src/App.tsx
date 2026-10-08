import { FormEvent, useEffect, useMemo, useState } from "react";

type Numeric = number | string | null | undefined;
type StringMap = Record<string, string>;

interface Overview {
  total_customers: number;
  total_orders: number;
  total_activities: number;
  gross_order_value: Numeric;
  total_revenue: Numeric;
  average_order_value: Numeric;
  delivered_orders: number;
  cancelled_orders: number;
  pending_orders: number;
}

interface CategoryMetric {
  order_count: number;
  gross_order_value: Numeric;
  realized_revenue: Numeric;
  average_order_value: Numeric;
}

interface CustomerRank {
  customer_id: string;
  name: string;
  city: string;
  order_count: number;
  total_spending: Numeric;
  activity_count: number;
}

interface ActivityStats {
  by_type: Record<string, number>;
  by_device: Record<string, number>;
  top_products_by_activity: Array<{ product: string; activity_count: number }>;
}

interface CustomerDirectoryItem {
  customer_id: string;
  name: string;
  city: string;
  category: string;
  order_count: number;
  total_spending: Numeric;
  activity_count: number;
}

interface CustomerDirectoryResponse {
  items: CustomerDirectoryItem[];
  total: number;
  limit: number;
  offset: number;
  available_cities: string[];
  available_categories: string[];
}

interface Order {
  order_id: string;
  product: string;
  category: string;
  amount: Numeric;
  date: string;
  status: string;
}

interface Activity {
  timestamp: string;
  activity_id: string;
  type: string;
  device: string;
  product: string;
}

interface Customer360 {
  customer_id: string;
  profile: StringMap;
  preferences: StringMap;
  order_summary: {
    order_count: number;
    total_spending: Numeric;
    average_order_value: Numeric;
    delivered_order_count: number;
    cancelled_order_count: number;
    pending_order_count: number;
  };
  order_history: Order[];
  activity_summary: { total_activities: number; by_type: Record<string, number> };
  activity_history: Activity[];
}

interface ErrorPayload {
  detail?: string;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

function isErrorPayload(value: unknown): value is ErrorPayload {
  return typeof value === "object" && value !== null && "detail" in value;
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  const payload: unknown = await response.json();
  if (!response.ok) {
    const detail = isErrorPayload(payload) && typeof payload.detail === "string" ? payload.detail : "Request failed";
    throw new Error(detail);
  }
  return payload as T;
}

function numberValue(value: Numeric): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoney(value: Numeric): string {
  return numberValue(value).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  });
}

function formatNumber(value: Numeric): string {
  return numberValue(value).toLocaleString("en-IN");
}

function labelize(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function MetricCard({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <article className="metric-card reveal">
      <p className="eyebrow">{label}</p>
      <p className="metric-value">{value}</p>
      <p className="metric-note">{note}</p>
    </article>
  );
}

function SectionHeading({ index, title, detail }: { index: string; title: string; detail: string }) {
  return (
    <div className="section-heading">
      <span className="section-index">{index}</span>
      <div>
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function BarRows({ values, money = false }: { values: Array<{ label: string; value: number }>; money?: boolean }) {
  const largest = Math.max(...values.map((item) => item.value), 1);
  return (
    <div className="bar-list">
      {values.map((item) => (
        <div className="bar-row" key={item.label}>
          <div className="bar-label">
            <span>{item.label}</span>
            <strong>{money ? formatMoney(item.value) : formatNumber(item.value)}</strong>
          </div>
          <div className="bar-track" aria-hidden="true">
            <span style={{ width: `${Math.max((item.value / largest) * 100, 2)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

interface CustomerDirectoryProps {
  onViewCustomer: (customerId: string) => void;
}

function CustomerDirectory({ onViewCustomer }: CustomerDirectoryProps) {
  const emptyFilters = { search: "", city: "", category: "", min_orders: "" };
  const [filters, setFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);
  const [directory, setDirectory] = useState<CustomerDirectoryResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams({
      limit: "50",
      offset: String(offset),
    });
    if (appliedFilters.search.trim()) params.set("search", appliedFilters.search.trim());
    if (appliedFilters.city) params.set("city", appliedFilters.city);
    if (appliedFilters.category) params.set("category", appliedFilters.category);
    if (appliedFilters.min_orders) params.set("min_orders", appliedFilters.min_orders);

    setLoading(true);
    setError("");
    void apiGet<CustomerDirectoryResponse>(`/api/customers?${params.toString()}`)
      .then(setDirectory)
      .catch((requestError: unknown) => {
        setError(requestError instanceof Error ? requestError.message : "Could not load customers.");
      })
      .finally(() => setLoading(false));
  }, [appliedFilters, offset]);

  const submitFilters = (event: FormEvent) => {
    event.preventDefault();
    setOffset(0);
    setAppliedFilters({ ...filters });
  };

  const clearFilters = () => {
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    setOffset(0);
  };

  const total = directory?.total ?? 0;
  const limit = directory?.limit ?? 50;
  const firstRow = total === 0 ? 0 : offset + 1;
  const lastRow = Math.min(offset + limit, total);

  return (
    <>
      <section className="directory-hero reveal">
        <div>
          <div className="hero-kicker">Customer directory / HBase scan / 06</div>
          <h1>Find the customer<br /><span>behind the row key.</span></h1>
          <p className="hero-copy">Search and filter customer summaries without leaving HBase. Each row combines profile, order, spending, and activity data.</p>
        </div>
        <div className="directory-count"><strong>{formatNumber(total)}</strong><span>matching customers</span></div>
      </section>

      <section className="directory-section reveal">
        <form className="directory-filters" onSubmit={submitFilters}>
          <div className="filter-field filter-search"><label htmlFor="directory-search">Search</label><input id="directory-search" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} placeholder="Name or customer ID" /></div>
          <div className="filter-field"><label htmlFor="directory-city">City</label><select id="directory-city" value={filters.city} onChange={(event) => setFilters({ ...filters, city: event.target.value })}><option value="">All cities</option>{directory?.available_cities.map((city) => <option key={city} value={city}>{city}</option>)}</select></div>
          <div className="filter-field"><label htmlFor="directory-category">Category</label><select id="directory-category" value={filters.category} onChange={(event) => setFilters({ ...filters, category: event.target.value })}><option value="">All categories</option>{directory?.available_categories.map((category) => <option key={category} value={category}>{category}</option>)}</select></div>
          <div className="filter-field filter-orders"><label htmlFor="directory-orders">Minimum orders</label><input id="directory-orders" type="number" min="0" max="1000" value={filters.min_orders} onChange={(event) => setFilters({ ...filters, min_orders: event.target.value })} placeholder="0" /></div>
          <div className="filter-actions"><button type="submit">Apply filters</button><button type="button" className="secondary-button" onClick={clearFilters}>Reset</button></div>
        </form>

        {error && <div className="error-banner" role="alert"><strong>Customer list unavailable.</strong> {error}</div>}
        <div className="directory-toolbar"><span>{loading ? "Reading customer rows…" : `Showing ${firstRow.toLocaleString("en-IN")}–${lastRow.toLocaleString("en-IN")} of ${total.toLocaleString("en-IN")}`}</span><span className="mono-label">PROFILE + ORDERS + ACTIVITY</span></div>
        <div className="panel table-panel directory-table-panel">
          <div className="table-scroll">
            <table>
              <thead><tr><th>Customer</th><th>City</th><th>Preference</th><th>Orders</th><th>Activity</th><th className="align-right">Spending</th><th aria-label="Actions" /></tr></thead>
              <tbody>
                {directory?.items.map((item) => (
                  <tr key={item.customer_id}>
                    <td><strong>{item.name}</strong><span className="sub-cell">{item.customer_id}</span></td>
                    <td>{item.city}</td>
                    <td><span className="category-tag">{item.category}</span></td>
                    <td>{formatNumber(item.order_count)}</td>
                    <td>{formatNumber(item.activity_count)}</td>
                    <td className="align-right amount-cell">{formatMoney(item.total_spending)}</td>
                    <td className="action-cell"><button type="button" className="table-action" onClick={() => onViewCustomer(item.customer_id)}>View 360</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && directory?.items.length === 0 && <div className="empty-state"><strong>No customers match these filters.</strong><span>Try a different city, category, or minimum order count.</span></div>}
          </div>
        </div>
        <div className="pagination"><button type="button" className="secondary-button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</button><span>Page {total === 0 ? 0 : Math.floor(offset / limit) + 1} of {Math.max(1, Math.ceil(total / limit))}</span><button type="button" className="secondary-button" disabled={offset + limit >= total || loading} onClick={() => setOffset(offset + limit)}>Next</button></div>
      </section>
    </>
  );
}

type AppPage = "overview" | "customers";

function App() {
  const [page, setPage] = useState<AppPage>(() => (window.location.hash === "#customers" ? "customers" : "overview"));
  const [overview, setOverview] = useState<Overview | null>(null);
  const [categories, setCategories] = useState<Record<string, CategoryMetric>>({});
  const [topCustomers, setTopCustomers] = useState<CustomerRank[]>([]);
  const [activity, setActivity] = useState<ActivityStats | null>(null);
  const [customer, setCustomer] = useState<Customer360 | null>(null);
  const [customerId, setCustomerId] = useState("CUST000001");
  const [loading, setLoading] = useState(true);
  const [customerLoading, setCustomerLoading] = useState(false);
  const [error, setError] = useState("");
  const [customerError, setCustomerError] = useState("");

  const loadDashboard = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextOverview, nextCategories, nextCustomers, nextActivity] = await Promise.all([
        apiGet<Overview>("/api/analytics/overview"),
        apiGet<{ categories: Record<string, CategoryMetric> }>("/api/analytics/categories"),
        apiGet<{ customers: CustomerRank[] }>("/api/analytics/top-customers"),
        apiGet<ActivityStats>("/api/analytics/activity"),
      ]);
      setOverview(nextOverview);
      setCategories(nextCategories.categories);
      setTopCustomers(nextCustomers.customers);
      setActivity(nextActivity);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load the dashboard.");
    } finally {
      setLoading(false);
    }
  };

  const loadCustomer = async (event?: FormEvent, requestedId?: string) => {
    event?.preventDefault();
    const selectedCustomerId = (requestedId ?? customerId).trim();
    setCustomerLoading(true);
    setCustomerError("");
    try {
      const nextCustomer = await apiGet<Customer360>(`/api/customers/${encodeURIComponent(selectedCustomerId)}/360`);
      setCustomerId(selectedCustomerId);
      setCustomer(nextCustomer);
    } catch (requestError) {
      setCustomer(null);
      setCustomerError(requestError instanceof Error ? requestError.message : "Could not load this customer.");
    } finally {
      setCustomerLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
    void loadCustomer();
  }, []);

  useEffect(() => {
    const syncPage = () => setPage(window.location.hash === "#customers" ? "customers" : "overview");
    window.addEventListener("hashchange", syncPage);
    return () => window.removeEventListener("hashchange", syncPage);
  }, []);

  const navigateTo = (nextPage: AppPage) => {
    window.location.hash = nextPage === "customers" ? "customers" : "top";
    setPage(nextPage);
  };

  const viewCustomer = (requestedId: string) => {
    navigateTo("overview");
    void loadCustomer(undefined, requestedId);
  };

  const categoryRows = useMemo(
    () => Object.entries(categories).map(([label, metric]) => ({ label, value: metric.order_count })),
    [categories],
  );
  const revenueRows = useMemo(
    () => Object.entries(categories).map(([label, metric]) => ({ label, value: numberValue(metric.realized_revenue) })),
    [categories],
  );
  const activityRows = useMemo(
    () => Object.entries(activity?.by_type ?? {}).map(([label, value]) => ({ label: labelize(label), value })),
    [activity],
  );

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" onClick={() => navigateTo("overview")} aria-label="HBase Customer 360 home">
          <span className="brand-mark">H</span>
          <span>Customer 360 <em>/ HBase</em></span>
        </a>
        <nav className="primary-nav" aria-label="Primary navigation">
          <button type="button" className={page === "overview" ? "nav-link active" : "nav-link"} onClick={() => navigateTo("overview")}>Overview</button>
          <button type="button" className={page === "customers" ? "nav-link active" : "nav-link"} onClick={() => navigateTo("customers")}>Customers</button>
        </nav>
        <div className="topbar-meta">
          <span className="live-dot" />
          <span>Live database</span>
          <span className="mono-label">THRIFT : 9090</span>
        </div>
      </header>

      <main id="top" className="page-wrap">
        {page === "customers" ? <CustomerDirectory onViewCustomer={viewCustomer} /> : (
          <>
        <section className="hero reveal">
          <div className="hero-kicker">Apache HBase / Read model / 01</div>
          <h1>Customer data,<br /><span>read at a glance.</span></h1>
          <p className="hero-copy">A live view of profiles, order behavior, and activity history served directly from the project’s HBase tables.</p>
          <div className="hero-rule" />
          <div className="hero-footnote">
            <span>Source of truth</span>
            <strong>customers · customer_orders · customer_activity</strong>
          </div>
        </section>

        {error && (
          <div className="error-banner" role="alert">
            <strong>Dashboard unavailable.</strong> {error}
            <button type="button" onClick={() => void loadDashboard()}>Retry</button>
          </div>
        )}

        <section className="metrics-grid" aria-label="Overview metrics">
          <MetricCard label="Customers" value={loading ? "—" : formatNumber(overview?.total_customers)} note="Profile rows" />
          <MetricCard label="Orders" value={loading ? "—" : formatNumber(overview?.total_orders)} note={`${formatNumber(overview?.delivered_orders)} delivered`} />
          <MetricCard label="Realized revenue" value={loading ? "—" : formatMoney(overview?.total_revenue)} note="Delivered orders only" />
          <MetricCard label="Activities" value={loading ? "—" : formatNumber(overview?.total_activities)} note="Recorded events" />
          <MetricCard label="Average order" value={loading ? "—" : formatMoney(overview?.average_order_value)} note="All valid amounts" />
        </section>

        <section className="content-section reveal">
          <SectionHeading index="02" title="Category pulse" detail="Order volume and realized revenue, grouped at the HBase analytics layer." />
          <div className="two-column-grid">
            <article className="panel">
              <div className="panel-title"><span>Orders by category</span><span className="panel-meta">COUNT</span></div>
              <BarRows values={categoryRows} />
            </article>
            <article className="panel">
              <div className="panel-title"><span>Revenue by category</span><span className="panel-meta">INR / DELIVERED</span></div>
              <BarRows values={revenueRows} money />
            </article>
          </div>
        </section>

        <section className="content-section reveal">
          <SectionHeading index="03" title="Customer ranking" detail="The ten highest-spending customers, calculated from delivered orders." />
          <div className="panel table-panel">
            <div className="table-scroll">
              <table>
                <thead><tr><th>Rank</th><th>Customer</th><th>City</th><th>Orders</th><th className="align-right">Spending</th></tr></thead>
                <tbody>
                  {topCustomers.map((item, index) => (
                    <tr key={item.customer_id}>
                      <td className="rank-cell">{String(index + 1).padStart(2, "0")}</td>
                      <td><strong>{item.name}</strong><span className="sub-cell">{item.customer_id}</span></td>
                      <td>{item.city}</td>
                      <td>{formatNumber(item.order_count)}</td>
                      <td className="align-right amount-cell">{formatMoney(item.total_spending)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="content-section reveal">
          <SectionHeading index="04" title="Activity signal" detail="Event type and device distribution from the activity table." />
          <div className="two-column-grid activity-grid">
            <article className="panel">
              <div className="panel-title"><span>Activity by type</span><span className="panel-meta">EVENTS</span></div>
              <BarRows values={activityRows} />
            </article>
            <article className="panel">
              <div className="panel-title"><span>Device distribution</span><span className="panel-meta">EVENTS</span></div>
              <div className="device-list">
                {Object.entries(activity?.by_device ?? {}).map(([device, count]) => (
                  <div className="device-row" key={device}><span>{labelize(device)}</span><strong>{formatNumber(count)}</strong></div>
                ))}
              </div>
            </article>
          </div>
        </section>

        <section className="content-section customer-section reveal">
          <SectionHeading index="05" title="Customer 360" detail="Use a customer ID to run a profile read and two customer-prefix scans." />
          <form className="search-form" onSubmit={(event) => void loadCustomer(event)}>
            <label htmlFor="customer-id">Customer ID</label>
            <div className="search-row">
              <input id="customer-id" value={customerId} onChange={(event) => setCustomerId(event.target.value)} placeholder="CUST000001" />
              <button type="submit" disabled={customerLoading}>{customerLoading ? "Reading…" : "Load customer"}</button>
            </div>
          </form>
          {customerError && <div className="error-banner compact" role="alert">{customerError}</div>}
          {customer && (
            <div className="customer-layout">
              <article className="panel profile-panel">
                <div className="profile-code">{customer.customer_id}</div>
                <h3>{customer.profile.name || "Unnamed customer"}</h3>
                <p className="profile-location">{customer.profile.city || "City not recorded"}</p>
                <dl className="detail-list">
                  <div><dt>Email</dt><dd>{customer.profile.email || "—"}</dd></div>
                  <div><dt>Phone</dt><dd>{customer.profile.phone || "—"}</dd></div>
                  <div><dt>Category</dt><dd>{customer.preferences.category || "—"}</dd></div>
                  <div><dt>Payment</dt><dd>{customer.preferences.payment || "—"}</dd></div>
                </dl>
              </article>
              <article className="panel summary-panel">
                <div className="panel-title"><span>Order summary</span><span className="panel-meta">CUSTOMER 360</span></div>
                <div className="summary-grid">
                  <div><span>Orders</span><strong>{formatNumber(customer.order_summary.order_count)}</strong></div>
                  <div><span>Spending</span><strong>{formatMoney(customer.order_summary.total_spending)}</strong></div>
                  <div><span>Average</span><strong>{formatMoney(customer.order_summary.average_order_value)}</strong></div>
                  <div><span>Activities</span><strong>{formatNumber(customer.activity_summary.total_activities)}</strong></div>
                </div>
                <div className="mini-heading">Activity summary</div>
                <div className="tag-list">{Object.entries(customer.activity_summary.by_type).map(([type, count]) => <span key={type}>{labelize(type)} <b>{count}</b></span>)}</div>
              </article>
            </div>
          )}
          {customer && (
            <div className="two-column-grid customer-history">
              <article className="panel table-panel">
                <div className="panel-title"><span>Order history</span><span className="panel-meta">{customer.order_history.length} ROWS</span></div>
                <div className="table-scroll"><table><thead><tr><th>Order</th><th>Product</th><th>Status</th><th className="align-right">Amount</th></tr></thead><tbody>{customer.order_history.map((order) => <tr key={order.order_id}><td className="mono-label">{order.order_id}</td><td>{order.product}</td><td><span className={`status status-${order.status.toLowerCase()}`}>{order.status}</span></td><td className="align-right amount-cell">{formatMoney(order.amount)}</td></tr>)}</tbody></table></div>
              </article>
              <article className="panel table-panel">
                <div className="panel-title"><span>Activity history</span><span className="panel-meta">{customer.activity_history.length} ROWS</span></div>
                <div className="table-scroll"><table><thead><tr><th>Type</th><th>Device</th><th>Product</th></tr></thead><tbody>{customer.activity_history.map((item) => <tr key={`${item.timestamp}-${item.activity_id}`}><td>{labelize(item.type)}</td><td>{labelize(item.device)}</td><td>{item.product || "—"}</td></tr>)}</tbody></table></div>
              </article>
            </div>
          )}
        </section>
          </>
        )}

        <footer className="footer"><span>Apache HBase customer analytics</span><span className="mono-label">LOCAL DEVELOPMENT / SINGLE NODE</span></footer>
      </main>
    </div>
  );
}

export default App;
