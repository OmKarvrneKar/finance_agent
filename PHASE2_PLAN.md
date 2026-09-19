# Phase 2 Implementation Plan - AI Finance Agent

Generated: 2026-09-19 | Based on actual codebase audit

---

## A. Current-State Findings

### Backend

| Area | Status |
|------|--------|
| Authentication | ABSENT - Zero auth on all 15 endpoints |
| Multi-user | ABSENT - No user_id on any of 5 models |
| DB Migrations | ABSENT - Manual ALTER TABLE in main.py, no Alembic |
| API Key Auth | ABSENT - Backend is fully open |
| Rate Limiting | Phase 1 done - IP-based, /agent/ask only, in-memory |
| Decimal | Phase 1 done - All monetary fields Numeric(12,2) |
| AI Error Handling | Phase 1 done - Timeout, connection, 429 handling |
| Health Check | ABSENT - No /health endpoint |
| Logging | Basic logging - no structured JSON logging |

### Frontend

| Area | Status |
|------|--------|
| Auth UI | ABSENT - No login/register pages |
| Transaction Editing | ABSENT - No edit/delete in UI |
| Category Correction | ABSENT - Can only set on receipt confirm |
| Mobile Nav | ABSENT - No hamburger menu |
| State Management | None - All useState, no Context/Redux |
| Tests | ZERO - No test framework, no test files |
| Date Range Controls | ABSENT - Dashboard locked to current month |
| Search | ABSENT - No text search on transactions |
| Error Boundaries | ABSENT |
| Toast Notifications | ABSENT |

### AI Agent (11 tools - ALL NOT user-scoped)

Every tool queries the entire database. No tool filters by user_id.

### Security Risks

| Risk | Severity |
|------|----------|
| No authentication | CRITICAL |
| No user isolation | CRITICAL |
| .env committed to repo | HIGH |
| limit=10000 dumpable | MEDIUM |
| CORS too permissive | MEDIUM |
| Rate limiter fails behind proxy | MEDIUM |

---

## B. Phase 2 Priorities

### MUST-HAVE

1. User authentication - JWT-based login/register
2. User model + user_id on all resources - Data isolation
3. Authorization middleware - Every endpoint scoped to authenticated user
4. Agent tools user-scoped - All 11 tools filter by user_id
5. Alembic migrations - Replace manual ALTER TABLE
6. Transaction editing - Backend API + frontend UI
7. Category correction - Backend API + frontend UI
8. Frontend tests - At least critical paths
9. Health check endpoint - /api/health

### NICE-TO-HAVE

10. Transaction search + date range filter
11. Column sorting on transactions table
12. Dynamic category list (not hardcoded)
13. Mobile responsive navigation
14. Toast notifications
15. Error boundaries
16. WhatIfSimulator mobile layout fix
17. Conversation persistence in AI chat
18. Dashboard date range controls
19. PostgreSQL readiness (config-driven)
20. Structured JSON logging
21. Docker setup
22. Security headers middleware
23. API rate limiting on all endpoints
24. Export/download transactions

---

## C. Recommended Implementation Order

```
Phase 2A: Auth Foundation (MUST)        -> Blocks everything
Phase 2B: User Scoping (MUST)           -> Blocks multi-user
Phase 2C: DB Migrations (MUST)          -> Enables schema evolution
Phase 2D: Transaction Features (MUST)   -> Core UX
Phase 2E: Frontend Auth + Tests (MUST)  -> Complete auth flow
Phase 2F: Polish and Quality (NICE)     -> UX improvements
Phase 2G: Production Readiness (NICE)   -> Deployment hardening
```

Dependencies:
- 2B depends on 2A (need user model first)
- 2C can run in parallel with 2A/2B
- 2D depends on 2B (transaction editing needs user scoping)
- 2E depends on 2A (need auth API to build login UI)
- 2F and 2G are independent, depend on 2A-2E

---

## D. Detailed Task-by-Task Plan

### Phase 2A: Authentication Foundation

**Task 2A-1: Add auth dependencies**
- backend/requirements.txt - Add passlib[bcrypt], python-jose[cryptography]
- backend/app/auth.py - NEW: JWT token creation/verification, password hashing, get_current_user dependency

**Task 2A-2: User model**
- backend/app/database/db.py - Add User model: id, email (unique), hashed_password, full_name, is_active, created_at
- backend/app/models/schemas.py - Add UserCreate, UserLogin, UserResponse, TokenResponse

**Task 2A-3: Auth endpoints**
- backend/app/routers/auth.py - NEW: POST /api/auth/register, POST /api/auth/login, GET /api/auth/me
- backend/app/main.py - Register auth router

**Task 2A-4: Environment config**
- backend/.env.example - Add JWT_SECRET_KEY, JWT_ALGORITHM=HS256, JWT_EXPIRE_MINUTES=1440

---

### Phase 2B: User Scoping

**Task 2B-1: Add user_id to all models**
- backend/app/database/db.py - Add user_id ForeignKey to Transaction, BudgetGoal, SavingsGoal, PendingReceipt, AnomalyReview. Add indexes on (user_id, category), (user_id, date).

**Task 2B-2: Update CRUD operations**
- backend/app/database/crud.py - All queries filtered by user_id
- backend/app/routers/transactions.py - Inject current_user, pass user_id
- backend/app/routers/budgets.py - Same
- backend/app/routers/receipts.py - Same
- backend/app/routers/forecast.py - Same
- backend/app/routers/anomalies.py - Same
- backend/app/routers/agent.py - Same

**Task 2B-3: Scope agent tools**
- backend/app/services/agent_tools.py - Add user_id to all 6 functions
- backend/app/services/agent_service.py - Pass user_id to tool calls

**Task 2B-4: Scope services**
- backend/app/services/forecasting.py - Filter by user_id
- backend/app/services/anomalies.py - Same
- backend/app/services/budgets.py - Same

---

### Phase 2C: Database Migrations

**Task 2C-1: Set up Alembic**
- backend/alembic.ini - NEW: Alembic config
- backend/alembic/ - NEW: env and scripts
- backend/app/database/db.py - Expose engine for Alembic

**Task 2C-2: Initial migration**
- Generate from current models + User + user_id FKs

**Task 2C-3: Remove manual migrations**
- backend/app/main.py - Remove ALTER TABLE blocks
- Add proper indexes in Alembic migration

---

### Phase 2D: Transaction Features

**Task 2D-1: Transaction editing API**
- backend/app/routers/transactions.py - PUT /api/transactions/{id}, DELETE /api/transactions/{id}
- backend/app/models/schemas.py - TransactionUpdate schema
- backend/app/database/crud.py - update_transaction, delete_transaction

**Task 2D-2: Transaction search API**
- backend/app/routers/transactions.py - search param (ILIKE on description), start_date, end_date params
- backend/app/database/crud.py - Update get_transactions_paginated

**Task 2D-3: Dynamic categories**
- backend/app/routers/transactions.py - GET /api/categories
- backend/app/database/crud.py - Query distinct categories for user

---

### Phase 2E: Frontend Auth + Tests

**Task 2E-1: Auth context + protected routes**
- frontend/src/context/AuthContext.jsx - NEW: User state, login/logout, token storage
- frontend/src/App.jsx - Wrap routes with ProtectedRoute
- frontend/src/utils/api.js - Add Authorization header interceptor

**Task 2E-2: Login and Register pages**
- frontend/src/pages/Login.jsx - NEW: Login form
- frontend/src/pages/Register.jsx - NEW: Registration form
- frontend/src/components/Navigation.jsx - Add auth state, logout button

**Task 2E-3: Frontend test setup**
- frontend/vitest.config.js - NEW: Vitest config
- frontend/src/test/ - NEW: Test utilities, mocks
- Add tests for: auth flow, transaction list, budget CRUD, agent chat

---

### Phase 2F: Polish and Quality

**Task 2F-1: Transaction editing UI**
- frontend/src/components/TransactionRow.jsx - Add edit/delete buttons
- frontend/src/components/EditTransactionModal.jsx - NEW: Edit form
- frontend/src/utils/api.js - Add updateTransaction, deleteTransaction, getCategories

**Task 2F-2: Search and filters**
- frontend/src/pages/Transactions.jsx - Add search input, date range picker, column sort

**Task 2F-3: Dynamic categories**
- frontend/src/pages/Transactions.jsx - Fetch categories from API
- frontend/src/components/BudgetGoals.jsx - Fetch categories from API
- frontend/src/components/WhatIfSimulator.jsx - Same

**Task 2F-4: Mobile responsive**
- frontend/src/components/Navigation.jsx - Add hamburger menu
- frontend/src/components/WhatIfSimulator.jsx - Stack columns on mobile
- frontend/src/components/PendingReceipts.jsx - Stack form on mobile

**Task 2F-5: Error handling UX**
- frontend/src/components/ErrorBoundary.jsx - NEW: React error boundary
- frontend/src/components/Toast.jsx - NEW: Toast notification system
- Update all API calls to show toast on error

**Task 2F-6: Dashboard improvements**
- frontend/src/pages/Dashboard.jsx - Add month selector, date range controls

---

### Phase 2G: Production Readiness

**Task 2G-1: Health check**
- backend/app/routers/health.py - NEW: GET /api/health (DB connectivity, AI service status)

**Task 2G-2: Security headers**
- backend/app/main.py - Add SecurityHeadersMiddleware (X-Content-Type-Options, X-Frame-Options, etc.)

**Task 2G-3: CORS tightening**
- backend/app/main.py - Restrict allow_methods to GET/POST/PUT/DELETE, restrict allow_headers

**Task 2G-4: Structured logging**
- backend/app/logging_config.py - NEW: JSON structured logging setup
- Replace all print/logging calls

**Task 2G-5: Docker**
- backend/Dockerfile - NEW
- docker-compose.yml - NEW: Backend + frontend + optional PostgreSQL

**Task 2G-6: PostgreSQL readiness**
- backend/app/database/db.py - Config-driven DATABASE_URL (SQLite default, PostgreSQL optional)
- backend/requirements.txt - Add psycopg2-binary

**Task 2G-7: Requirements cleanup**
- backend/requirements.txt - Remove unused google-generativeai, add version pins

---

## E. Files Likely to Change

### Backend - Must Change (16 files)

| File | Changes |
|------|---------|
| backend/app/database/db.py | User model, user_id FKs on all models, indexes |
| backend/app/models/schemas.py | User schemas, TransactionUpdate, TokenResponse |
| backend/app/database/crud.py | user_id filters, update_transaction, delete_transaction, get_categories |
| backend/app/routers/transactions.py | Auth injection, user_id scoping, PUT/DELETE, search, date filter |
| backend/app/routers/agent.py | Auth injection, user_id scoping |
| backend/app/routers/budgets.py | Auth injection, user_id scoping |
| backend/app/routers/receipts.py | Auth injection, user_id scoping |
| backend/app/routers/forecast.py | Auth injection, user_id scoping |
| backend/app/routers/anomalies.py | Auth injection, user_id scoping |
| backend/app/services/agent_tools.py | user_id parameter on all 6 functions |
| backend/app/services/agent_service.py | Pass user_id to tools |
| backend/app/services/forecasting.py | user_id filter on all queries |
| backend/app/services/anomalies.py | user_id filter on all queries |
| backend/app/services/budgets.py | user_id filter on all queries |
| backend/app/main.py | Register auth router, remove ALTER TABLE |
| backend/requirements.txt | Add auth deps, remove google-generativeai |

### Backend - New Files (5 files)

| File | Purpose |
|------|---------|
| backend/app/auth.py | JWT + password hashing + get_current_user |
| backend/app/routers/auth.py | Register, login, me endpoints |
| backend/app/routers/health.py | Health check endpoint |
| backend/alembic.ini | Alembic configuration |
| backend/alembic/ | Migration scripts |

### Frontend - Must Change (10 files)

| File | Changes |
|------|---------|
| frontend/src/App.jsx | ProtectedRoute wrapper, new routes |
| frontend/src/utils/api.js | Auth interceptor, new API calls |
| frontend/src/components/Navigation.jsx | Auth state, logout, hamburger menu |
| frontend/src/components/TransactionRow.jsx | Edit/delete buttons |
| frontend/src/pages/Transactions.jsx | Search, date filter, dynamic categories |
| frontend/src/pages/Dashboard.jsx | Month selector, date range |
| frontend/src/components/BudgetGoals.jsx | Dynamic categories |
| frontend/src/components/WhatIfSimulator.jsx | Dynamic categories, mobile layout |
| frontend/src/components/PendingReceipts.jsx | Mobile responsive |
| frontend/src/index.css | Mobile responsive styles |

### Frontend - New Files (6 files)

| File | Purpose |
|------|---------|
| frontend/src/context/AuthContext.jsx | Auth state management |
| frontend/src/pages/Login.jsx | Login form |
| frontend/src/pages/Register.jsx | Registration form |
| frontend/src/components/EditTransactionModal.jsx | Edit transaction form |
| frontend/src/components/ErrorBoundary.jsx | React error boundary |
| frontend/src/components/Toast.jsx | Toast notification system |

---

## F. Database/Schema Changes

### New Table: users

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email VARCHAR NOT NULL UNIQUE,
    hashed_password VARCHAR NOT NULL,
    full_name VARCHAR,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_users_email ON users (email);
```

### Modified Tables (all add user_id)

```sql
ALTER TABLE transactions ADD COLUMN user_id INTEGER REFERENCES users(id);
ALTER TABLE budget_goals ADD COLUMN user_id INTEGER REFERENCES users(id);
ALTER TABLE savings_goals ADD COLUMN user_id INTEGER REFERENCES users(id);
ALTER TABLE pending_receipts ADD COLUMN user_id INTEGER REFERENCES users(id);
ALTER TABLE anomaly_reviews ADD COLUMN user_id INTEGER REFERENCES users(id);
```

### New Indexes

```sql
CREATE INDEX ix_transactions_user_date ON transactions (user_id, date);
CREATE INDEX ix_transactions_user_category ON transactions (user_id, category);
CREATE INDEX ix_budget_goals_user ON budget_goals (user_id);
CREATE INDEX ix_savings_goals_user ON savings_goals (user_id);
```

### Data Migration Strategy

1. Create users table
2. Create a default admin user for existing data
3. Add user_id columns (nullable initially)
4. Backfill all existing rows with default user_id
5. Make user_id NOT NULL
6. Add foreign key constraints

---

## G. API Changes

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/auth/register | Register new user |
| POST | /api/auth/login | Login, returns JWT |
| GET | /api/auth/me | Get current user profile |
| GET | /api/health | Health check |
| GET | /api/categories | List user's categories |
| PUT | /api/transactions/{id} | Update a transaction |
| DELETE | /api/transactions/{id} | Delete a transaction |

### Modified Endpoints (all require Authorization: Bearer <token>)

| Endpoint | Change |
|----------|--------|
| POST /api/upload-statement | Scoped to authenticated user |
| GET /api/transactions | Filter by user_id, add search/date params |
| GET /api/subscriptions | Filter by user_id |
| POST /api/agent/ask | Agent queries scoped to user |
| GET /api/budgets | Filter by user_id |
| POST /api/budgets | Scoped to user |
| DELETE /api/budgets/{category} | Scoped to user |
| GET /api/goals | Filter by user_id |
| POST /api/goals | Scoped to user |
| POST /api/simulate | Scoped to user |
| POST /api/receipts/upload | Scoped to user |
| GET /api/receipts/pending-review | Filter by user_id |
| POST /api/receipts/{id}/confirm | Scoped to user |
| POST /api/receipts/{id}/discard | Scoped to user |
| GET /api/forecast/summary | Filter by user_id |
| GET /api/forecast/alerts | Filter by user_id |
| GET /api/forecast/category/{name} | Filter by user_id |
| GET /api/anomalies | Filter by user_id |
| POST /api/anomalies/{id}/dismiss | Scoped to user |
| POST /api/anomalies/{id}/confirm | Scoped to user |

---

## H. Frontend Changes

### Auth Flow

1. Unauthenticated users redirected to /login
2. JWT stored in localStorage
3. Axios interceptor adds Authorization header
4. AuthContext provides user state globally
5. Navigation shows user name + logout button
6. 401 responses redirect to login

### Transaction Editing

1. Edit icon on each TransactionRow
2. Modal with category dropdown, description, amount fields
3. Save calls PUT /api/transactions/{id}
4. Delete with confirmation dialog
5. Optimistic UI update

### Search and Filters

1. Search input (text search on description)
2. Date range picker (start/end date inputs)
3. Dynamic category dropdown from GET /api/categories
4. Sort by clicking column headers

### Mobile Responsive

1. Hamburger menu for Navigation
2. WhatIfSimulator: single column on mobile
3. PendingReceipts: single column form on mobile
4. Transactions table: horizontal scroll preserved

### Error Handling

1. ErrorBoundary wraps entire app
2. Toast component for success/error notifications
3. All API errors show toast + log to console
4. Loading states on all async operations

---

## I. Testing Strategy

### Backend Tests

| Area | Tests | Framework |
|------|-------|-----------|
| Auth | Register, login, JWT validation, expired token, wrong password | pytest |
| User Scoping | Verify user A cannot see user B data | pytest |
| Transaction CRUD | Create, read, update, delete, search, filter | pytest |
| Agent | Verify agent queries are user-scoped | pytest |
| Budgets | CRUD with user scoping | pytest |
| Migrations | Alembic upgrade/downgrade | pytest |

Target: 80+ tests (56 existing + 25+ new)

### Frontend Tests

| Area | Tests | Framework |
|------|-------|-----------|
| Auth | Login form, register form, protected route redirect | Vitest |
| Transactions | List rendering, search, filter, edit, delete | Vitest |
| Budgets | CRUD operations, progress bar | Vitest |
| Agent | Chat interface, message rendering | Vitest |
| Dashboard | Data display, chart rendering | Vitest |

Target: 30+ frontend tests

---

## J. Security Considerations

### Authentication Security

- Passwords hashed with bcrypt (passlib)
- JWT tokens with configurable expiry (default 24h)
- Secret key from environment variable, never hardcoded
- No password in any response schema
- Email uniqueness enforced at DB level

### Authorization Security

- Every endpoint requires valid JWT
- Every database query filtered by user_id
- Agent tools inject user_id from token, not from request body
- Receipt files stored in user-scoped directories (future: user_id/uuid.ext)

### Input Validation

- Pydantic schemas validate all inputs
- Transaction type restricted to debit/credit (add Literal type)
- Category validated against known list
- Amount must be positive
- Date format validated

### API Security

- CORS restricted to known origins only
- Rate limiting on all endpoints (not just agent)
- Security headers (X-Content-Type-Options, X-Frame-Options, CSP)
- No sensitive data in logs
- Request ID tracking for debugging

---

## K. Migration/Rollback Strategy

### Phase 2A-2B (Auth + User Scoping)

1. Create users table (new table, no risk)
2. Add user_id columns as NULLABLE (no data loss)
3. Create default user, backfill all existing rows
4. Make user_id NOT NULL after backfill
5. Add foreign key constraints

**Rollback:** Drop user_id columns, drop users table. Data is preserved.

### Phase 2C (Alembic)

1. Set up Alembic with current state as baseline
2. Generate initial migration
3. Remove manual ALTER TABLE from main.py
4. Test upgrade/downgrade cycle

**Rollback:** Revert to manual ALTER TABLE approach.

### Data Safety

- All migrations are additive (no data deletion)
- Backup finance.db before any migration
- Backfill uses default user_id, existing data preserved
- Foreign keys are added after data exists

---

## L. Risks and Tradeoffs

### High Risk

| Risk | Mitigation |
|------|------------|
| Breaking all existing data with user_id migration | Nullable columns first, backfill before NOT NULL |
| JWT secret key leaked | Generate strong random key, document rotation |
| Agent prompt injection after auth | Still a risk; limit tool output size, validate tool args |

### Medium Risk

| Risk | Mitigation |
|------|------------|
| Performance with user_id indexes | Add indexes incrementally, measure query times |
| Frontend auth state management complexity | Keep it simple: Context + localStorage, no Redux |
| Alembic migration conflicts | One person merges migrations, clear commit messages |

### Low Risk

| Risk | Mitigation |
|------|------------|
| Bcrypt slow on login | Acceptable for security; cache if needed |
| Token expiry too short/long | Default 24h, configurable |
| Mobile responsive CSS issues | Test on real devices, use CSS Grid/Flexbox |

### Tradeoffs Accepted

- JWT over sessions: Simpler, stateless, works with SPA. No server-side session store needed.
- SQLite over PostgreSQL: Keep SQLite for now, make PostgreSQL optional via config. Avoid premature infrastructure complexity.
- bcrypt over argon2: bcrypt is simpler and well-supported by passlib. argon2 is better but adds complexity.
- In-memory rate limiter: Acceptable for single-instance. Redis-based for production multi-instance is future work.

---

## M. Definition of Done for Phase 2

### Must-Have (all required to consider Phase 2 complete)

- [ ] User can register and login
- [ ] JWT authentication on every endpoint
- [ ] user_id on all database models
- [ ] All queries filtered by authenticated user
- [ ] Agent tools are user-scoped
- [ ] Alembic migrations replace manual ALTER TABLE
- [ ] Transaction editing (update category, description, amount)
- [ ] Transaction deletion
- [ ] Category correction
- [ ] Frontend login/register pages
- [ ] Protected routes in frontend
- [ ] Frontend tests passing (30+ tests)
- [ ] Backend tests passing (80+ tests)
- [ ] Health check endpoint

### Nice-to-Have (at least 5 of 15)

- [ ] Transaction search
- [ ] Date range filters
- [ ] Column sorting
- [ ] Dynamic category list
- [ ] Mobile responsive navigation
- [ ] Toast notifications
- [ ] Error boundaries
- [ ] WhatIfSimulator mobile fix
- [ ] Dashboard date range controls
- [ ] PostgreSQL config option
- [ ] Structured logging
- [ ] Docker setup
- [ ] Security headers
- [ ] Global rate limiting
- [ ] Export/download
