# DisputeOS — Banking Dispute Resolution

**Live website:** [Open DisputeOS](https://disputeos-banking-resolution.vercel.app)

Demo login: `officer@demo.bank` / `Demo@2026!`. All banking data is synthetic.

The sidebar scrolls independently on short screens. The seeded workspace includes detailed complaints, transaction locations and recent dates, executed ten-agent results, case notes, sample historical approvals, and notifications. Seeded historical reviews are explicitly marked as synthetic. Existing cases with investigation results, reviews, notes, or evidence are preserved during the versioned data update.

A functional synthetic banking sandbox: React/TypeScript, FastAPI, SQLAlchemy, JWT, bcrypt and ten deterministic LangGraph agents. Humans approve decisions. No real money operations are connected.

## Windows PowerShell setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:JWT_SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python -m uvicorn backend.app.main:app --reload
```

In a second terminal:

```powershell
npm install
npm run dev
```

Open http://localhost:5173. API documentation: http://localhost:8000/docs. SQLite is automatically seeded with 50 synthetic customers, 200 transactions, 30 cases, and 10 sample policies. No paid API key is needed.

## Demo accounts

All use password `Demo@2026!`: `customer@demo.bank`, `officer@demo.bank`, `analyst@demo.bank`, `admin@demo.bank`. Customers see only their own cases. Officers review ordinary cases. Analysts and administrators review high-risk cases. High-risk approvals require two distinct senior reviewers.

Open a non-final case, run investigation, inspect AI analysis, attach evidence, and enter a reason under Human decisions. Every executed investigation and review is persisted with an audit event. New dispute submission automatically runs the ten agents. Use TXN-00001 and amount 887.50 for the demo customer.

## Architecture and features

```text
React workspace → JWT REST API → FastAPI / SQLAlchemy
  → LangGraph complaint → verification → history → risk → policy retrieval
  → investigation → recommendation → validation → escalation → case management
  → human approval gate → audit log + notification
```

Policy retrieval uses local TF-IDF cosine similarity with document references and scores. Risk uses explainable deterministic rules, not calibrated ML probabilities. Uploaded PDF/DOCX/TXT policies are searchable. Evidence has extension/signature validation and a 5 MB limit. Case access and review authority are enforced on the backend. Reports export database-visible cases as CSV or PDF. The workspace includes search, status filtering, case notes, agent execution outputs, notifications, light/dark theme and responsive layouts.

## Validation

```powershell
python -m pytest backend/tests -q
npm run build
```

Tests cover authentication, customer isolation, ten-agent execution, policy citations, distinct senior approval, rejected evidence, report export and audited rejection.

## Deployment

`vercel.json` builds the frontend and exposes FastAPI through `api/index.py`. Run `vercel --prod` from the root. Configure `JWT_SECRET_KEY` with a persistent random secret. For durable shared storage configure `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE`. Vercel's default `/tmp` SQLite database is ephemeral and different instances can have different data. The hosted default is an exploratory demo. Without a persistent JWT secret, cold starts may invalidate logins; sign in again.

Docker: copy `.env.example` to `.env`, set JWT_SECRET_KEY, then `docker compose up --build`. The backend runs on port 8000 with persistent PostgreSQL. Run the Vite frontend separately.

## Scope and remaining requirements

This is a working demo foundation, not a completed or certified enterprise banking platform. The supplied master prompt's remaining requirements include normalized tables and Alembic migrations, rate limiting, production object storage, malware scanning, native LangGraph interrupts/retries and conditional routing, live progress streaming and background jobs, configurable LLM integration, chunk-based FAISS/Chroma embeddings, trained Isolation Forest and Logistic Regression evaluation, assignment controls, full user administration, SLA tasks, and frontend/Playwright tests. Workflow snapshots are stored as JSON records; human resume is implemented with API review gates rather than LangGraph interrupts. Agent duration values are illustrative. Demo policy samples are not official regulations. The user directory is read-only.

Storage uses an indexed generic SQLAlchemy JSON record store. All important case mutations and audit events are within database transactions. No API keys or secrets are committed. Do not input real financial or personal data. Setting an OpenAI key alone does not enable an LLM provider. `DEMO_MODE=false` requires a persistent JWT secret; replace demo provisioning before any real use.

Troubleshooting: check file signatures/size for rejected uploads; scanned PDFs require OCR outside this implementation. Use PostgreSQL to avoid Vercel data resets. Check `/api/health` and API docs for connectivity. Review decisions require at least 10 characters of explanation, completed investigation, and appropriate authority.
