# Pratvim Subscriptions and Billing Implementation Plan

**Product:** Pratvim Mobile App  
**Primary users:** Parents and kids  
**Backend:** `pratvim-backend`  
**Mobile app:** `pratvim-mobile-app`  
**Admin module:** `pratvim-admin -> Billing`  
**Last updated:** 2026-07-01

This document reflects the current backend, admin, and mobile app flows. It also defines the next implementation steps needed to move billing from demo/local behavior to a backend-owned subscription flow.

---

## 1. Current Implementation Snapshot

### 1.1 Backend state

The backend already has a subscription foundation:

- `billing_plans` table exists.
- `subscriptions` table exists.
- Parent registration creates a starter subscription row.
- Billing API exposes plans, current subscription, checkout-session demo, subscription update, and cancellation.
- Admin API can list billing plans and assign a plan to a parent.
- Dashboard API exposes plan and child-limit information.
- Child profile creation enforces the current plan's child limit.

The backend does not yet have:

- Real payment provider integration.
- Store product mapping.
- Webhook handling.
- Credit wallets.
- Credit packs.
- Usage event billing.
- Read-only mode after credit exhaustion.
- Plan-copy fields for full mobile card rendering.
- Mobile payment confirmation tied to a provider transaction.

### 1.2 Mobile app state

The mobile app currently has a payment UI, but it is still local/prototype behavior:

- `PaymentPlansScreen` renders hardcoded plans: `monthly`, `quarterly`, `annual`.
- `PaymentPlansScreen` updates local app state with `subscription/select`.
- `PaymentConfirmationScreen` explicitly says no backend or gateway was called.
- Mobile subscription state uses `planId: monthly | quarterly | annual`, which does not match backend plan codes.
- Mobile does not call `/billing/plans`, `/billing/subscription`, or checkout aliases yet.

### 1.3 Admin state

The admin app currently supports limited billing operations:

- Admin can fetch active billing plans from `/admin/billing/plans`.
- Admin user detail view can change a parent plan with `/admin/users/{parent_user_id}/subscription`.
- Admin billing view shows a selected subscription summary.

Admin does not yet support:

- Creating or editing billing plans from the UI.
- Managing free plan settings.
- Managing credit packs.
- Viewing family wallets.
- Viewing usage events or credit ledger.
- Payment provider sync.
- Invoice browsing.

---

## 2. Current Data Model

### 2.1 `billing_plans`

Current schema:

```sql
CREATE TABLE IF NOT EXISTS billing_plans (
  code TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  monthly_price_inr INTEGER NOT NULL DEFAULT 0,
  allowed_child_count INTEGER NOT NULL CHECK (allowed_child_count >= 1),
  features_json JSONB NOT NULL DEFAULT '[]',
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Seeded plan codes:

| Plan code | Title | Monthly price INR | Child limit |
|---|---|---:|---:|
| `starter` | Starter - 1 child plan | 299 | 1 |
| `family_plus` | Family Plus - 2 child plan | 599 | 2 |
| `family_max` | Family Max - 4 child plan | 999 | 4 |

Important mismatch:

- The old product plan language used `Free`, `Basic`, `Plus`, and `Family`.
- The current backend uses `starter`, `family_plus`, and `family_max`.
- The mobile app uses `monthly`, `quarterly`, and `annual`.

Decision:

```text
Backend plan codes must be the source of truth.
Mobile must stop using monthly/quarterly/annual as plan IDs.
Billing cycle can still be monthly/quarterly/annual, but it is separate from plan_code.
```

### 2.2 `subscriptions`

Current schema:

```sql
CREATE TABLE IF NOT EXISTS subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
  plan_code TEXT NOT NULL,
  billing_cycle TEXT NOT NULL,
  status TEXT NOT NULL,
  starts_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ends_at TIMESTAMPTZ,
  auto_renew BOOLEAN NOT NULL DEFAULT true,
  payment_provider TEXT,
  provider_customer_id TEXT,
  provider_subscription_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Current behavior:

- Parent registration inserts `starter`, `trial`, `active`, `auto_renew=false`, `payment_provider='trial'`.
- Demo checkout inserts a new active subscription with `payment_provider='demo'`.
- Admin plan change inserts a new active subscription with `payment_provider='admin'`.
- Cancellation updates the latest subscription row to `status='canceled'` and `auto_renew=false`.
- Dashboard and child-limit code use the latest active subscription, falling back to `starter`.

---

## 3. Current Backend API Contracts

All backend routes are under `/api/v1`.

### 3.1 Parent billing routes

| Route | Method | Current behavior |
|---|---|---|
| `/billing/plans` | GET | Returns active `billing_plans` ordered by child limit |
| `/billing/subscription` | GET | Returns latest subscription, or fallback starter shape if none exists |
| `/billing/checkout-session` | POST | Demo only: inserts active subscription and returns demo redirect URL |
| `/billing/subscription` | PATCH | Inserts active subscription row and sends billing active email |
| `/billing/subscription/cancel` | POST | Cancels latest subscription row and sends cancellation email |

Current checkout payload:

```ts
type CheckoutPayload = {
  plan_code: string;       // default "family_plus"
  billing_cycle: string;   // default "monthly"
};
```

### 3.2 Mobile alias routes

The backend also exposes mobile-friendly aliases:

| Route | Method | Maps to |
|---|---|---|
| `/plans/family` | GET | `/billing/plans` |
| `/subscriptions/current` | GET | `/billing/subscription` |
| `/checkout/session` | POST | `/billing/checkout-session` |
| `/checkout/confirm` | POST | Demo confirmation wrapper around current subscription |

Mobile should use these aliases if the rest of the mobile API convention prefers them. Otherwise, it can call the `/billing/*` routes directly.

### 3.3 Admin billing routes

| Route | Method | Current behavior |
|---|---|---|
| `/admin/billing/plans` | GET | Returns active billing plans |
| `/admin/users/{parent_user_id}/subscription` | POST | Inserts admin-managed active subscription for parent |

### 3.4 Dashboard and entitlement routes

`/dashboard/overview` currently returns:

```json
{
  "child_count": 1,
  "current_plan": "starter",
  "current_plan_title": "Starter - 1 child plan",
  "allowed_child_count": 1,
  "can_add_child": false,
  "weekly_sessions": 0,
  "pending_alerts": 0,
  "top_topics": [],
  "recent_activity": []
}
```

Child profile creation enforces child limit:

```text
POST /children
if active child count >= billing_plans.allowed_child_count:
  return 403 ENTITLEMENT_EXCEEDED
```

Current error is generic. It should be expanded for mobile UX.

---

## 4. Current Mobile Flow and Required Changes

### 4.1 Current mobile payment flow

Current screen flow:

```text
Parent dashboard or billing CTA
  -> PaymentPlansScreen
  -> local plan selection: monthly / quarterly / annual
  -> local modal "Secure checkout"
  -> dispatch(subscription/select)
  -> PaymentConfirmationScreen
```

Current limitations:

- No backend plan fetch.
- No current subscription fetch.
- No checkout-session request.
- No confirm request.
- Local `subscription` state does not match backend subscriptions.
- Confirmation screen text says the app is offline-only.

### 4.2 Target mobile payment flow

Mobile should become backend-owned:

```text
PaymentPlansScreen loads plans from backend
  GET /plans/family or /billing/plans

PaymentPlansScreen loads current subscription
  GET /subscriptions/current or /billing/subscription

Parent selects a backend plan_code and billing_cycle
  POST /checkout/session

If demo checkout:
  show confirmation from backend response
  POST /checkout/confirm

If real provider checkout:
  open provider checkout or native in-app purchase flow
  confirm with backend after provider success

After confirmation:
  refresh current subscription
  refresh dashboard overview
  navigate to PaymentConfirmationScreen
```

### 4.3 Mobile state model changes

Replace local-only state:

```ts
type Subscription = {
  planId: 'monthly' | 'quarterly' | 'annual';
  status: 'Active' | 'Trial' | 'Expired';
  validUntil: string;
  tokensLeft: number;
  daysLeft: number;
};
```

With backend-aligned state:

```ts
type BillingPlan = {
  code: string;
  name?: string;
  title: string;
  monthly_price_inr: number;
  allowed_child_count: number;
  features: string[];
  active: boolean;
};

type CurrentSubscription = {
  parent_user_id: string;
  plan_code: string;
  billing_cycle: string;
  status: string;
  auto_renew: boolean;
  starts_at?: string;
  ends_at?: string;
  updated_at?: string;
};
```

Recommended mobile app state:

```ts
type BillingState = {
  plans: BillingPlan[];
  currentSubscription?: CurrentSubscription;
  selectedPlanCode?: string;
  selectedBillingCycle: 'monthly' | 'quarterly' | 'annual';
  loading: boolean;
  error?: string;
};
```

### 4.4 Payment screen copy changes

Remove this text after backend integration:

```text
Secure prototype checkout. No backend payment gateway is connected.
Payment method: UPI / Card placeholder. This is UI only.
The app remains offline-only in this prototype. No backend or gateway was called.
```

Replace with state-aware copy:

```text
Plan changes are managed securely by Pratvim billing.
Your child profile limit updates after confirmation.
```

For demo checkout only:

```text
Demo checkout is enabled in this environment. No live payment will be charged.
```

---

## 5. Admin Flow

### 5.1 Current admin flow

Admin user detail page:

```text
Admin -> Users -> Parent -> Billing panel
  select plan from active billing plans
  submit Update plan
  POST /admin/users/{parent_id}/subscription
  backend inserts active subscription with payment_provider='admin'
  backend sends billing_family_plan_active_parent email
```

Admin Billing page:

```text
Admin -> Billing
  displays one subscription summary from loaded parent users
```

### 5.2 Required admin improvements

Admin Billing should support:

1. Plan management:
   - Create plan.
   - Edit title.
   - Edit price.
   - Edit allowed child count.
   - Edit feature bullets.
   - Activate/deactivate plan.

2. Subscription management:
   - Search parent subscriptions.
   - View latest subscription per parent.
   - View subscription history.
   - Change plan through controlled support action.
   - Cancel or resume subscription.

3. Provider state:
   - Show payment provider.
   - Show provider customer ID.
   - Show provider subscription ID.
   - Show webhook status when provider integration exists.

Not implemented yet:

- Free credit settings.
- Credit packs.
- Rate cards.
- Usage ledger.
- Invoices.
- Wallet adjustments.

---

## 6. Entitlements and Limits

### 6.1 Currently implemented

Only child profile limit is implemented.

Current entitlement source:

```text
effective plan = latest active subscription, else starter
child limit = billing_plans.allowed_child_count
```

Current enforcement points:

- `/dashboard/overview` returns `can_add_child`.
- `POST /children` blocks creating a child if active child count is at or above plan limit.

### 6.2 Required response shape for child limit errors

Current mobile needs a better error payload for plan upgrade CTAs.

Recommended error payload:

```json
{
  "error_code": "ENTITLEMENT_EXCEEDED",
  "message": "Current plan child profile limit reached.",
  "details": {
    "limit_type": "kid_count",
    "current_plan": "starter",
    "active_kids_count": 1,
    "max_kids_allowed": 1,
    "can_add_child": false,
    "upgrade_cta": "Upgrade to add another child profile."
  }
}
```

### 6.3 Not implemented yet: credit usage limits

The previous plan described monthly credits, add-on credits, credit deduction, and read-only mode after exhaustion. Those are not implemented in the current backend or mobile app.

Do not represent this as current behavior.

Future entitlement fields:

```ts
type PlanLimitState = {
  usage_limit_reached: boolean;
  kid_limit_reached: boolean;
  message_write_mode: 'READ_WRITE' | 'READ_ONLY';
  can_chat: boolean;
  can_read_history: boolean;
  can_add_child: boolean;
  active_kids_count: number;
  max_kids_allowed: number;
};
```

Future rule:

```text
Billing can block normal chat generation, but it must never disable safety guardrails, safety-critical responses, alerts, or history reads.
```

---

## 7. Backend Implementation Phases

### Phase 1 - Align mobile with current backend

Goal: make mobile payment screens use existing backend subscriptions.

Tasks:

1. Add mobile billing API client:
   - `getFamilyPlans()`
   - `getCurrentSubscription()`
   - `createCheckoutSession(planCode, billingCycle)`
   - `confirmCheckout()`

2. Replace hardcoded mobile plan cards with backend plans:
   - `starter`
   - `family_plus`
   - `family_max`

3. Replace `subscription.planId` local state with backend `plan_code`.

4. On payment confirmation:
   - call backend checkout session,
   - call confirm if demo mode,
   - refresh subscription,
   - refresh parent dashboard entitlement state.

5. Update copy to remove "UI only" and "offline-only" language.

6. Handle `ENTITLEMENT_EXCEEDED` from child creation:
   - show upgrade CTA,
   - navigate parent to payment plans.

### Phase 2 - Improve backend plan contracts

Goal: make backend plan records sufficient to render mobile plan cards without hardcoded content.

Add fields to `billing_plans`:

```sql
ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS subtitle TEXT;
ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS badge_text TEXT;
ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS cta_text TEXT;
ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS footer_note TEXT;
ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS price_display_text TEXT;
ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
```

Then update:

- `/billing/plans`
- `/plans/family`
- `/admin/billing/plans`
- admin plan management UI

### Phase 3 - Real checkout provider integration

Goal: replace demo checkout with actual billing provider or app store products.

Backend tasks:

1. Add provider product mapping table.
2. Add checkout session creation through selected provider.
3. Add webhook endpoints.
4. Verify provider signatures.
5. Store provider customer/subscription IDs.
6. Update subscription status from webhooks, not client trust.
7. Add idempotency keys.

Mobile tasks:

1. Use provider redirect URL or native in-app purchase SDK.
2. Return to confirmation screen only after backend confirms current subscription.
3. Show pending state if provider webhook has not arrived.

### Phase 4 - Credit wallet and read-only chat

Goal: implement monthly credits and optional add-on credits.

New backend concepts:

- billing periods,
- credit buckets,
- usage events,
- immutable credit ledger,
- credit reservation/release,
- credit packs,
- read-only normal chat mode.

Important safety rule:

```text
Safety classifier, safety-critical responses, and parent alerts must still run when normal chat credits are exhausted.
```

Suggested tables:

- `billing_credit_buckets`
- `billing_usage_events`
- `billing_credit_ledger`
- `billing_credit_packs`
- `billing_store_products`

Suggested backend enforcement:

```text
On child message:
  run guardrail classifier/safety path
  if safety-critical:
    return safe response even if normal credits are exhausted
  else:
    check wallet balance
    if balance insufficient:
      return read-only/limit response
    reserve credits
    generate answer
    finalize debit from measured usage
```

---

## 8. Mobile Integration Details

### 8.1 API client to add

Suggested file:

```text
pratvim-mobile-app/src/features/payments/data/billingApi.ts
```

Suggested functions:

```ts
export function getFamilyPlans(token: string): Promise<BillingPlan[]>;
export function getCurrentSubscription(token: string): Promise<CurrentSubscription>;
export function createCheckoutSession(
  payload: { plan_code: string; billing_cycle: string },
  token: string
): Promise<CheckoutSession>;
export function confirmCheckout(token: string): Promise<CheckoutConfirmation>;
```

### 8.2 PaymentPlansScreen changes

Required behavior:

1. Read `state.auth.accessToken`.
2. Fetch plans and current subscription on mount.
3. Display backend plan title, price, child count, and features.
4. Default selected plan to current subscription plan.
5. Disable current plan CTA or show "Current plan".
6. On submit, call checkout session.
7. In demo mode, call confirm and navigate to confirmation.
8. In real provider mode, open provider checkout.

### 8.3 PaymentConfirmationScreen changes

Required behavior:

1. Accept `planCode`, not `monthly | quarterly | annual`.
2. Display confirmed subscription from backend state.
3. Remove offline-only copy.
4. Offer "Return to Parent Home".
5. Optionally offer "Add child profile" if `can_add_child` is true.

### 8.4 Parent dashboard and child creation

Parent dashboard should use backend dashboard fields:

- `current_plan`
- `current_plan_title`
- `allowed_child_count`
- `can_add_child`

When child creation returns `ENTITLEMENT_EXCEEDED`, mobile should:

1. show the backend message,
2. explain the current child limit,
3. offer an upgrade button,
4. navigate to `PaymentPlans`.

---

## 9. Admin Implementation Details

### 9.1 Plan management API to add

Recommended admin routes:

| Route | Method | Purpose |
|---|---|---|
| `/admin/billing/plans` | POST | Create plan |
| `/admin/billing/plans/{code}` | PATCH | Update plan |
| `/admin/billing/plans/{code}/deactivate` | POST | Deactivate plan |
| `/admin/billing/plans/{code}/activate` | POST | Activate plan |

### 9.2 Subscription management API to add

Recommended admin routes:

| Route | Method | Purpose |
|---|---|---|
| `/admin/billing/subscriptions` | GET | Search/list subscriptions |
| `/admin/billing/subscriptions/{parent_user_id}` | GET | Subscription history |
| `/admin/billing/subscriptions/{parent_user_id}/cancel` | POST | Support cancellation |
| `/admin/billing/subscriptions/{parent_user_id}/resume` | POST | Support resume |

Current support route:

```text
POST /admin/users/{parent_user_id}/subscription
```

Keep it for parent detail quick action, but move broader billing operations under `/admin/billing/*`.

---

## 10. Acceptance Criteria

### 10.1 Current backend integration acceptance

Mobile billing is considered integrated with the current backend when:

- PaymentPlansScreen fetches plans from backend.
- PaymentPlansScreen displays backend plan codes and copy.
- Current subscription is fetched from backend.
- Selecting a plan calls backend checkout session.
- Demo checkout creates/updates subscription on backend.
- Confirmation screen no longer says offline-only.
- Parent dashboard reflects updated child limit after upgrade.
- Child creation limit errors navigate to upgrade flow.

### 10.2 Admin acceptance

Admin billing is considered minimally useful when:

- Admin can list plans.
- Admin can assign a plan to a parent.
- Admin can see latest subscription on parent detail.
- Admin can see child limit and subscription status.
- Backend sends billing update email after admin plan change.

This minimum is mostly implemented today.

### 10.3 Future credit-wallet acceptance

Credit wallet is considered implemented only when:

- Every AI chat request produces a usage event.
- Credits are debited in an immutable ledger.
- Current balance is returned to mobile.
- Normal chat is blocked when credits are exhausted.
- Old history remains readable.
- Safety-critical responses still run.
- Admin can view and adjust wallet state.

This is not implemented today.

---

## 11. Immediate Next Steps

Recommended implementation order:

1. Add mobile billing API client.
2. Replace hardcoded mobile plan IDs with backend `plan_code`.
3. Wire PaymentPlansScreen to `/plans/family` and `/subscriptions/current`.
4. Wire Review and Pay to `/checkout/session` and `/checkout/confirm`.
5. Update PaymentConfirmationScreen copy and route params.
6. Refresh dashboard overview after subscription changes.
7. Improve `ENTITLEMENT_EXCEEDED` details for child limit failures.
8. Add backend plan display fields for mobile copy.
9. Add admin plan create/edit UI.
10. Plan provider/webhook integration separately after demo checkout is stable.

---

## 12. Decisions

1. Backend plan codes are canonical.
2. Billing cycle is separate from plan code.
3. Current paid-provider behavior is demo only.
4. Child-limit entitlement is currently implemented and enforced.
5. Credit usage limits, add-on credits, and read-only chat are future work.
6. Safety and guardrails must remain independent from billing limits.
7. Mobile should not hardcode plan copy once backend plan display fields exist.

---

## 13. Complete Target Architecture

### 13.1 Ownership boundaries

Backend owns:

- plan catalog,
- current subscription state,
- effective entitlement,
- child profile limits,
- checkout session creation,
- payment provider verification,
- provider webhook reconciliation,
- future credit wallets and usage enforcement,
- audit trail for admin/support changes.

Mobile owns:

- presenting backend plan data,
- selecting a plan and billing cycle,
- launching checkout or in-app purchase UI,
- showing confirmation/pending/failure states,
- refreshing dashboard and subscription state after checkout,
- routing parent to billing when a child limit is reached.

Admin owns:

- plan catalog operations,
- subscription support operations,
- provider diagnostics,
- future credit ledger adjustments,
- billing reports.

Payment provider owns:

- payment method collection,
- subscription renewals,
- failed payment events,
- invoices/receipts,
- external payment status.

Important rule:

```text
Mobile must never be trusted as proof of payment.
Only backend-created checkout sessions and verified provider webhooks can create or renew paid entitlement.
```

### 13.2 Final runtime flow

```text
Parent opens PaymentPlansScreen
  -> mobile fetches backend plan catalog
  -> mobile fetches current subscription
  -> parent chooses plan_code + billing_cycle
  -> mobile requests checkout session
  -> backend creates provider checkout/in-app purchase intent
  -> parent completes provider payment
  -> provider sends webhook to backend
  -> backend verifies webhook and updates subscription
  -> mobile polls or confirms checkout status
  -> mobile refreshes subscription + dashboard
```

### 13.3 Effective entitlement evaluation

Create one backend helper used by dashboard, child creation, chat, and billing UI:

```python
def evaluate_entitlement(parent_user_id: str) -> EffectiveEntitlement:
    latest_active_subscription = find_latest_active_subscription(parent_user_id)
    if latest_active_subscription:
        plan = find_plan(latest_active_subscription.plan_code)
        account_mode = "SUBSCRIPTION_ACTIVE"
    else:
        plan = find_default_plan()
        account_mode = "FREE_ACTIVE"

    child_count = count_active_children(parent_user_id)
    wallet = find_current_wallet(parent_user_id, plan.code)

    return {
        "account_mode": account_mode,
        "effective_plan": plan,
        "subscription": latest_active_subscription,
        "child_count": child_count,
        "can_add_child": child_count < plan.allowed_child_count,
        "kid_limit_reached": child_count >= plan.allowed_child_count,
        "usage_limit_reached": wallet.limit_reached if wallet else False,
        "message_write_mode": "READ_ONLY" if wallet and wallet.limit_reached else "READ_WRITE",
        "can_chat": not wallet.limit_reached if wallet else True,
        "can_read_history": True,
    }
```

In the current codebase only the child-limit portion exists. The complete implementation should consolidate that logic instead of duplicating subscription queries in dashboard, children, and billing routers.

---

## 14. Complete Database Plan

### 14.1 Upgrade `billing_plans`

Current table is enough for child limit, but not enough for mobile-owned display or real products.

Target columns:

```sql
ALTER TABLE billing_plans
  ADD COLUMN IF NOT EXISTS plan_type TEXT NOT NULL DEFAULT 'paid',
  ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'INR',
  ADD COLUMN IF NOT EXISTS subtitle TEXT,
  ADD COLUMN IF NOT EXISTS description TEXT,
  ADD COLUMN IF NOT EXISTS badge_text TEXT,
  ADD COLUMN IF NOT EXISTS cta_text TEXT,
  ADD COLUMN IF NOT EXISTS footer_note TEXT,
  ADD COLUMN IF NOT EXISTS price_display_text TEXT,
  ADD COLUMN IF NOT EXISTS child_limit_display_text TEXT,
  ADD COLUMN IF NOT EXISTS included_monthly_credits BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS voice_enabled BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS addon_credits_allowed BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS is_default_free BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
```

Recommended plan definitions for MVP:

| Code | Type | Cycle | Price | Kids | Credits | Notes |
|---|---|---|---:|---:|---:|---|
| `starter` | free/trial | monthly | 0 or 299 display depending business decision | 1 | 0 until wallet phase | Current default |
| `family_plus` | paid | monthly | 599 | 2 | 0 until wallet phase | Active paid upgrade |
| `family_max` | paid | monthly | 999 | 4 | 0 until wallet phase | Highest child limit |

Business decision needed:

```text
Is starter truly free, or is it a paid starter plan?
```

The current database seeds `starter` at `299`, while earlier product rules described a default free monthly plan. Choose one before provider integration.

### 14.2 Add store product mapping

Required for App Store, Play Store, Stripe, Razorpay, or another provider.

```sql
CREATE TABLE IF NOT EXISTS billing_store_products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  internal_product_code TEXT NOT NULL,
  product_type TEXT NOT NULL CHECK (product_type IN ('subscription', 'consumable')),
  provider TEXT NOT NULL,
  provider_product_id TEXT NOT NULL,
  provider_price_id TEXT,
  platform TEXT NOT NULL DEFAULT 'server',
  plan_code TEXT REFERENCES billing_plans(code),
  billing_cycle TEXT,
  active BOOLEAN NOT NULL DEFAULT true,
  metadata_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_product_id, provider_price_id)
);
```

### 14.3 Upgrade `subscriptions`

Current `subscriptions` is usable, but needs provider lifecycle fields.

```sql
ALTER TABLE subscriptions
  ADD COLUMN IF NOT EXISTS provider_status TEXT,
  ADD COLUMN IF NOT EXISTS current_period_start TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS canceled_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS provider_payload_json JSONB NOT NULL DEFAULT '{}';
```

Recommended statuses:

```text
trialing
active
past_due
canceled
expired
incomplete
grace
blocked
```

### 14.4 Add checkout sessions

```sql
CREATE TABLE IF NOT EXISTS billing_checkout_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
  plan_code TEXT NOT NULL REFERENCES billing_plans(code),
  billing_cycle TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_checkout_session_id TEXT,
  provider_payment_intent_id TEXT,
  status TEXT NOT NULL DEFAULT 'created',
  redirect_url TEXT,
  idempotency_key TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (idempotency_key)
);
```

### 14.5 Add provider webhook event log

```sql
CREATE TABLE IF NOT EXISTS billing_webhook_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider TEXT NOT NULL,
  provider_event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  signature_verified BOOLEAN NOT NULL DEFAULT false,
  processing_status TEXT NOT NULL DEFAULT 'received',
  payload_json JSONB NOT NULL,
  error_text TEXT,
  processed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_event_id)
);
```

### 14.6 Future credit wallet tables

Only add these when usage metering is ready.

```sql
CREATE TABLE IF NOT EXISTS billing_credit_buckets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
  source_type TEXT NOT NULL,
  source_id TEXT,
  credits_granted BIGINT NOT NULL,
  credits_remaining BIGINT NOT NULL,
  starts_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active',
  metadata_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS billing_usage_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
  child_profile_id UUID REFERENCES child_profiles(id) ON DELETE SET NULL,
  chat_message_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
  usage_type TEXT NOT NULL,
  units BIGINT NOT NULL,
  credits_charged BIGINT NOT NULL DEFAULT 0,
  safety_critical BOOLEAN NOT NULL DEFAULT false,
  metadata_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS billing_credit_ledger (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
  bucket_id UUID REFERENCES billing_credit_buckets(id) ON DELETE SET NULL,
  usage_event_id UUID REFERENCES billing_usage_events(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  amount_delta BIGINT NOT NULL,
  balance_after BIGINT NOT NULL,
  reason_code TEXT,
  admin_user_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
  idempotency_key TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (idempotency_key)
);
```

---

## 15. Complete Backend API Plan

### 15.1 Public parent billing APIs

#### `GET /api/v1/billing/plans`

Return backend-owned plan cards.

Response:

```json
{
  "data": [
    {
      "code": "family_plus",
      "title": "Family Plus",
      "subtitle": "For two children",
      "description": "Protected learning with parent controls.",
      "monthly_price_inr": 599,
      "currency": "INR",
      "price_display_text": "₹599 / month",
      "allowed_child_count": 2,
      "child_limit_display_text": "Up to 2 child profiles",
      "features": ["alerts", "2FA", "summaries"],
      "badge_text": "Popular",
      "cta_text": "Choose Plus",
      "footer_note": "Renews monthly. Cancel anytime.",
      "active": true
    }
  ]
}
```

#### `GET /api/v1/billing/subscription`

Return latest subscription plus effective entitlement.

Response:

```json
{
  "data": {
    "subscription": {
      "parent_user_id": "uuid",
      "plan_code": "family_plus",
      "billing_cycle": "monthly",
      "status": "active",
      "auto_renew": true,
      "starts_at": "2026-07-01T00:00:00Z",
      "ends_at": "2026-08-01T00:00:00Z",
      "payment_provider": "demo"
    },
    "entitlement": {
      "account_mode": "SUBSCRIPTION_ACTIVE",
      "effective_plan_code": "family_plus",
      "active_kids_count": 1,
      "max_kids_allowed": 2,
      "kid_limit_reached": false,
      "can_add_child": true,
      "usage_limit_reached": false,
      "message_write_mode": "READ_WRITE",
      "can_chat": true,
      "can_read_history": true
    }
  }
}
```

#### `POST /api/v1/billing/checkout-session`

Request:

```json
{
  "plan_code": "family_plus",
  "billing_cycle": "monthly",
  "provider": "demo",
  "platform": "ios",
  "idempotency_key": "client-generated-uuid"
}
```

Response:

```json
{
  "data": {
    "checkout_session_id": "uuid",
    "provider": "demo",
    "status": "created",
    "plan_code": "family_plus",
    "billing_cycle": "monthly",
    "redirect_url": "https://billing.example/pratvim/demo",
    "demo_mode": true
  },
  "message": "Checkout created."
}
```

#### `POST /api/v1/billing/checkout-session/{id}/confirm`

For demo checkout this can immediately activate. For real providers this should validate provider state.

Response:

```json
{
  "data": {
    "confirmed": true,
    "subscription": {},
    "entitlement": {}
  }
}
```

### 15.2 Admin APIs

Add or complete these routes:

| Route | Method | Purpose |
|---|---|---|
| `/admin/billing/plans` | GET | List plans |
| `/admin/billing/plans` | POST | Create plan |
| `/admin/billing/plans/{code}` | PATCH | Update plan |
| `/admin/billing/plans/{code}/activate` | POST | Activate plan |
| `/admin/billing/plans/{code}/deactivate` | POST | Deactivate plan |
| `/admin/billing/subscriptions` | GET | Search subscriptions |
| `/admin/billing/subscriptions/{parent_user_id}` | GET | Subscription history |
| `/admin/billing/subscriptions/{parent_user_id}/change-plan` | POST | Support plan override |
| `/admin/billing/subscriptions/{parent_user_id}/cancel` | POST | Support cancellation |
| `/admin/billing/webhooks` | GET | Webhook event log |
| `/admin/billing/checkout-sessions` | GET | Checkout session diagnostics |

Admin support actions must write an audit record. If no dedicated audit table exists, add one:

```sql
CREATE TABLE IF NOT EXISTS admin_audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_user_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
  action_type TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  reason_text TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 15.3 Provider webhook API

Add provider-specific endpoint:

```text
POST /api/v1/billing/webhooks/{provider}
```

Webhook handling rules:

1. Verify signature before processing.
2. Store event in `billing_webhook_events`.
3. Enforce idempotency by provider event ID.
4. Map provider product/price ID to internal plan.
5. Update `subscriptions`.
6. Recompute entitlement.
7. Send transactional email if subscription became active/canceled/past_due.

Provider event mapping:

| Provider event | Internal action |
|---|---|
| checkout completed | create or activate subscription |
| subscription renewed | extend current period |
| payment failed | set `past_due` or `grace` |
| subscription canceled | set `canceled` |
| subscription expired | set `expired`, fallback to starter/free |
| refund | mark metadata, optionally add ledger reversal in future wallet phase |

---

## 16. Complete Mobile Implementation Plan

### 16.1 Files to add/update

Add:

```text
src/features/payments/data/billingApi.ts
src/features/payments/presentation/viewmodels/useBillingViewModel.ts
```

Update:

```text
src/app/state/types.ts
src/app/state/appReducer.ts
src/features/payments/presentation/screens/PaymentPlansScreen.tsx
src/features/payments/presentation/screens/PaymentConfirmationScreen.tsx
src/features/parent/presentation/viewmodels/useParentViewModel.ts
src/features/parent/presentation/screens/ParentDashboardScreen.tsx
src/features/parent/presentation/screens/CreateChildProfileScreen.tsx
```

### 16.2 Mobile API client

```ts
export type BillingPlan = {
  code: string;
  title: string;
  subtitle?: string;
  description?: string;
  monthly_price_inr: number;
  price_display_text?: string;
  allowed_child_count: number;
  child_limit_display_text?: string;
  features: string[];
  badge_text?: string;
  cta_text?: string;
  footer_note?: string;
  active: boolean;
};

export type CurrentSubscriptionResponse = {
  subscription: {
    parent_user_id: string;
    plan_code: string;
    billing_cycle: string;
    status: string;
    auto_renew: boolean;
    starts_at?: string;
    ends_at?: string;
    payment_provider?: string;
  };
  entitlement: {
    account_mode: string;
    effective_plan_code: string;
    active_kids_count: number;
    max_kids_allowed: number;
    kid_limit_reached: boolean;
    can_add_child: boolean;
    usage_limit_reached: boolean;
    message_write_mode: 'READ_WRITE' | 'READ_ONLY';
    can_chat: boolean;
    can_read_history: boolean;
  };
};
```

### 16.3 PaymentPlansScreen required behavior

States:

- loading plans,
- loading current subscription,
- selecting plan,
- creating checkout,
- checkout failed,
- checkout pending,
- checkout confirmed.

Rendering rules:

- Current plan gets "Current plan" marker.
- Plans unavailable because they are inactive are hidden.
- CTA text comes from backend if available.
- Feature bullets come from backend.
- Price display comes from backend.
- Child limit display comes from backend or derived from `allowed_child_count`.

Submit behavior:

```ts
async function reviewAndPay() {
  const session = await createCheckoutSession({
    plan_code: selectedPlanCode,
    billing_cycle: selectedBillingCycle,
    provider: 'demo',
    platform: Platform.OS,
    idempotency_key: uuid()
  }, token);

  if (session.demo_mode) {
    const confirmation = await confirmCheckout(session.checkout_session_id, token);
    refreshSubscription();
    refreshDashboard();
    navigation.navigate('PaymentConfirmation', { planCode: selectedPlanCode });
    return;
  }

  openProviderCheckout(session.redirect_url);
}
```

### 16.4 PaymentConfirmationScreen required behavior

Route params:

```ts
type PaymentConfirmationParams = {
  planCode: string;
  checkoutSessionId?: string;
};
```

Screen should show:

- confirmed plan title,
- subscription status,
- child profile limit,
- next renewal/end date when present,
- CTA: Return to Parent Home,
- optional CTA: Add Child Profile when `can_add_child=true`.

### 16.5 Child limit mobile behavior

When `POST /children` returns `ENTITLEMENT_EXCEEDED`:

```text
Show bottom sheet/modal:
  title: "Your current plan allows 1 child profile"
  body: backend message
  primary CTA: "View plans"
  secondary CTA: "Not now"
```

Then navigate:

```ts
navigation.navigate('PaymentPlans', { reason: 'child_limit' });
```

---

## 17. Complete Admin Implementation Plan

### 17.1 Billing overview

Admin Billing overview should show:

- active subscriptions,
- trial/starter accounts,
- past_due accounts,
- canceled accounts,
- plan distribution,
- estimated MRR,
- child-limit exceeded attempts,
- checkout sessions created,
- checkout sessions failed,
- webhook failures.

### 17.2 Plans tab

Admin can:

- create a plan,
- edit plan copy,
- edit price,
- edit child limit,
- edit features,
- set active/inactive,
- reorder plans,
- preview mobile card.

Fields:

- `code`,
- `title`,
- `subtitle`,
- `description`,
- `monthly_price_inr`,
- `currency`,
- `price_display_text`,
- `allowed_child_count`,
- `features_json`,
- `badge_text`,
- `cta_text`,
- `footer_note`,
- `active`,
- `sort_order`.

### 17.3 Subscriptions tab

Admin can:

- search parent by email/name,
- view latest subscription,
- view history,
- change plan with reason,
- cancel/resume with reason,
- view provider IDs,
- view related webhook events.

All writes require:

- admin auth,
- reason text,
- audit event,
- transactional email where user-visible.

### 17.4 Provider diagnostics tab

Admin can inspect:

- checkout sessions,
- webhook events,
- signature verification status,
- processing errors,
- raw provider event type,
- linked subscription.

---

## 18. Credit Wallet Future Scope

Credit wallet is not required to complete backend-owned subscription checkout, but it should be planned as a separate milestone.

### 18.1 Credit deduction inputs

Credit costs can be based on:

- input tokens,
- output tokens,
- cached input tokens,
- voice input seconds,
- voice output seconds,
- STT units,
- TTS units.

Guardrail internals should be tracked for operational cost, but not charged separately to parent in MVP.

### 18.2 Read-only mode

Read-only mode is not an account status. It is an entitlement result:

```ts
message_write_mode: 'READ_WRITE' | 'READ_ONLY'
```

Allowed:

- read old chats,
- open saved responses,
- safety-critical messages,
- parent alerts.

Blocked:

- normal new child messages,
- normal voice chat,
- normal image/file upload when it would trigger generation.

### 18.3 Chat integration

When wallet exists, `/chat/message` must:

1. run safety classification,
2. allow safety-critical response even when credits are exhausted,
3. check credit balance before normal generation,
4. reserve estimated credits,
5. run generation,
6. debit actual credits,
7. release unused reservation,
8. write usage event and ledger entries.

---

## 19. Testing Plan

### 19.1 Backend unit tests

Add tests for:

- plan listing,
- current subscription fallback,
- checkout session idempotency,
- admin plan change,
- cancellation,
- child-limit entitlement,
- dashboard entitlement fields,
- webhook idempotency,
- provider event mapping.

### 19.2 Backend integration tests

Scenarios:

1. New parent gets starter/trial subscription.
2. Starter parent can create one child.
3. Starter parent cannot create second child.
4. Admin upgrades parent to `family_plus`.
5. Parent can now create second child.
6. Parent checkout upgrades to `family_max`.
7. Dashboard reflects four-child limit.
8. Cancellation falls back to starter/free behavior.
9. Duplicate webhook does not duplicate subscription rows.

### 19.3 Mobile tests

Manual and automated checks:

- plan loading skeleton,
- plan load error,
- current plan marker,
- backend checkout success,
- backend checkout failure,
- confirmation screen content,
- dashboard refresh after upgrade,
- child-limit modal and upgrade navigation.

### 19.4 Admin tests

Check:

- plans load,
- plan update validation,
- parent plan override,
- audit event creation,
- subscription status display,
- webhook diagnostics display.

---

## 20. Rollout Plan

### Step 1 - Demo backend integration

- Keep provider as `demo`.
- Mobile calls real backend endpoints.
- Remove local-only payment copy.
- Confirm dashboard and child-limit behavior.

### Step 2 - Admin plan management

- Add plan create/edit UI.
- Add audit trail.
- Keep checkout demo mode.

### Step 3 - Provider sandbox

- Add provider mapping and checkout sessions.
- Add sandbox webhooks.
- Verify signature and idempotency.
- Keep admin diagnostics visible.

### Step 4 - Production provider

- Configure production provider keys through environment/secrets.
- Enable webhook endpoint.
- Run test purchases.
- Monitor webhook failures.

### Step 5 - Credit wallet

- Add wallet tables and usage events.
- Start in shadow mode: record usage but do not block.
- Compare estimated and actual cost.
- Enable read-only mode after confidence.

---

## 21. Security and Compliance Requirements

- Never store raw card/payment credentials.
- Verify every provider webhook signature.
- Store provider event IDs and enforce idempotency.
- Audit every admin billing write.
- Do not expose provider secrets to mobile.
- Do not trust mobile confirmation without backend verification.
- Minimize raw provider payload exposure in admin UI.
- Avoid deleting subscription/payment rows during parent deletion until retention policy is confirmed.
- Ensure parent account deletion covers or anonymizes billing references according to legal requirements.

---

## 22. Operational Alerts

Add alerts for:

- webhook verification failures,
- checkout session failures,
- duplicate webhook events above threshold,
- subscription update failures,
- high cancellation rate,
- high payment failure rate,
- child-limit error spike,
- provider API outage,
- mismatch between provider state and local subscription state.

---

## 23. Open Questions

1. Is `starter` a free plan, a paid plan, or a 7-day trial plan?
2. Which provider is the first real payment target: App Store, Play Store, Stripe, Razorpay, or another provider?
3. Should mobile use `/billing/*` routes or mobile aliases like `/plans/family`?
4. Are quarterly and annual cycles required for the first backend integration, or only monthly?
5. Do subscriptions renew through app stores or external checkout?
6. Should child profiles above a downgraded plan limit remain chat-enabled or become read-only?
7. Are credit wallets required before production billing, or can child-limit subscriptions ship first?
8. What is the legal retention policy for subscription and invoice data after parent deletion?

---

## 24. Complete Task Checklist

### Backend

- [ ] Centralize entitlement evaluation helper.
- [ ] Add plan display fields to `billing_plans`.
- [ ] Add checkout session table.
- [ ] Add provider product mapping table.
- [ ] Add webhook event table.
- [ ] Expand `/billing/plans` response.
- [ ] Expand `/billing/subscription` response with entitlement.
- [ ] Add checkout session idempotency.
- [ ] Add checkout confirmation endpoint with session ID.
- [ ] Improve child-limit error details.
- [ ] Add admin plan create/edit routes.
- [ ] Add admin subscription search/history routes.
- [ ] Add billing audit events.
- [ ] Add provider webhook route.
- [ ] Add provider sandbox integration.
- [ ] Add tests.

### Mobile

- [ ] Add `billingApi.ts`.
- [ ] Add `useBillingViewModel`.
- [ ] Replace hardcoded payment plans.
- [ ] Replace local `monthly/quarterly/annual` plan IDs with backend plan codes.
- [ ] Fetch current subscription.
- [ ] Create checkout session.
- [ ] Confirm demo checkout.
- [ ] Refresh dashboard after checkout.
- [ ] Update confirmation screen.
- [ ] Handle child-limit errors with upgrade CTA.
- [ ] Remove offline-only checkout copy.

### Admin

- [ ] Build Billing overview.
- [ ] Build plan management UI.
- [ ] Build subscription search/history UI.
- [ ] Add provider diagnostics UI.
- [ ] Show audit history for support changes.
- [ ] Add wallet/ledger screens after credit wallet phase.

### Future Wallet

- [ ] Add credit bucket table.
- [ ] Add usage event table.
- [ ] Add credit ledger table.
- [ ] Add credit pack table.
- [ ] Record chat usage in shadow mode.
- [ ] Add read-only entitlement mode.
- [ ] Add admin wallet adjustment flow.
