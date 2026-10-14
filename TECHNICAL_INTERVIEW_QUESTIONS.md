# 🎯 DevPulse: Complete Architectural Breakdown & Deep Technical Interview Masterclass

This document provides a deep-dive technical overview of the **DevPulse** project, followed by the **most rigorous, technical interview questions and comprehensive answers** spanning FastAPI internals, Python concurrency, ASGI architecture, data engineering bottlenecks, React mechanics, DORA productivity metrics, and large-scale system design.

---

## 1. Project Overview & System Architecture

### What is DevPulse?
**DevPulse** is a full-stack engineering productivity analytics platform. It aggregates software delivery performance indicators (Lead Time, Cycle Time, Pull Request Throughput, Deployment Frequency, and Escaped Bug Rate) to deliver actionable diagnostic interpretations and concrete next steps for Individual Contributors (ICs) and Engineering Managers.

### How it Works (End-to-End Flow)

```
┌─────────────────────────────────────────────────────────────┐
│                       React Frontend                        │
│                   (http://localhost:3000)                   │
│                                                             │
│  [IC Dashboard]      [Team Overview]     [Metrics Glossary] │
│   - Dev/Month filter  - Team aggregations - Benchmark rules │
│   - Trend PNG plots   - Team comparison   - Definitions     │
└───────────────┬─────────────────────────────▲───────────────┘
                │                             │
    HTTP / JSON │ CRA Proxy (:8000)           │ Streaming PNG & JSON
                ▼                             │
┌─────────────────────────────────────────────┴───────────────┐
│                      FastAPI Backend                        │
│                   (http://localhost:8000)                   │
│                                                             │
│  [main.py]                                                  │
│   ├── CORSMiddleware (localhost:3000)                       │
│   ├── GET /developers                                       │
│   ├── GET /months                                           │
│   ├── GET /metrics/{dev_id}/{month}                         │
│   ├── GET /manager-summary/{month}                          │
│   ├── GET /visualize/{dev_id}      (StreamingResponse PNG)  │
│   └── GET /visualize-team/{month}  (StreamingResponse PNG)  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                        Data Extraction
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               data_loader.py Engine & Analytics             │
│                                                             │
│  - Lazy Singleton Excel Parser (pd.ExcelFile)               │
│  - Pandas DataFrames (Dim_Developers, Metric_Examples)      │
│  - Heuristic Diagnostic Engine (_build_interpretation)      │
│  - Recommendation Engine (_build_next_steps)                │
│  - Headless Matplotlib Chart Generator (Agg backend)        │
│  - Data Source: intern_assignment_support_pack_dev_only.xlsx│
└─────────────────────────────────────────────────────────────┘
```

1. **Data Ingestion & Lazy Loading**:
   - The dataset resides in an Excel workbook (`intern_assignment_support_pack_dev_only_v3.xlsx`).
   - `data_loader.py` implements a global singleton caching pattern (`global _xl`) to avoid re-opening the zip archive on every request.
   - It reads two sheets: `Dim_Developers` (metadata: level, team, manager, service type) and `Metric_Examples` (monthly raw productivity counts & time deltas).

2. **Metrics Computation & Diagnostic Heuristics**:
   - For any developer and month, the backend extracts:
     - **Lead Time (days)**: PR open to production deployment.
     - **Cycle Time (days)**: Work started (In Progress) to Done.
     - **PR Throughput**: Total merged PRs in the month.
     - **Deployment Frequency**: Count of production deployments.
     - **Bug Rate (%)**: Escaped bugs / completed issues.
   - Business logic classifies metrics against established engineering benchmarks to generate qualitative feedback (`_build_interpretation`) and actionable remediation suggestions (`_build_next_steps`).

3. **Dynamic Visualization Pipeline**:
   - Endpoints `/visualize/{developer_id}` and `/visualize-team/{month}` use **headless Matplotlib** (`matplotlib.use('Agg')`).
   - Plots are customized with dark-mode styling (transparent alpha background, sleek hex colors `#3B82F6` and `#8B5CF6`).
   - The plot is saved to an in-memory byte buffer (`io.BytesIO()`), rewound (`buf.seek(0)`), and streamed over HTTP using Starlette's `StreamingResponse(media_type="image/png")`.

4. **Frontend Architecture**:
   - Single Page Application built with React 18.
   - Leverages Create React App's development proxy (`"proxy": "http://localhost:8000"`) in `package.json`, allowing the frontend to make relative calls (`/developers`, `/metrics/...`) without browser CORS preflight overhead in development.
   - State-driven reactive layout: switching tabs triggers data fetching through `useApi.js`, populating interactive metric cards, hover tooltips, and dynamic charts.

---

## 2. Hardcore Technical Interview Questions & Answers

---

### Category A: FastAPI, ASGI, Uvicorn & Python Concurrency

#### Q1: In `backend/main.py`, the endpoints are defined as regular synchronous functions (`def list_developers()`, `def get_metrics(...)`) rather than `async def`. How does FastAPI internally handle `def` vs `async def` route handlers, and what are the concurrency ramifications?
**Answer:**
* **FastAPI Concurrency Model**: FastAPI is built on top of Starlette and AnyIO.
  - When an endpoint is declared with **`async def`**, FastAPI executes it directly on the main **ASGI Event Loop**. If an `async def` function performs blocking, CPU-bound, or synchronous I/O operations (like `pd.read_excel()` or `plt.savefig()`), it blocks the single event loop thread, preventing any other concurrent requests from being processed until the operation finishes.
  - When an endpoint is declared with standard **`def`**, FastAPI detects that it is synchronous and offloads its execution to an **external threadpool** (`anyio.to_thread.run_sync`, wrapping a `ThreadPoolExecutor` with a default cap of 40 threads).
* **Ramifications in DevPulse**:
  - Because `data_loader.py` uses blocking synchronous libraries (**Pandas** and **Matplotlib**), declaring the endpoints as `def` is actually the correct design choice to prevent blocking the event loop.
  - *However*, threadpool offloading incurs context-switching overhead and can exhaust thread workers under high concurrent load (e.g., hundreds of concurrent users requesting Matplotlib chart generation).

#### Q2: What is ASGI, how does it differ from WSGI, and how does the Uvicorn-Starlette-FastAPI stack process a request?
**Answer:**
* **WSGI (Web Server Gateway Interface, PEP 3333)**: Synchronous, single-callable standard: `application(environ, start_response)`. Each request blocks its worker thread or process until completion. It cannot natively handle WebSockets, long polling, or HTTP/2 multiplexing without monkey-patching (like gevent).
* **ASGI (Asynchronous Server Gateway Interface)**: Asynchronous standard designed around Python's `asyncio`. It uses a 3-argument callable:
  ```python
  async def app(scope, receive, send):
      ...
  ```
  - `scope`: A dictionary containing connection metadata (type, HTTP method, path, headers).
  - `receive`: An `async` callable yielding events (e.g., `http.request` with body chunks).
  - `send`: An `async` callable dispatching events back to the client (e.g., `http.response.start`, `http.response.body`).
* **The Stack**:
  1. **Uvicorn** binds the TCP socket, parses the raw HTTP/1.1 or HTTP/2 protocol into ASGI event dictionaries.
  2. **Starlette** receives the ASGI connection, routes requests via Radix trees, runs middleware pipelines, and manages request/response lifecycles.
  3. **FastAPI** adds high-level abstractions: dependency injection, Pydantic data serialization/validation, OpenAPI/Swagger generation, and status code handling.

#### Q3: In `main.py`, `CORSMiddleware` is configured with `allow_origins=["http://localhost:3000"]`. How does CORS work under the hood at the HTTP protocol level, what is a "preflight" request, and why didn't the React app fail even when requests were sent directly?
**Answer:**
* **CORS Mechanics**: Cross-Origin Resource Sharing is a browser-enforced security mechanism preventing malicious scripts on one origin (`http://evil.com`) from reading data from another origin (`http://api.com`).
* **Preflight (`OPTIONS`) Request**:
  - For non-simple HTTP requests (e.g., methods other than GET/POST/HEAD, or custom headers like `Authorization` or `Content-Type: application/json`), the browser automatically dispatches an `OPTIONS` request before the actual request.
  - It sends headers:
    - `Origin: http://localhost:3000`
    - `Access-Control-Request-Method: GET`
    - `Access-Control-Request-Headers: content-type`
  - FastAPI's `CORSMiddleware` intercepts this before hitting route handlers and replies with `200 OK` and headers:
    - `Access-Control-Allow-Origin: http://localhost:3000`
    - `Access-Control-Allow-Methods: *`
    - `Access-Control-Allow-Headers: *`
* **Why React worked without CORS**:
  - In `frontend/package.json`, `"proxy": "http://localhost:8000"` is configured.
  - When React makes a call to `/developers`, the request is sent to the local Webpack dev server on port 3000 (Same-Origin). The Node.js dev server proxies the request via TCP to port 8000 on the server side. Because servers do not enforce browser CORS restrictions, CORS is completely bypassed during dev proxying.

#### Q4: What are the security vulnerabilities and production design flaws in `backend/main.py`? How would you refactor it to meet production enterprise standards?
**Answer:**
1. **Missing Pydantic Response Models & Type Validation**:
   - Endpoints return raw Python dictionaries or Pandas data structures without Pydantic schemas (`response_model=...`).
   - *Risk*: Data leakage (e.g., internal fields or NaN values serialized into invalid JSON), lack of strict contracts, and missing API documentation schemas in Swagger UI.
2. **Wildcard / Hardcoded CORS**:
   - `allow_origins=["http://localhost:3000"]` is hardcoded. In production, this should be driven by environment variables (`os.getenv("ALLOWED_ORIGINS")`).
3. **Missing Path/Query Parameter Validation**:
   - `developer_id: str` and `month: str` have no regex or length constraints. An attacker could pass unexpected strings or traversal payloads.
   - *Fix*: Use Pydantic's `Field` or FastAPI's `Path(regex=r"^DEV-\d{3}$")` and `Path(regex=r"^\d{4}-\d{2}$")`.
4. **Lack of Global Exception Handling**:
   - Only `HTTPException(404)` is caught. Unhandled exceptions (e.g., file corruption, missing columns) will result in raw 500 tracebacks. A custom exception handler using `@app.exception_handler(Exception)` should sanitize and log errors.

---

### Category B: Data Engineering, Pandas Internals & Memory Architecture

#### Q5: Examine `backend/data_loader.py`:
```python
_xl = None

def _load_excel():
    global _xl
    if _xl is None:
        _xl = pd.ExcelFile(EXCEL_PATH)
    return _xl
```
#### What are the thread-safety issues, multi-process scaling issues, and memory lifecycle implications of this singleton caching pattern?
**Answer:**
1. **Thread Safety & Race Conditions**:
   - When multiple threads in Uvicorn's `ThreadPoolExecutor` call `_load_excel()` simultaneously upon startup, multiple threads could evaluate `_xl is None` as true before the variable is assigned (a classic "Check-Then-Act" race condition).
   - While Python's GIL prevents memory corruption during pointer assignment, multiple `pd.ExcelFile` instances might be instantiated concurrently, wasting memory and file descriptors.
   - *Fix*: Use a thread lock (`threading.Lock()`) with the Double-Checked Locking pattern.
2. **Multi-Process / Multi-Worker Isolation**:
   - If Uvicorn is run with multiple worker processes (`uvicorn main:app --workers 4`), memory is **not shared** between processes.
   - Each worker process maintains its own independent `_xl` singleton, duplicating the memory footprint across all OS processes.
3. **Lack of Cache Invalidation & File Locking**:
   - If the underlying Excel file is replaced or updated on disk, `_load_excel()` will never reload the file until the process is restarted.
   - On Windows, holding an open file descriptor on an Excel file can lock the file, preventing OS-level updates or replacements.
4. **Repeated Parsing Overhead**:
   - `pd.ExcelFile` keeps the zip archive handle open, but calling `pd.read_excel(xl, sheet_name=...)` inside `_get_metrics_df()` on **every single request** forces Python to re-parse the XML sheet DOM from scratch on every endpoint invocation!
   - *Fix*: Cache the parsed DataFrames (`_metrics_df`, `_devs_df`) in memory rather than the `ExcelFile` reader.

#### Q6: Why is storing and querying analytical data via Excel/Pandas in an HTTP API an anti-pattern, and what storage engine should replace it?
**Answer:**
* **Why it's an anti-pattern**:
  1. **Latency & CPU Burn**: Parsing `.xlsx` requires decompressing a ZIP container and parsing massive OpenXML structures. This is CPU-intensive and synchronous.
  2. **No Column Projection or Predicate Pushdown**: Pandas reads the entire sheet into memory before filtering `df[df["developer_id"] == dev_id]`. For a dataset with millions of rows, this leads to $O(N)$ full table scans in memory and out-of-memory (OOM) crashes.
  3. **No Indexing**: Lookups are linear searches ($O(N)$) rather than $B$-Tree or Hash-indexed lookups ($O(1)$ / $O(\log N)$).
* **Target Architecture for Analytics**:
  - **Embedded OLAP**: Replace with **DuckDB** or **SQLite**. DuckDB can directly query Parquet or CSV files with vectorized SIMD execution, column projection, and sub-millisecond response times.
  - **Production Scale**: Ingest data into **PostgreSQL** (with composite indexes on `(developer_id, month)`) or a columnar time-series database like **ClickHouse** / **TimescaleDB**.

---

### Category C: Matplotlib, Binary Streaming & System Performance

#### Q7: In `get_developer_trend_plot()`, the backend uses:
```python
matplotlib.use('Agg')
import matplotlib.pyplot as plt
...
buf = io.BytesIO()
plt.savefig(buf, format='png', dpi=120, transparent=True)
buf.seek(0)
plt.close(fig)
return buf
```
#### Explain:
1. Why `matplotlib.use('Agg')` is required in a web backend.
2. What happens if `plt.close(fig)` is omitted.
3. Why `pyplot` is dangerous in multi-threaded environments, and how to write this using thread-safe Object-Oriented Matplotlib.
4. Why `buf.seek(0)` is necessary before returning the stream.

**Answer:**
1. **`matplotlib.use('Agg')`**:
   - By default, Matplotlib attempts to initialize an interactive GUI backend (e.g., Tkinter, Qt, macOS cocoa) to display windows on a desktop.
   - On a headless server (Docker, Linux VM, cloud instances), no X-server or display monitor exists; Matplotlib will crash with an error (`no display name and no $DISPLAY environment variable`).
   - The `Agg` (Anti-Grain Geometry) backend renders raster images directly to memory buffers without requiring a GUI window system.
2. **Omitting `plt.close(fig)` (The Memory Leak)**:
   - Matplotlib's global state keeps internal references to all active figures in `pyplot._pylab_helpers.Gcf` to track window numbers.
   - If `plt.close(fig)` is not called, Python's garbage collector cannot free the memory occupied by the figure, axes, and artists. Over time, under production web traffic, this causes a severe **continuous memory leak** culminating in an OOM process kill.
3. **Thread-Safety Danger of `pyplot`**:
   - `matplotlib.pyplot` is an imperative, stateful interface designed for interactive scripting. It maintains a **global current figure and current axes**.
   - If two request threads execute `plt.plot()` concurrently in the threadpool, they will write onto each other's figures, resulting in race conditions, corrupted charts, or thread crashes.
   - **Thread-safe Object-Oriented Solution**:
     ```python
     from matplotlib.figure import Figure

     def get_developer_trend_plot_safe(developer_id: str):
         fig = Figure(figsize=(6, 4))
         ax = fig.subplots()
         ax.plot(months, lead_times, label='Lead Time', color='#3B82F6')
         buf = io.BytesIO()
         fig.savefig(buf, format='png', dpi=120, transparent=True)
         buf.seek(0)
         return buf
     ```
4. **`buf.seek(0)`**:
   - When `fig.savefig(buf, ...)` writes the PNG byte stream to `io.BytesIO`, the stream's internal cursor advances to the end of the byte array (byte offset $N$).
   - If the buffer is passed to `StreamingResponse` without resetting the cursor, the response reader starts reading from offset $N$ and immediately encounters End-Of-File (EOF), returning an empty 0-byte response to the client. `buf.seek(0)` rewinds the cursor to the beginning.

#### Q8: What are the architectural tradeoffs of server-side Matplotlib chart generation vs client-side charting libraries (e.g., Chart.js, Recharts, D3)?
**Answer:**
| Dimension | Server-Side Matplotlib (Current) | Client-Side (Recharts / D3 / Chart.js) |
|---|---|---|
| **CPU Utilization** | High on backend (image rasterization). Blocks server threadpool. | Negligible on backend. Offloaded to client GPU/browser. |
| **Network Payload** | Large (50KB–200KB PNG raster image per chart). | Tiny (raw JSON data points: ~500 bytes). |
| **Interactivity** | None (static flat image, no tooltips on datapoints, no zooming). | Rich (dynamic SVG/Canvas tooltips, hover animations, filters). |
| **Caching** | Requires HTTP caching / reverse proxy image cache. | Standard API response caching (React Query / SWR / browser cache). |
| **Consistency** | 100% deterministic pixel-perfect rendering across all devices. | Minor font/rendering variations across browsers. |

*Verdict*: Server-rendered static images are suitable for PDF export or email reports, but client-side charting (e.g., Recharts) is vastly superior for an interactive web dashboard.

---

### Category D: Frontend Mechanics & React Internals

#### Q9: In `frontend/src/App.js`:
```javascript
const loadMetrics = useCallback(() => {
  if (!selectedDev || !selectedMonth || view !== "ic") return;
  setLoading(true);
  setError(null);
  setMetrics(null);
  fetchMetrics(selectedDev, selectedMonth)
    .then(data => { setMetrics(data); setLoading(false); })
    .catch(err => { setError(err.message); setLoading(false); });
}, [selectedDev, selectedMonth, view]);

useEffect(() => { loadMetrics(); }, [loadMetrics]);
```
#### Identify the race condition in this code. If a user quickly switches from "DEV-001" to "DEV-002", what can happen, and how do you fix it with an `AbortController`?
**Answer:**
* **The Race Condition**:
  - `fetchMetrics` is asynchronous and relies on network latency.
  - If the user selects "DEV-001" and then immediately switches to "DEV-002":
    1. Request 1 for DEV-001 is dispatched.
    2. Request 2 for DEV-002 is dispatched.
    3. If Request 2 completes in 50ms, the state is updated to DEV-002.
    4. If Request 1 was delayed by server load and finishes in 200ms, its `.then()` callback executes *after* Request 2, overwriting the dashboard with DEV-001's data while the UI dropdown displays DEV-002!
* **The Solution (`AbortController`)**:
  ```javascript
  useEffect(() => {
    if (!selectedDev || !selectedMonth || view !== "ic") return;
    
    const controller = new AbortController();
    setLoading(true);

    fetch(`/metrics/${selectedDev}/${selectedMonth}`, { signal: controller.signal })
      .then(res => res.json())
      .then(data => {
        setMetrics(data);
        setLoading(false);
      })
      .catch(err => {
        if (err.name !== "AbortError") {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => controller.abort(); // Cancels inflight request on re-render / unmount
  }, [selectedDev, selectedMonth, view]);
  ```

#### Q10: How does React 18's state batching work, and how does `useCallback` prevent unnecessary re-renders in this component tree?
**Answer:**
* **Automatic Batching in React 18**:
  - Prior to React 18, React only batched state updates inside synthetic event handlers (like `onClick`). State updates inside `fetch().then()`, `setTimeout`, or native promises triggered separate render cycles for each `setState`.
  - In React 18, **Automatic Batching** is enabled everywhere:
    ```javascript
    .then(data => {
      setMetrics(data);  // Does not trigger a render yet
      setLoading(false); // Batched together into a SINGLE re-render!
    })
    ```
* **Role of `useCallback`**:
  - In JavaScript, functions are first-class objects; every time `App()` renders, any raw inline function is re-allocated at a new memory reference.
  - If that function is passed as a dependency to `useEffect`, the effect detects a reference change on every render, triggering an **infinite render loop**.
  - `useCallback` memoizes the function definition across renders until one of its dependencies (`[selectedDev, selectedMonth, view]`) changes.

---

### Category E: Domain Knowledge & Engineering Productivity Metrics (DORA / SPACE)

#### Q11: DevPulse tracks five primary metrics:
1. **Lead Time (days)**
2. **Cycle Time (days)**
3. **PR Throughput**
4. **Deployment Frequency**
5. **Escaped Bug Rate (%)**

#### Compare these against the industry-standard DORA metrics. What is the fundamental difference between Lead Time and Cycle Time in this codebase?
**Answer:**
* **Comparison with DORA (DevOps Research and Assessment)**:
  - DORA defines 4 core metrics:
    1. *Deployment Frequency* (Shipping cadence) — **Tracked in DevPulse**.
    2. *Lead Time for Changes* (Commit to Production) — **Tracked in DevPulse** (approximated as PR creation to prod deploy).
    3. *Change Failure Rate (CFR)* (% of deployments causing production failures) — DevPulse uses *Escaped Bug Rate* (bugs / completed issues) instead.
    4. *Failed Deployment Recovery Time / MTTR* (Mean Time to Recover) — **Not tracked in DevPulse**.
  - DevPulse also adds *Cycle Time* and *PR Throughput*, aligning with the **SPACE framework** (Performance & Activity dimensions).
* **Lead Time vs. Cycle Time Distinction**:
  - **Cycle Time**: Measured from when an issue moves into **"In Progress"** until it is marked **"Done"**. It measures individual coding, local testing, and developer execution efficiency.
  - **Lead Time**: Measured from when a **Pull Request is opened** until it is **deployed to production**. It measures organizational velocity: code review latency, CI/CD pipeline duration, QA signoff, and deployment gating.
  - *Key insight*: A developer can have a rapid Cycle Time (3 days) but a dreadful Lead Time (10 days) if their PR sits in review queues or deployment windows are blocked.

#### Q12: How does Goodhart's Law apply to engineering productivity dashboards like DevPulse, and how does the data model protect against perverse incentives?
**Answer:**
* **Goodhart's Law**: *"When a measure becomes a target, it ceases to be a good measure."*
  - If an engineering organization measures engineers solely on **PR Throughput**, developers will split a single 200-line feature into ten 20-line micro-PRs or submit trivial commits to artificially inflate throughput.
  - If measured solely on **Cycle Time**, developers will avoid refactoring technical debt or taking on complex architectural work in favor of trivial 1-point bugs.
* **How DevPulse Balances Metrics**:
  - DevPulse employs **Counterbalancing Metrics**:
    - **Speed vs Quality**: High PR Throughput and low Lead Time are counterbalanced by **Escaped Bug Rate**. If an engineer rushes changes without automated tests, their Escaped Bug Rate surges, triggering warning patterns (`"Speed may be outpacing testing"`).
    - **Output vs Release Cadence**: PR Throughput is balanced against **Deployment Frequency**. Merging 20 PRs that sit unreleased in a staging branch yields a poor deployment frequency score.

---

### Category F: System Design & Enterprise Scale-Up

#### Q13: You are asked to scale DevPulse from a toy project (1 Excel file, 8 developers) to an enterprise system monitoring 50,000 developers across 10,000 GitHub/GitLab repositories in real time. Architect the target system.
**Answer:**

```
┌─────────────────┐       ┌─────────────────┐
│ GitHub Webhooks │       │  Jira / Linear  │
│ (PRs, Deploys)  │       │  (Issue State)  │
└────────┬────────┘       └────────┬────────┘
         │                         │
         ▼                         ▼
┌───────────────────────────────────────────┐
│      API Gateway & Ingestion Layer        │
│    (Signature Verification, Rate Limit)   │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌───────────────────────────────────────────┐
│     Apache Kafka / AWS Kinesis Stream     │
│   Topics: 'pr-events', 'deploy-events'    │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌───────────────────────────────────────────┐
│     Stream Processors (Flink / Faust)     │
│    Windowed cycle/lead time computation   │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌───────────────────────────────────────────┐
│             ClickHouse / OLAP             │
│    Aggregated timeseries & rollup views   │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌───────────────────────────────────────────┐
│       FastAPI Query Engine (Cached)       │
│        Redis (L1) + ClickHouse (L2)       │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌───────────────────────────────────────────┐
│      React Client (Recharts / Canvas)     │
└───────────────────────────────────────────┘
```

1. **Ingestion Layer (Event-Driven)**:
   - Eliminate Excel batch loads. Listen to **GitHub/GitLab Webhooks** (`pull_request.opened`, `pull_request.closed`, `workflow_job.completed`, `deployment.success`) and issue tracker webhooks (Jira/Linear).
   - Ingestion service validates HMAC signatures and publishes raw events to **Apache Kafka**.
2. **Stream Processing & Correlation Engine**:
   - A distributed stream processor (**Apache Flink** or **Faust**) processes events using event-time sliding windows.
   - Correlates issue ID from commit message / PR title with deployment tags to compute exact Lead Time ($t_{\text{deploy}} - t_{\text{pr\_open}}$) and Cycle Time ($t_{\text{done}} - t_{\text{in\_progress}}$).
3. **Analytical Storage (OLAP)**:
   - Store processed rollups in **ClickHouse** or **PostgreSQL with TimescaleDB**.
   - Schema optimized with Partitioning by `(tenant_id, date)` and Primary Keys on `(team_id, developer_id, event_timestamp)`.
4. **Caching & API Tier**:
   - High-throughput **FastAPI** backend with **Pydantic v2** (Rust-based serializer).
   - Multi-tier caching: **Redis** stores monthly aggregated metric objects with 1-hour TTL.
5. **Client-Side Rendering**:
   - Migrate Matplotlib PNG generation to client-side **Recharts** or **Apache ECharts** rendering interactive SVG/WebGL charts directly in the browser.

---

## 3. Quick Reference: Running & Validating the Project

### Services & Port Mappings
| Service | Technology | Port | URL |
|---|---|---|---|
| **Backend API** | FastAPI + Uvicorn | `8000` | http://127.0.0.1:8000 |
| **API Documentation** | Swagger UI | `8000` | http://127.0.0.1:8000/docs |
| **Frontend UI** | React (Create React App) | `3000` | http://localhost:3000 |

### Active Verification Commands
- Check API health:
  ```powershell
  Invoke-RestMethod -Uri "http://127.0.0.1:8000/months"
  Invoke-RestMethod -Uri "http://127.0.0.1:8000/developers"
  Invoke-RestMethod -Uri "http://127.0.0.1:8000/metrics/DEV-001/2026-04"
  ```
- Check Web Frontend:
  ```powershell
  Invoke-WebRequest -Uri "http://localhost:3000"
  ```
