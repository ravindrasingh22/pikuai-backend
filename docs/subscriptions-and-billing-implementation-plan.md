# Pratvim Subscriptions & Billing Implementation Plan

**File:** `subscriptions-and-billing-implementation-plan.md`  
**Product:** Pratvim Mobile App  
**Primary users:** Parents and kids  
**Admin module:** `Admin Panel → Billing`  
**Frontend status:** Mobile frontend design is already implemented. This plan focuses on backend, admin configuration, API contracts, state wiring, and mobile integration.

---

## 1. Objective

Pratvim needs a billing system where parents can use a default free monthly plan, upgrade to paid subscriptions, and buy add-on credits when eligible.

The system must support:

1. A default **Free Active** entitlement for every parent account without an active paid subscription.
2. Admin-configurable monthly free credits.
3. Admin-configurable number of kids allowed per plan.
4. Admin-configurable paid plans and add-on credit packs.
5. Credit deduction for text input, text output, cached input, and voice usage if voice is enabled.
6. A read-only message mode when a plan usage limit is reached.
7. Backend-owned plan content so the mobile app can render plan cards without hardcoded plan text.
8. Safety checks and safety responses that are never disabled by billing.
9. All billing setup, monitoring, reporting, and adjustments under **Admin Panel → Billing**.

---

## 2. Key Product Rules

### 2.1 Free Active is the default

Every family account must have a billing entitlement.

If the parent does not have an active paid subscription, the backend must assign the account to the default free plan.

This includes:

- Newly created parent accounts.
- Parents who never subscribed.
- Parents whose paid subscription was cancelled.
- Parents whose paid subscription expired.
- Parents whose paid subscription was not renewed.

The default account mode for these users remains:

```ts
'FREE_ACTIVE'
```

Do **not** change the account mode to `FREE_EXHAUSTED_READ_ONLY` when free credits are used. Instead, store and return a limit flag.

---

### 2.2 Do not use exhausted account modes

Credit exhaustion should not be represented by changing the account mode.

Use these fields instead:

```ts
usage_limit_reached: boolean
kid_limit_reached: boolean
message_write_mode: 'READ_WRITE' | 'READ_ONLY'
can_chat: boolean
can_read_history: boolean
```

Correct model:

```text
Account mode = commercial entitlement state
Limit flags = whether the current plan limit is reached
Message write mode = whether kids can send normal new messages
```

Example:

```json
{
  "account_mode": "FREE_ACTIVE",
  "usage_limit_reached": true,
  "message_write_mode": "READ_ONLY",
  "can_chat": false,
  "can_read_history": true
}
```

---

### 2.3 Safety is never compromised

Billing must never disable safety.

This means:

1. Safety classifier / guardrail checks must run even if credits are zero.
2. High-risk safety responses must be allowed even if the plan limit is reached.
3. Parent safety alerts must still work if billing limit is reached.
4. Read-only mode blocks normal chat generation, not safety handling.

Examples of safety-critical categories:

- self-harm
- grooming
- blackmail
- coercion
- abuse
- bullying escalation
- unsafe meeting request
- immediate danger
- dangerous instruction seeking

Backend rule:

```text
If usage limit is reached:
    Run safety classifier first.
    If safety-critical:
        Return safe response and trigger parent safety workflow if required.
    Else:
        Block normal generation and keep message history read-only.
```

---

### 2.4 No model variation

Pratvim should not have model-based plan behavior in this version.

Rules:

- All plans use the same AI model / AI engine.
- No Basic / Standard / Premium model tiers.
- No model-based entitlements.
- No model catalog required in Billing.
- No model-based rate cards.
- No model-based reports for MVP.

Credit cost should be based only on usage type:

- input tokens
- output tokens
- cached input tokens
- voice input seconds, if enabled
- voice output seconds, if enabled
- STT / TTS units if used separately

---

### 2.5 Plan content comes from backend

The mobile app should not hardcode plan card text.

Plan content should be managed from backend/admin and returned through APIs.

Backend should return:

- plan name
- title
- subtitle
- description
- feature bullets
- badge text
- CTA text
- footer note
- price display text
- credit display text
- kids allowed display text

This lets admin update plan copy without mobile app release.

---

## 3. Billing State Model

### 3.1 Account mode

Use account mode only for broad billing entitlement state.

```ts
type AccountMode =
  | 'FREE_ACTIVE'
  | 'SUBSCRIPTION_ACTIVE'
  | 'BILLING_GRACE'
  | 'BILLING_BLOCKED';
```

| Account mode | Meaning |
|---|---|
| `FREE_ACTIVE` | Default state when there is no active paid subscription |
| `SUBSCRIPTION_ACTIVE` | Paid subscription is active |
| `BILLING_GRACE` | Paid subscription has a billing issue but grace access is allowed |
| `BILLING_BLOCKED` | Account blocked by billing/admin/fraud process, not normal credit exhaustion |

Do not create these old states:

```text
FREE_EXHAUSTED_READ_ONLY
SUBSCRIPTION_EXHAUSTED
NO_CREDITS_READ_ONLY
```

Those should be represented by `usage_limit_reached` and `message_write_mode`.

---

### 3.2 Plan limit flags

Use explicit limit flags.

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

| Flag | Meaning |
|---|---|
| `usage_limit_reached` | Current plan credits are finished and no usable add-on credits are available |
| `kid_limit_reached` | Parent has reached the max kid profiles allowed by current plan |
| `message_write_mode` | `READ_WRITE` for normal use, `READ_ONLY` when normal chat is blocked |
| `can_chat` | Whether normal new child messages are allowed |
| `can_read_history` | Whether old messages can be read |
| `can_add_child` | Whether parent can add another kid profile |

---

## 4. Free Monthly Plan

### 4.1 Free plan behavior

The free plan is active by default for every account without an active paid subscription.

Example:

```text
Free Plan = 10 credits/month
```

The value must be admin configurable.

The free plan should support:

| Feature | Behavior |
|---|---|
| Monthly credits | Admin configurable |
| Kids allowed | Admin configurable |
| Voice enabled | Admin configurable, recommended No for MVP |
| Add-on credits | Recommended No until paid subscription is active |
| Message history | Always readable |
| New chat after usage limit reached | Block normal chat, keep read-only history |
| Safety response after usage limit reached | Always allowed for safety-critical messages |

---

### 4.2 Free plan after paid cancellation

When a parent cancels or loses a paid subscription:

1. Paid subscription status becomes cancelled/expired.
2. The account falls back to the default free plan.
3. `account_mode` becomes `FREE_ACTIVE`.
4. Backend applies free plan limits.
5. If free credits are already used for the current free period, set `usage_limit_reached = true`.
6. If the family has more kids than the free plan allows, set `kid_limit_reached = true` and block adding more kids.

Do not delete existing child profiles.

Recommended MVP behavior for excess kids after downgrade/cancellation:

```text
If active kids count > max kids allowed:
    Keep all kid profiles visible to parent.
    Allow old message history to be read.
    Allow normal chat only for the first allowed active kid profiles or require parent to choose active kid profiles.
    Mark remaining kid profiles as read-only until parent upgrades.
```

---

### 4.3 Free usage limit reached

When free monthly credits reach zero:

- Keep `account_mode = FREE_ACTIVE`.
- Set `usage_limit_reached = true`.
- Set `message_write_mode = READ_ONLY`.
- Set `can_chat = false` for normal chat.
- Keep `can_read_history = true`.
- Parent should see a subscription CTA.
- Kid should see soft read-only messaging.

Kid-facing copy:

```text
Your free Pratvim messages for this month are finished. You can still read your old chats. Ask your parent to unlock more Pratvim time.
```

Parent-facing copy:

```text
Free monthly credits are used. Subscribe to keep Pratvim active for your kid.
```

---

## 5. Paid Subscriptions

### 5.1 Paid plan behavior

Paid subscriptions provide:

1. Monthly access.
2. Monthly included credits.
3. Admin-configured kids allowed.
4. Voice access if enabled for that plan.
5. Eligibility for add-on credit packs.
6. Backend-owned plan content for mobile display.

Paid subscriptions do **not** provide different model tiers.

---

### 5.2 Paid plan examples

These are examples only. Final values should come from **Admin → Billing → Plans**.

| Plan | Included monthly credits | Kids allowed | Voice | Add-on credits |
|---|---:|---:|---:|---:|
| Basic | 10,000 | 1 | No | Yes |
| Plus | 50,000 | 2 | Yes | Yes |
| Family | 150,000 | 4 | Yes | Yes |

---

### 5.3 Paid usage limit reached

When paid monthly credits are used:

1. Use add-on credits if available.
2. If no add-on credits are available, set `usage_limit_reached = true`.
3. Keep `account_mode = SUBSCRIPTION_ACTIVE` if the paid subscription itself is still active.
4. Set `message_write_mode = READ_ONLY` for normal child chat.
5. Parent can buy add-on credits or upgrade plan.
6. Safety-critical responses remain available.

Parent-facing copy:

```text
Monthly credits are used. Add extra credits or upgrade your plan to continue chatting.
```

Kid-facing copy:

```text
Pratvim needs a quick refill from your parent to continue. You can still read your old chats.
```

---

## 6. Kids Allowed Limit

### 6.1 Admin-configurable per plan

Every plan must have an admin-configurable kids limit.

Fields:

```text
max_kids_allowed
```

Examples:

| Plan | Max kids allowed |
|---|---:|
| Free | 1 |
| Basic | 1 |
| Plus | 2 |
| Family | 4 |

---

### 6.2 Add child enforcement

When parent tries to add a kid profile:

```text
Backend checks current effective plan.
Backend counts active kid profiles.
If active kids count >= max kids allowed:
    Do not create new kid profile.
    Set/return kid_limit_reached = true.
    Return KID_LIMIT_REACHED.
Else:
    Create kid profile.
```

API error example:

```json
{
  "error_code": "KID_LIMIT_REACHED",
  "account_mode": "FREE_ACTIVE",
  "kid_limit_reached": true,
  "active_kids_count": 1,
  "max_kids_allowed": 1,
  "message": "Your current plan allows 1 kid profile. Upgrade to add more."
}
```

---

## 7. Add-on Credits

### 7.1 Add-on credit rule

Recommended MVP rule:

```text
Only paid subscribers can buy add-on credits.
```

This keeps the funnel simple:

```text
Free plan limit reached → subscribe first.
Paid plan limit reached → buy add-on credits or upgrade.
```

---

### 7.2 Add-on credit behavior

| Rule | Behavior |
|---|---|
| Purchase type | Consumable in-app product |
| Expiry | No expiry recommended |
| Reset monthly | No |
| Used before monthly credits? | No |
| Used after monthly credits? | Yes |
| Refund support | Ledger adjustment/reversal required |

---

### 7.3 Credit pack examples

| Pack | Credits |
|---|---:|
| Small Pack | 10,000 |
| Medium Pack | 50,000 |
| Large Pack | 150,000 |

Pack amount, product IDs, display copy, status, and eligible plans should be configurable under:

```text
Admin Panel → Billing → Credit Packs
```

---

## 8. Credit Consumption Priority

Credits should be consumed in this order:

1. Free monthly credits, only for accounts on the free plan.
2. Paid monthly subscription credits, only for active paid plans.
3. Promotional credits, if configured.
4. Add-on purchased credits.
5. Admin adjustment credits.

Important:

```text
Do not grant free monthly credits and paid monthly credits at the same time for the same effective billing period.
```

If a paid subscription is cancelled/expired, the account returns to free plan behavior from the next entitlement evaluation.

---

## 9. Read-only Message Mode

### 9.1 Read-only behavior

Read-only mode is not an account mode. It is a message write state.

```ts
type MessageWriteMode = 'READ_WRITE' | 'READ_ONLY';
```

Allowed in read-only:

- View previous conversations.
- Open old AI responses.
- Scroll chat history.
- Read saved content.
- Ask parent to unlock.
- Safety-critical detection and response.

Blocked in read-only:

- Send a new normal message.
- Generate a normal new AI answer.
- Start normal voice chat.
- Upload normal voice input.

---

### 9.2 Backend source of truth

Mobile can hide the composer for UX, but backend must enforce read-only mode.

```text
Mobile state is not trusted.
Backend entitlement + wallet state is the final authority.
```

---

## 10. Admin Panel Structure

All subscription and credit settings must come under:

```text
Admin Panel → Billing
```

### 10.1 Billing menu structure

```text
Billing
├── Overview
├── Plans
├── Free Plan
├── Credit Packs
├── Rate Cards
├── Subscriptions
├── Family Wallets
├── Usage Events
├── Credit Ledger
├── Adjustments
├── Store Products
├── Billing Alerts
├── Reports
└── Settings
```

Removed from MVP:

```text
Model Catalog
```

Reason:

```text
No model variation is needed. All plans use the same AI engine.
```

---

### 10.2 Billing → Overview

Purpose: show operational billing summary.

Metrics:

- Active subscriptions
- Free accounts
- Free accounts with usage limit reached
- Paid accounts with usage limit reached
- Add-on credits sold
- Credits consumed today
- Monthly recurring revenue
- Failed renewals
- Billing grace accounts
- Kids limit reached count
- Free-to-paid conversion

---

### 10.3 Billing → Plans

Admin can configure paid plans and their mobile display content.

Fields:

| Field | Description |
|---|---|
| Plan name | Basic, Plus, Family |
| Plan type | Paid |
| Included monthly credits | Credits granted every billing cycle |
| Monthly price | Display/reference price |
| Price display text | Backend-owned display string for mobile |
| App Store product ID | iOS subscription product ID |
| Play Store product ID | Android subscription product ID |
| Max kids allowed | Number of kid profiles allowed |
| Voice enabled | Yes/No |
| Add-on credits allowed | Yes/No |
| Plan title | Mobile card title |
| Plan subtitle | Mobile card subtitle |
| Plan description | Mobile card/body text |
| Feature bullets | JSON/list of features |
| Badge text | Example: Popular, Best Value |
| CTA text | Example: Start Plus |
| Footer note | Terms/helper text |
| Status | Active/Inactive |
| Sort order | Display ordering |

Do not include:

```text
Allowed model tier
Model key
Model catalog reference
```

---

### 10.4 Billing → Free Plan

Admin can configure default free monthly access.

Fields:

| Field | Description |
|---|---|
| Free monthly credits | Default 10 or admin-configured value |
| Reset frequency | Monthly |
| Max kids allowed | Admin configurable |
| Voice enabled | Yes/No, recommended No for MVP |
| Add-on credits allowed | Recommended No |
| Read-only after usage limit | Yes |
| Safety always enabled | Must be Yes and not disabled |
| Require verified parent email/phone | Recommended |
| Plan title | Mobile card/title text |
| Plan subtitle | Mobile subtitle |
| Plan description | Mobile description |
| Feature bullets | JSON/list of free plan features |
| CTA text | Example: Continue Free / Upgrade |
| Footer note | Helper text |
| Status | Active/Inactive |

Do not include model tier or model behavior fields.

---

### 10.5 Billing → Credit Packs

Admin can configure add-on packs.

Fields:

| Field | Description |
|---|---|
| Pack name | Small/Medium/Large |
| Credit amount | Number of credits granted |
| Price display text | Backend-owned display string |
| App Store product ID | iOS consumable product ID |
| Play Store product ID | Android consumable product ID |
| Eligible plans | Which paid plans can buy this |
| Pack title | Mobile card title |
| Pack description | Mobile card text |
| Feature bullets | Optional JSON/list |
| CTA text | Example: Add Credits |
| Status | Active/Inactive |
| Sort order | Display ordering |

---

### 10.6 Billing → Rate Cards

Admin configures credit conversion rules.

Rate cards are global, usage-type based, and versioned.

Fields:

| Field | Description |
|---|---|
| Rate card name | Example: Default July 2026 |
| Version | v1, v2, v3 |
| Status | Draft/Active/Archived |
| Effective from | Date/time |
| Created by | Admin user |

Rate card items:

| Usage type | Unit | Example |
|---|---|---:|
| `TEXT_INPUT_TOKEN` | Per 1,000 tokens | 10 credits |
| `TEXT_OUTPUT_TOKEN` | Per 1,000 tokens | 40 credits |
| `CACHED_INPUT_TOKEN` | Per 1,000 tokens | 2 credits |
| `VOICE_INPUT_SECOND` | Per second | 3 credits |
| `VOICE_OUTPUT_SECOND` | Per second | 4 credits |
| `STT_AUDIO_SECOND` | Per second | 2 credits |
| `TTS_CHARACTER` | Per 1,000 chars | 5 credits |

Internal safety items:

| Usage type | Recommendation |
|---|---|
| `SAFETY_CLASSIFIER_CALL` | Do not charge parent separately |
| `VALIDATOR_CALL` | Do not charge parent separately |
| `NORMALIZER_CALL` | Do not charge parent separately |

Do not use `model_catalog_id` in rate card items.

---

### 10.7 Billing → Subscriptions

Admin can view subscription state by family account.

Columns:

- Family account
- Parent name/email
- Current effective plan
- Store
- Subscription status
- Current period start
- Current period end
- Auto-renew status
- Renewal issue
- Cancelled/expired date
- Fallback plan, usually Free
- Created at

Actions:

- View subscription details
- View family wallet
- View credit ledger
- Grant adjustment credits
- Add internal note

Do not manually mark paid subscriptions active unless there is a controlled support process.

---

### 10.8 Billing → Family Wallets

Shows credit balances and current plan limit state by family.

Columns:

- Family account
- Account mode
- Effective plan
- Usage limit reached
- Kid limit reached
- Message write mode
- Monthly credits remaining
- Add-on credits remaining
- Promo credits remaining
- Total credits remaining
- Active kids count
- Max kids allowed
- Next reset date
- Last usage date

Actions:

- View credit buckets
- View ledger
- Add adjustment
- Lock wallet if abuse detected
- Recalculate entitlement state

---

### 10.9 Billing → Usage Events

Shows AI usage events.

Columns:

- Date/time
- Family
- Kid profile
- Conversation
- Input tokens
- Cached input tokens
- Output tokens
- Voice input seconds
- Voice output seconds
- Credits charged
- Safety-critical flag
- Request status

Filters:

- Date range
- Family
- Kid
- Plan
- Usage type
- High usage only
- Safety-critical only

Do not include model filters for MVP.

---

### 10.10 Billing → Credit Ledger

Immutable ledger of all credit changes.

Ledger event types:

```text
grant
debit
refund
reserve
release
adjustment
expiry
reversal
```

Columns:

- Date/time
- Family
- Event type
- Amount delta
- Balance after
- Source type
- Request ID
- Usage event ID
- Admin reason
- Idempotency key

---

### 10.11 Billing → Adjustments

Manual credit adjustments.

Required fields:

- Family account
- Amount
- Add/remove
- Reason
- Admin note
- Approved by, if required

Allowed reasons:

```text
Support compensation
Refund correction
Founder promo
Testing grant
Billing issue
Migration correction
Abuse reversal
```

---

### 10.12 Billing → Store Products

Map internal plans/packs to iOS and Android product IDs.

Fields:

- Internal product ID
- Product type: subscription/consumable
- App Store product ID
- Play Store product ID
- Linked plan or credit pack
- Status
- Last verified date

---

### 10.13 Billing → Billing Alerts

Admin can configure alert thresholds.

Examples:

| Alert | Default |
|---|---:|
| Low credit warning | 20% remaining |
| Very low credit warning | 5% remaining |
| Usage limit reached | Enabled |
| Kid limit reached | Enabled |
| Failed renewal | Enabled |
| High usage spike | Enabled |
| Repeated free account creation | Enabled |

---

### 10.14 Billing → Reports

Reports:

- Free to paid conversion
- Plan distribution
- Credit consumption by plan
- Add-on pack purchases
- Revenue estimate
- Usage by kid age band
- Usage by day/week/month
- Free plan abuse signals
- Usage limit reached funnel
- Kid limit reached funnel

Do not include model-based reports for MVP.

---

### 10.15 Billing → Settings

Global settings:

| Setting | Purpose |
|---|---|
| Credit display name | Credits / Pratvim Credits |
| Default currency | INR/USD/etc. |
| Grace period days | Billing grace behavior |
| Safety always enabled | Must be enabled and protected |
| Free plan enabled | Turn default free plan on/off only if business wants closed access |
| Default free plan ID | Used when no paid subscription is active |
| Add-on credits require paid subscription | Recommended Yes |
| Usage reservation enabled | Recommended Yes |
| Minimum credit charge | Optional |
| Rounding mode | ceil/floor/nearest |

---

## 11. Backend Database Design

### 11.1 `plans`

```sql
CREATE TABLE plans (
  id UUID PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  plan_type VARCHAR(20) NOT NULL, -- free / paid
  monthly_price_minor BIGINT DEFAULT 0,
  currency VARCHAR(10),
  included_monthly_credits BIGINT NOT NULL,
  max_kids_allowed INT NOT NULL DEFAULT 1,
  voice_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  addon_credits_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  is_default_free BOOLEAN NOT NULL DEFAULT FALSE,
  billing_period VARCHAR(20) NOT NULL DEFAULT 'monthly',
  price_display_text VARCHAR(100),
  credit_display_text VARCHAR(100),
  kids_display_text VARCHAR(100),
  plan_title VARCHAR(150),
  plan_subtitle VARCHAR(250),
  plan_description TEXT,
  feature_bullets_json JSONB,
  badge_text VARCHAR(100),
  cta_text VARCHAR(100),
  footer_note TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INT DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

Important:

```text
No allowed_model_tier column.
No model_catalog reference.
```

---

### 11.2 `family_billing_state`

Stores the current effective billing state and plan limit flags for a family.

```sql
CREATE TABLE family_billing_state (
  id UUID PRIMARY KEY,
  family_account_id UUID NOT NULL UNIQUE,
  effective_plan_id UUID NOT NULL REFERENCES plans(id),
  current_subscription_id UUID NULL,
  account_mode VARCHAR(40) NOT NULL DEFAULT 'FREE_ACTIVE',
  usage_limit_reached BOOLEAN NOT NULL DEFAULT FALSE,
  kid_limit_reached BOOLEAN NOT NULL DEFAULT FALSE,
  message_write_mode VARCHAR(20) NOT NULL DEFAULT 'READ_WRITE', -- READ_WRITE / READ_ONLY
  can_chat BOOLEAN NOT NULL DEFAULT TRUE,
  can_read_history BOOLEAN NOT NULL DEFAULT TRUE,
  can_add_child BOOLEAN NOT NULL DEFAULT TRUE,
  active_kids_count INT NOT NULL DEFAULT 0,
  max_kids_allowed INT NOT NULL DEFAULT 1,
  next_credit_reset_at TIMESTAMP NULL,
  last_evaluated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

Rules:

```text
For non-paid or cancelled paid users:
    effective_plan_id = default free plan
    account_mode = FREE_ACTIVE

For active paid users:
    effective_plan_id = paid plan
    account_mode = SUBSCRIPTION_ACTIVE

If credits are finished:
    usage_limit_reached = true
    message_write_mode = READ_ONLY
    can_chat = false
    account_mode does not change
```

---

### 11.3 `subscriptions`

```sql
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY,
  family_account_id UUID NOT NULL,
  plan_id UUID NOT NULL REFERENCES plans(id),
  store VARCHAR(30) NOT NULL, -- apple / google / revenuecat / web
  store_customer_id VARCHAR(200),
  store_transaction_id VARCHAR(300),
  status VARCHAR(40) NOT NULL, -- active / cancelled / expired / grace / billing_issue
  current_period_start TIMESTAMP,
  current_period_end TIMESTAMP,
  auto_renew BOOLEAN DEFAULT TRUE,
  cancelled_at TIMESTAMP NULL,
  expired_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

### 11.4 `credit_packs`

```sql
CREATE TABLE credit_packs (
  id UUID PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  credit_amount BIGINT NOT NULL,
  price_display_text VARCHAR(100),
  pack_title VARCHAR(150),
  pack_description TEXT,
  feature_bullets_json JSONB,
  cta_text VARCHAR(100),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  eligible_plan_type VARCHAR(30) DEFAULT 'paid',
  sort_order INT DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

### 11.5 `store_products`

```sql
CREATE TABLE store_products (
  id UUID PRIMARY KEY,
  internal_product_key VARCHAR(120) UNIQUE NOT NULL,
  product_type VARCHAR(30) NOT NULL, -- subscription / consumable
  platform VARCHAR(30) NOT NULL, -- ios / android / web
  store_product_id VARCHAR(200) NOT NULL,
  plan_id UUID NULL REFERENCES plans(id),
  credit_pack_id UUID NULL REFERENCES credit_packs(id),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

### 11.6 `credit_buckets`

```sql
CREATE TABLE credit_buckets (
  id UUID PRIMARY KEY,
  family_account_id UUID NOT NULL,
  source_type VARCHAR(40) NOT NULL, -- free_monthly / paid_monthly / addon_purchase / promo / admin_adjustment
  source_id UUID NULL,
  credits_granted BIGINT NOT NULL,
  credits_remaining BIGINT NOT NULL,
  expires_at TIMESTAMP NULL,
  priority INT NOT NULL DEFAULT 100,
  status VARCHAR(30) NOT NULL DEFAULT 'active', -- active / expired / reversed / locked
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

### 11.7 `credit_ledger`

```sql
CREATE TABLE credit_ledger (
  id UUID PRIMARY KEY,
  family_account_id UUID NOT NULL,
  child_id UUID NULL,
  bucket_id UUID NULL REFERENCES credit_buckets(id),
  event_type VARCHAR(40) NOT NULL, -- grant / debit / refund / reserve / release / adjustment / expiry / reversal
  amount_delta BIGINT NOT NULL,
  balance_after BIGINT NOT NULL,
  request_id VARCHAR(120),
  usage_event_id UUID NULL,
  idempotency_key VARCHAR(300) UNIQUE NOT NULL,
  metadata_json JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

### 11.8 `rate_cards`

```sql
CREATE TABLE rate_cards (
  id UUID PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  version INT NOT NULL,
  status VARCHAR(30) NOT NULL, -- draft / active / archived
  effective_from TIMESTAMP,
  created_by UUID,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

### 11.9 `rate_card_items`

Global usage-type pricing only.

```sql
CREATE TABLE rate_card_items (
  id UUID PRIMARY KEY,
  rate_card_id UUID NOT NULL REFERENCES rate_cards(id),
  usage_type VARCHAR(50) NOT NULL,
  unit VARCHAR(50) NOT NULL,
  credits_per_unit BIGINT NOT NULL,
  min_charge_credits BIGINT DEFAULT 0,
  rounding_mode VARCHAR(20) DEFAULT 'ceil',
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

Important:

```text
No model_catalog_id.
No model tier.
No model-based pricing.
```

---

### 11.10 `usage_events`

```sql
CREATE TABLE usage_events (
  id UUID PRIMARY KEY,
  family_account_id UUID NOT NULL,
  child_id UUID NULL,
  conversation_id UUID NULL,
  request_id VARCHAR(120) NOT NULL,
  rate_card_id UUID NOT NULL REFERENCES rate_cards(id),
  input_tokens BIGINT DEFAULT 0,
  cached_input_tokens BIGINT DEFAULT 0,
  output_tokens BIGINT DEFAULT 0,
  voice_input_seconds NUMERIC(12, 3) DEFAULT 0,
  voice_output_seconds NUMERIC(12, 3) DEFAULT 0,
  stt_audio_seconds NUMERIC(12, 3) DEFAULT 0,
  tts_characters BIGINT DEFAULT 0,
  credits_charged BIGINT NOT NULL DEFAULT 0,
  safety_critical BOOLEAN NOT NULL DEFAULT FALSE,
  charge_skipped_reason VARCHAR(100) NULL,
  status VARCHAR(30) NOT NULL, -- reserved / completed / failed / refunded / safety_no_charge
  metadata_json JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

## 12. Backend Services

### 12.1 Billing Entitlement Service

Responsibility:

- Determine current effective plan.
- Default to Free Plan if no active paid subscription exists.
- Keep `FREE_ACTIVE` as default for cancelled/expired paid users.
- Determine plan credit status.
- Determine kids limit status.
- Return `usage_limit_reached` and `kid_limit_reached`.
- Return `message_write_mode`.
- Return plan content for mobile.

Method:

```ts
getEntitlement(familyAccountId: string): BillingEntitlement
```

---

### 12.2 Family Plan State Evaluator

Responsibility:

- Recalculate `family_billing_state`.
- Recalculate `usage_limit_reached`.
- Recalculate `kid_limit_reached`.
- Recalculate `can_chat` and `can_add_child`.
- Run after subscription change, credit grant, debit, child add/remove, and admin plan update.

Pseudo-code:

```ts
async function evaluateFamilyBillingState(familyAccountId: string) {
  const activeSubscription = await subscriptions.findActive(familyAccountId);
  const defaultFreePlan = await plans.getDefaultFreePlan();

  const effectivePlan = activeSubscription
    ? await plans.getById(activeSubscription.planId)
    : defaultFreePlan;

  const accountMode = activeSubscription ? 'SUBSCRIPTION_ACTIVE' : 'FREE_ACTIVE';
  const totalCredits = await wallet.getUsableCredits(familyAccountId, effectivePlan.id);
  const activeKidsCount = await kids.countActive(familyAccountId);

  const usageLimitReached = totalCredits <= 0;
  const kidLimitReached = activeKidsCount >= effectivePlan.maxKidsAllowed;

  return familyBillingState.upsert({
    familyAccountId,
    effectivePlanId: effectivePlan.id,
    currentSubscriptionId: activeSubscription?.id ?? null,
    accountMode,
    usageLimitReached,
    kidLimitReached,
    messageWriteMode: usageLimitReached ? 'READ_ONLY' : 'READ_WRITE',
    canChat: !usageLimitReached,
    canReadHistory: true,
    canAddChild: activeKidsCount < effectivePlan.maxKidsAllowed,
    activeKidsCount,
    maxKidsAllowed: effectivePlan.maxKidsAllowed,
  });
}
```

---

### 12.3 Credit Wallet Service

Responsibility:

- Grant credits.
- Reserve credits.
- Debit credits.
- Release reserved credits.
- Refund credits.
- Expire credits.
- Return balance summary.

Important:

Use database transactions and row locks when debiting credits.

```sql
SELECT * FROM credit_buckets
WHERE family_account_id = :familyAccountId
AND status = 'active'
AND credits_remaining > 0
ORDER BY priority ASC, created_at ASC
FOR UPDATE;
```

---

### 12.4 Usage Metering Service

Responsibility:

- Record AI usage.
- Apply active global rate card.
- Calculate credits by usage type.
- Create usage event.
- Link usage event to ledger debit.

---

### 12.5 Rate Card Service

Responsibility:

- Manage active global rate card.
- Price usage types.
- Support draft/active/archive workflow.
- Never modify active rate card in place. Create a new version.

---

### 12.6 Purchase Verification Service

Responsibility:

- Verify mobile purchases.
- Handle App Store / Play Store / RevenueCat events.
- Prevent duplicate credit grants.
- Activate/cancel subscriptions.
- Grant add-on credits.
- Re-evaluate family billing state after purchase events.

---

### 12.7 Monthly Credit Job

Runs monthly or based on each account billing cycle.

Logic:

```ts
for each familyAccount:
  if hasActivePaidSubscription(familyAccount):
    grantPaidMonthlyCredits(familyAccount)
  else:
    grantFreeMonthlyCredits(familyAccount)
    setAccountMode(familyAccount, 'FREE_ACTIVE')

  evaluateFamilyBillingState(familyAccount)
```

Important:

```text
Cancelled paid users get FREE_ACTIVE by default.
Do not grant both free and paid monthly credits for the same effective period.
```

---

## 13. Credit Calculation

### 13.1 Usage types

```ts
type UsageType =
  | 'TEXT_INPUT_TOKEN'
  | 'TEXT_OUTPUT_TOKEN'
  | 'CACHED_INPUT_TOKEN'
  | 'VOICE_INPUT_SECOND'
  | 'VOICE_OUTPUT_SECOND'
  | 'STT_AUDIO_SECOND'
  | 'TTS_CHARACTER'
  | 'SAFETY_CLASSIFIER_CALL'
  | 'VALIDATOR_CALL'
  | 'NORMALIZER_CALL';
```

### 13.2 Formula

```text
credits =
  inputTokenUnits * inputRate
+ cachedTokenUnits * cachedInputRate
+ outputTokenUnits * outputRate
+ voiceInputSeconds * voiceInputRate
+ voiceOutputSeconds * voiceOutputRate
+ sttAudioSeconds * sttRate
+ ttsCharacterUnits * ttsRate
```

Example:

```text
Input tokens: 800
Cached tokens: 300
Output tokens: 500
Input rate: 10 credits / 1000 tokens
Cached rate: 2 credits / 1000 tokens
Output rate: 40 credits / 1000 tokens

Input charge = 8
Cached charge = 0.6
Output charge = 20
Total = 28.6
Rounded = 29 credits
```

### 13.3 Rounding

Recommended:

```text
rounding_mode = ceil
```

This avoids undercharging.

---

## 14. Backend API Contracts

### 14.1 Get billing entitlement

```http
GET /v1/billing/entitlement
```

Response: free plan with credits available

```json
{
  "account_mode": "FREE_ACTIVE",
  "effective_plan": {
    "id": "free",
    "type": "free",
    "name": "Free",
    "title": "Try Pratvim for free",
    "subtitle": "A small monthly allowance to get started",
    "description": "Your kid can safely try Pratvim with free monthly credits.",
    "feature_bullets": [
      "10 free credits every month",
      "1 kid profile",
      "Read previous chats anytime"
    ],
    "cta_text": "Upgrade",
    "badge_text": "Free",
    "price_display_text": "Free",
    "credit_display_text": "10 credits/month",
    "kids_display_text": "1 kid"
  },
  "limits": {
    "usage_limit_reached": false,
    "kid_limit_reached": false,
    "message_write_mode": "READ_WRITE",
    "can_chat": true,
    "can_read_history": true,
    "can_add_child": false,
    "active_kids_count": 1,
    "max_kids_allowed": 1
  },
  "features": {
    "voice_enabled": false,
    "can_buy_subscription": true,
    "can_buy_addon_credits": false
  },
  "credits": {
    "monthly_granted": 10,
    "monthly_remaining": 6,
    "addon_remaining": 0,
    "total_remaining": 6,
    "renews_at": "2026-08-01T00:00:00Z"
  }
}
```

Response: free plan limit reached

```json
{
  "account_mode": "FREE_ACTIVE",
  "effective_plan": {
    "id": "free",
    "type": "free",
    "name": "Free",
    "title": "Free Plan",
    "cta_text": "Subscribe to continue",
    "price_display_text": "Free",
    "credit_display_text": "10 credits/month",
    "kids_display_text": "1 kid"
  },
  "limits": {
    "usage_limit_reached": true,
    "kid_limit_reached": false,
    "message_write_mode": "READ_ONLY",
    "can_chat": false,
    "can_read_history": true,
    "can_add_child": false,
    "active_kids_count": 1,
    "max_kids_allowed": 1
  },
  "features": {
    "voice_enabled": false,
    "can_buy_subscription": true,
    "can_buy_addon_credits": false
  },
  "credits": {
    "monthly_granted": 10,
    "monthly_remaining": 0,
    "addon_remaining": 0,
    "total_remaining": 0,
    "renews_at": "2026-08-01T00:00:00Z"
  }
}
```

Response: paid subscription active

```json
{
  "account_mode": "SUBSCRIPTION_ACTIVE",
  "effective_plan": {
    "id": "plus",
    "type": "paid",
    "name": "Plus",
    "title": "More safe AI time for your family",
    "subtitle": "For regular Pratvim use",
    "description": "A monthly plan with more credits and more kid profiles.",
    "feature_bullets": [
      "50,000 credits every month",
      "2 kid profiles",
      "Voice access if enabled"
    ],
    "cta_text": "Current Plan",
    "badge_text": "Popular",
    "price_display_text": "₹XXX/month",
    "credit_display_text": "50,000 credits/month",
    "kids_display_text": "2 kids"
  },
  "limits": {
    "usage_limit_reached": false,
    "kid_limit_reached": false,
    "message_write_mode": "READ_WRITE",
    "can_chat": true,
    "can_read_history": true,
    "can_add_child": true,
    "active_kids_count": 1,
    "max_kids_allowed": 2
  },
  "features": {
    "voice_enabled": true,
    "can_buy_subscription": true,
    "can_buy_addon_credits": true
  },
  "plan": {
    "id": "plus",
    "name": "Plus",
    "status": "active",
    "renews_at": "2026-08-01T00:00:00Z"
  },
  "credits": {
    "monthly_granted": 50000,
    "monthly_remaining": 12000,
    "addon_remaining": 20000,
    "total_remaining": 32000,
    "used_percent": 76
  }
}
```

---

### 14.2 Get billing usage summary

```http
GET /v1/billing/usage-summary
```

Response:

```json
{
  "account_mode": "SUBSCRIPTION_ACTIVE",
  "effective_plan": {
    "id": "plus",
    "name": "Plus",
    "type": "paid"
  },
  "limits": {
    "usage_limit_reached": false,
    "kid_limit_reached": false,
    "message_write_mode": "READ_WRITE"
  },
  "credits": {
    "monthly_granted": 50000,
    "monthly_remaining": 12000,
    "addon_remaining": 20000,
    "total_remaining": 32000,
    "used_percent": 76
  },
  "alerts": {
    "low_credit": true,
    "usage_limit_reached": false,
    "kid_limit_reached": false
  }
}
```

---

### 14.3 Get available plans

```http
GET /v1/billing/plans
```

Response:

```json
{
  "plans": [
    {
      "id": "basic",
      "type": "paid",
      "name": "Basic",
      "title": "Start safe AI learning",
      "subtitle": "For light use",
      "description": "A simple plan for one kid profile.",
      "feature_bullets": [
        "10,000 credits every month",
        "1 kid profile",
        "Read old chats anytime"
      ],
      "monthly_credits": 10000,
      "max_kids_allowed": 1,
      "voice_enabled": false,
      "store_product_id": "pratvim_basic_monthly",
      "cta_text": "Choose Basic",
      "price_display_text": "₹XXX/month",
      "credit_display_text": "10,000 credits/month",
      "kids_display_text": "1 kid",
      "recommended": false
    },
    {
      "id": "plus",
      "type": "paid",
      "name": "Plus",
      "title": "More safe AI time",
      "subtitle": "For regular use",
      "description": "More credits and more kid profiles.",
      "feature_bullets": [
        "50,000 credits every month",
        "2 kid profiles",
        "Voice access if enabled"
      ],
      "monthly_credits": 50000,
      "max_kids_allowed": 2,
      "voice_enabled": true,
      "store_product_id": "pratvim_plus_monthly",
      "cta_text": "Choose Plus",
      "price_display_text": "₹XXX/month",
      "credit_display_text": "50,000 credits/month",
      "kids_display_text": "2 kids",
      "recommended": true
    }
  ]
}
```

---

### 14.4 Get credit packs

```http
GET /v1/billing/credit-packs
```

Response for paid users:

```json
{
  "eligible": true,
  "packs": [
    {
      "id": "small_pack",
      "name": "Small Pack",
      "title": "Small Credit Pack",
      "description": "Add extra credits for this month and beyond.",
      "credits": 10000,
      "cta_text": "Add 10,000 credits",
      "price_display_text": "₹XX",
      "store_product_id": "credits_small_pack"
    },
    {
      "id": "medium_pack",
      "name": "Medium Pack",
      "title": "Medium Credit Pack",
      "description": "Best for regular family usage.",
      "credits": 50000,
      "cta_text": "Add 50,000 credits",
      "price_display_text": "₹XX",
      "store_product_id": "credits_medium_pack"
    }
  ]
}
```

Response for free users:

```json
{
  "eligible": false,
  "reason": "SUBSCRIPTION_REQUIRED",
  "packs": []
}
```

---

### 14.5 Verify purchase

```http
POST /v1/billing/purchase/verify
```

Request:

```json
{
  "platform": "ios",
  "product_id": "pratvim_plus_monthly",
  "purchase_token": "store_purchase_token",
  "transaction_id": "store_transaction_id",
  "purchase_type": "subscription"
}
```

Response:

```json
{
  "success": true,
  "account_mode": "SUBSCRIPTION_ACTIVE",
  "entitlement_refresh_required": true
}
```

---

### 14.6 Restore purchases

```http
POST /v1/billing/restore
```

Response:

```json
{
  "success": true,
  "restored_subscriptions": 1,
  "restored_credit_packs": 0,
  "entitlement_refresh_required": true
}
```

---

### 14.7 Chat API billing response

```http
POST /v1/chat
```

Success response:

```json
{
  "message": {
    "id": "msg_123",
    "content": "AI response"
  },
  "billing": {
    "credits_charged": 29,
    "credits_remaining": 31971,
    "account_mode": "SUBSCRIPTION_ACTIVE",
    "usage_limit_reached": false,
    "message_write_mode": "READ_WRITE"
  }
}
```

Usage limit reached response:

```json
{
  "error_code": "PLAN_USAGE_LIMIT_REACHED",
  "account_mode": "FREE_ACTIVE",
  "usage_limit_reached": true,
  "message_write_mode": "READ_ONLY",
  "can_read_history": true,
  "parent_required": true,
  "message": "Ask your parent to unlock more Pratvim time."
}
```

Kid limit reached response:

```json
{
  "error_code": "KID_LIMIT_REACHED",
  "account_mode": "FREE_ACTIVE",
  "kid_limit_reached": true,
  "active_kids_count": 1,
  "max_kids_allowed": 1,
  "message": "Your current plan allows 1 kid profile. Upgrade to add more."
}
```

---

## 15. Mobile App Implementation Plan

The mobile frontend design is already implemented. App work should focus on wiring existing screens/components to backend state.

### 15.1 Recommended mobile feature structure

Use existing MVVM + UDF architecture.

```text
src/features/billing/
├── data/
│   ├── BillingApi.ts
│   ├── BillingRepository.ts
│   ├── PurchaseProvider.ts
│   └── BillingMappers.ts
├── domain/
│   ├── BillingModels.ts
│   ├── GetBillingEntitlementUseCase.ts
│   ├── GetUsageSummaryUseCase.ts
│   ├── GetPlansUseCase.ts
│   ├── GetCreditPacksUseCase.ts
│   ├── PurchaseSubscriptionUseCase.ts
│   ├── PurchaseCreditPackUseCase.ts
│   └── RestorePurchasesUseCase.ts
├── presentation/
│   ├── screens/
│   │   ├── SubscriptionPlansScreen.tsx
│   │   ├── UsageDashboardScreen.tsx
│   │   ├── AddCreditsScreen.tsx
│   │   ├── BillingHistoryScreen.tsx
│   │   └── PaymentProcessingScreen.tsx
│   ├── components/
│   │   ├── CreditMeter.tsx
│   │   ├── PlanCard.tsx
│   │   ├── CreditPackCard.tsx
│   │   ├── LowCreditBanner.tsx
│   │   └── ReadOnlyNotice.tsx
│   └── store/
│       ├── BillingState.ts
│       ├── BillingActions.ts
│       ├── BillingReducer.ts
│       └── BillingEffects.ts
```

Map these into existing app folders if names differ.

---

## 16. Mobile State Model

### 16.1 `BillingState`

```ts
export type AccountMode =
  | 'FREE_ACTIVE'
  | 'SUBSCRIPTION_ACTIVE'
  | 'BILLING_GRACE'
  | 'BILLING_BLOCKED';

export type MessageWriteMode = 'READ_WRITE' | 'READ_ONLY';

export type BillingState = {
  isLoading: boolean;
  accountMode: AccountMode;
  effectivePlan: {
    id: string;
    type: 'free' | 'paid';
    name: string;
    title?: string;
    subtitle?: string;
    description?: string;
    featureBullets: string[];
    badgeText?: string;
    ctaText?: string;
    priceDisplayText?: string;
    creditDisplayText?: string;
    kidsDisplayText?: string;
  };
  limits: {
    usageLimitReached: boolean;
    kidLimitReached: boolean;
    messageWriteMode: MessageWriteMode;
    canChat: boolean;
    canReadHistory: boolean;
    canAddChild: boolean;
    activeKidsCount: number;
    maxKidsAllowed: number;
  };
  features: {
    voiceEnabled: boolean;
    canBuySubscription: boolean;
    canBuyAddonCredits: boolean;
  };
  credits: {
    monthlyGranted: number;
    monthlyRemaining: number;
    addonRemaining: number;
    totalRemaining: number;
    usedPercent?: number;
    renewsAt?: string;
  };
  alerts: {
    lowCredit: boolean;
    usageLimitReached: boolean;
    kidLimitReached: boolean;
  };
  plans: BillingPlan[];
  creditPacks: CreditPack[];
  error?: string;
};
```

Do not include:

```text
allowedModelTier
modelTier
modelKey
```

---

### 16.2 Billing actions

```ts
export type BillingAction =
  | { type: 'BILLING_LOAD_REQUESTED' }
  | { type: 'BILLING_LOAD_SUCCEEDED'; payload: BillingEntitlement }
  | { type: 'BILLING_LOAD_FAILED'; error: string }
  | { type: 'PLANS_LOAD_SUCCEEDED'; payload: BillingPlan[] }
  | { type: 'CREDIT_PACKS_LOAD_SUCCEEDED'; payload: CreditPack[] }
  | { type: 'PURCHASE_STARTED'; productId: string }
  | { type: 'PURCHASE_SUCCEEDED' }
  | { type: 'PURCHASE_FAILED'; error: string }
  | { type: 'RESTORE_PURCHASES_SUCCEEDED' }
  | { type: 'CHAT_BILLING_UPDATED'; payload: ChatBillingUpdate }
  | { type: 'PLAN_USAGE_LIMIT_REACHED'; payload: BillingLimitPayload }
  | { type: 'KID_LIMIT_REACHED'; payload: BillingLimitPayload };
```

---

## 17. Mobile Screen Wiring

### 17.1 Parent dashboard

On parent dashboard load:

1. Call `GET /v1/billing/entitlement`.
2. Call `GET /v1/billing/usage-summary`.
3. Show usage meter from backend credits.
4. Show free plan card/content from backend.
5. Show paid plan CTA if `account_mode = FREE_ACTIVE`.
6. Show add credit CTA only when `features.canBuyAddonCredits = true`.
7. Show kid limit prompt if `limits.kidLimitReached = true`.

UI state logic:

| Backend state | Parent dashboard behavior |
|---|---|
| `FREE_ACTIVE`, `usage_limit_reached=false` | Show free meter and upgrade CTA |
| `FREE_ACTIVE`, `usage_limit_reached=true` | Show free limit reached message and subscribe CTA |
| `SUBSCRIPTION_ACTIVE`, `usage_limit_reached=false` | Show current plan, usage, add credits, upgrade |
| `SUBSCRIPTION_ACTIVE`, `usage_limit_reached=true` | Show add credits / upgrade CTA |
| `kid_limit_reached=true` | Show upgrade CTA to add more kids |

---

### 17.2 Kid chat screen

Before enabling composer:

1. Load entitlement.
2. Check `limits.canChat`.
3. Check `limits.messageWriteMode`.
4. If `canChat = true`, show normal composer.
5. If `canChat = false` and `canReadHistory = true`, show read-only composer.

Pseudo-code:

```ts
if (!billing.limits.canChat && billing.limits.canReadHistory) {
  return <ReadOnlyComposer onAskParent={openParentGate} />;
}

return <ChatComposer />;
```

Do not rely only on `accountMode`.

---

### 17.3 On chat send

After `POST /v1/chat`:

1. If success, append AI response.
2. Update billing state from `response.billing`.
3. If `PLAN_USAGE_LIMIT_REACHED`, switch kid UI to read-only.
4. If safety response is returned, display it even if usage limit is reached.

Pseudo-code:

```ts
const response = await chatApi.sendMessage(input);

if (response.error_code === 'PLAN_USAGE_LIMIT_REACHED') {
  dispatch({
    type: 'PLAN_USAGE_LIMIT_REACHED',
    payload: mapLimitResponse(response),
  });
  showReadOnlyMode();
  return;
}

if (response.message) {
  appendMessage(response.message);
}

dispatch({
  type: 'CHAT_BILLING_UPDATED',
  payload: response.billing,
});
```

---

### 17.4 Add kid flow

Before allowing parent to create another kid profile:

1. Call entitlement or use latest billing state.
2. Check `limits.canAddChild`.
3. If false, show plan upgrade message.
4. If true, continue existing child creation flow.

Pseudo-code:

```ts
if (!billing.limits.canAddChild) {
  showKidLimitReachedModal({
    activeKidsCount: billing.limits.activeKidsCount,
    maxKidsAllowed: billing.limits.maxKidsAllowed,
  });
  return;
}

navigateToCreateKidProfile();
```

Backend must still enforce the limit.

---

### 17.5 Subscription plans screen

On screen open:

1. Call `GET /v1/billing/plans`.
2. Render existing plan cards using backend content.
3. On select plan, call native purchase provider.
4. On purchase success, send receipt/token to backend.
5. Refresh entitlement.
6. Navigate to parent dashboard or payment confirmation screen.

---

### 17.6 Add credits screen

On screen open:

1. Call `GET /v1/billing/credit-packs`.
2. If eligible, show packs using backend content.
3. If not eligible, show subscription CTA.
4. On pack purchase, verify purchase with backend.
5. Refresh entitlement.

---

### 17.7 Restore purchases screen

Action:

1. Trigger native restore.
2. Send restored transaction data to backend.
3. Call `POST /v1/billing/restore`.
4. Refresh entitlement.

---

## 18. Mobile Navigation Flow

### 18.1 Free user first-time flow

```text
Parent onboarding
→ Parent dashboard
→ account_mode = FREE_ACTIVE
→ Kid can chat while usage_limit_reached = false
→ Credits finish
→ account_mode remains FREE_ACTIVE
→ usage_limit_reached = true
→ Kid read-only message mode
→ Parent subscription screen
→ Purchase subscription
→ account_mode = SUBSCRIPTION_ACTIVE
→ usage_limit_reached = false
→ Kid chat unlocked
```

---

### 18.2 Cancelled paid subscription flow

```text
Paid subscription cancelled/expired
→ Backend falls back to default Free Plan
→ account_mode = FREE_ACTIVE
→ Free plan credits/limits apply
→ Kids allowed limit applies from Free Plan config
→ Parent sees upgrade CTA
```

---

### 18.3 Paid user limit reached flow

```text
Kid sends message
→ Backend checks entitlement
→ Paid monthly credits exhausted
→ Add-on credits unavailable
→ account_mode remains SUBSCRIPTION_ACTIVE
→ usage_limit_reached = true
→ message_write_mode = READ_ONLY
→ Kid sees Ask Parent
→ Parent PIN gate
→ Add Credits / Upgrade Plan
→ Purchase success
→ Entitlement refresh
→ Kid chat unlocked
```

---

### 18.4 Existing parent billing flow

```text
Parent Dashboard
→ Billing / Usage
→ View credits
→ Manage Plan
→ Add Credits
→ Billing History
→ Restore Purchases
```

---

## 19. Parent PIN / Gate Rule

Payment screens must never be accessible directly from the kid area.

When kid taps **Ask Parent**:

1. Open parent gate / PIN screen.
2. After parent verification, navigate to parent billing screen.
3. Show subscription or add credit options depending on entitlement.

Pseudo-flow:

```text
Kid Read-only Screen
→ Ask Parent
→ Parent PIN
→ Billing Screen
```

---

## 20. Backend Chat Enforcement

Backend must be the final authority.

Mobile checks are only UX helpers. Backend must enforce:

- subscription status
- default free plan fallback
- free plan credit limit
- paid plan credit limit
- kids allowed limit
- add-on credit eligibility
- voice entitlement
- read-only message mode
- safety exception

Pseudo-code:

```ts
async function handleChatRequest(request) {
  const entitlement = await billingEntitlementService.getEntitlement(request.familyAccountId);

  // Safety always runs, even if plan limit is reached.
  const safety = await safetyService.classify(request.message, request.context);

  if (!entitlement.limits.canChat) {
    if (safety.isSafetyCritical) {
      return generateSafetyResponse({
        request,
        safety,
        chargeCredits: false,
        notifyParentIfRequired: true,
      });
    }

    return planUsageLimitReachedResponse(entitlement);
  }

  const reservation = await walletService.reserveCredits({
    familyAccountId: request.familyAccountId,
    estimatedCredits: request.estimatedCredits,
    requestId: request.requestId,
  });

  try {
    const aiResponse = await chatService.generate(request);
    const usage = await usageMeteringService.calculate(aiResponse.usage);

    await walletService.finalizeDebit({
      reservationId: reservation.id,
      actualCredits: usage.credits,
      usageEventId: usage.id,
    });

    await familyPlanStateEvaluator.evaluate(request.familyAccountId);

    return successResponse(aiResponse, usage);
  } catch (error) {
    await walletService.releaseReservation(reservation.id);
    throw error;
  }
}
```

---

## 21. Purchase Integration Recommendation

### 21.1 Recommended MVP option

Use a purchase abstraction layer:

```text
Mobile App → PurchaseProvider → App Store / Play Store
Mobile App → Backend Verify Purchase
Backend → Subscription/Credit Wallet Update
```

If using RevenueCat:

```text
Mobile App → RevenueCat SDK
RevenueCat → App Store / Play Store
RevenueCat Webhook → Backend
Backend → Entitlement + Credit Wallet
```

RevenueCat can reduce complexity for cross-platform subscriptions, restore purchases, subscription status, and webhooks.

---

### 21.2 Backend should still keep own entitlement

Even if RevenueCat is used, Pratvim backend should keep its own:

- subscriptions table
- family billing state table
- wallet table
- ledger table
- usage events
- entitlement API

Reason:

```text
RevenueCat manages purchase state.
Pratvim backend manages credits, usage, read-only mode, kids limits, and safety exceptions.
```

---

## 22. Idempotency Rules

All billing operations must be idempotent.

Use idempotency keys for:

- subscription activation
- subscription renewal
- subscription cancellation
- free monthly credit grant
- add-on credit grant
- refund
- credit adjustment
- credit debit
- reservation release

Example:

```text
apple:transaction_id:product_id
android:purchase_token:product_id
revenuecat:event_id
free_monthly:family_id:period
paid_monthly:subscription_id:period
chat:request_id:usage_debit
```

Never grant credits twice for the same purchase or monthly cycle.

---

## 23. Notifications

### 23.1 Parent notifications

| Trigger | Message |
|---|---|
| 20% credits left | Credits are running low. Add more or upgrade to avoid interruption. |
| Usage limit reached on free plan | Free monthly credits are used. Subscribe to continue chatting. |
| Usage limit reached on paid plan | Monthly credits are used. Add credits to continue. |
| Kid limit reached | Your current plan has reached the kid profile limit. Upgrade to add more. |
| Subscription renewal | Monthly credits have refreshed. |
| Payment failed | Payment could not be completed. Update billing to keep Pratvim active. |

### 23.2 Kid messages

Keep kid messages simple and non-commercial.

Use:

```text
Ask your parent to unlock more Pratvim time.
```

Avoid:

```text
Payment failed
Buy subscription
Your plan expired
Billing issue
```

---

## 24. Billing History

Parent should see simple billing history.

Items:

- Plan purchase
- Plan renewal
- Add-on credit purchase
- Credit adjustment
- Refund if applicable

Do not show token-level usage events to parents in MVP.

Admin can see detailed usage events.

---

## 25. Implementation Phases

## Phase 1: Backend Foundation

### Tasks

1. Add database tables:
   - `plans`
   - `family_billing_state`
   - `subscriptions`
   - `credit_packs`
   - `store_products`
   - `credit_buckets`
   - `credit_ledger`
   - `rate_cards`
   - `rate_card_items`
   - `usage_events`
2. Seed default Free Plan.
3. Seed Basic, Plus, Family plans.
4. Implement Billing Entitlement Service.
5. Implement Family Plan State Evaluator.
6. Implement Credit Wallet Service.
7. Implement Rate Card Service.
8. Implement Usage Metering Service.
9. Implement monthly free credit grant job.
10. Implement monthly paid credit grant job.

### Acceptance criteria

- New family without subscription gets `account_mode = FREE_ACTIVE`.
- Cancelled paid user falls back to `account_mode = FREE_ACTIVE`.
- Free credits are consumed correctly.
- Free credit exhaustion sets `usage_limit_reached = true` without changing `account_mode`.
- Paid credit exhaustion sets `usage_limit_reached = true` without changing `account_mode`.
- Kids limit is controlled by admin plan config.
- Plan content is returned from backend.
- Ledger records all grants and debits.

---

## Phase 2: Admin Billing Panel

### Tasks

Under **Admin → Billing**, implement:

1. Billing Overview
2. Plans
3. Free Plan
4. Credit Packs
5. Rate Cards
6. Subscriptions
7. Family Wallets
8. Usage Events
9. Credit Ledger
10. Adjustments
11. Store Products
12. Billing Alerts
13. Reports
14. Billing Settings

### Acceptance criteria

- Admin can configure free monthly credits.
- Admin can configure kids allowed for Free Plan.
- Admin can configure kids allowed for each paid plan.
- Admin can configure paid plan content shown in mobile.
- Admin can configure credit pack content shown in mobile.
- Admin can configure global usage-type rates.
- Admin can activate a new rate card version.
- Admin can view wallet and ledger for each family.
- Admin can manually adjust credits with reason.
- No Model Catalog page exists in Billing for MVP.
- No model tier/variation fields exist in plan setup.

---

## Phase 3: Mobile Billing Wiring

### Tasks

1. Add billing API client.
2. Add billing repository.
3. Add billing state/reducer/effects.
4. Wire parent dashboard credit meter.
5. Wire subscription screen to backend plan content.
6. Wire add credits screen to backend credit pack content.
7. Wire kid chat screen to `limits.canChat` and `limits.messageWriteMode`.
8. Add read-only message behavior.
9. Wire add-kid flow to `limits.canAddChild`.
10. Add parent PIN gate before billing actions from kid flow.
11. Add restore purchase flow.

### Acceptance criteria

- Parent sees free credits remaining.
- Parent sees paid plan usage.
- Parent sees plan copy from backend.
- Kid can chat when `limits.canChat = true`.
- Kid cannot send normal messages when `limits.canChat = false`.
- Kid can still read old messages in read-only mode.
- Parent can navigate to subscription screen when free usage limit is reached.
- Paid parent can navigate to add credits when usage limit is reached.
- Parent cannot add more kids when `limits.canAddChild = false`.

---

## Phase 4: Purchase Integration

### Tasks

1. Configure App Store subscription products.
2. Configure Play Store subscription products.
3. Configure consumable credit packs.
4. Implement mobile purchase provider.
5. Implement backend purchase verification.
6. Implement restore purchase flow.
7. Implement purchase webhooks if using RevenueCat.
8. Implement idempotent credit grants.
9. Re-evaluate `family_billing_state` after every purchase event.

### Acceptance criteria

- Subscription purchase activates plan.
- Monthly credits are granted after subscription activation.
- Add-on credit purchase grants correct credits.
- Duplicate purchase events do not duplicate credits.
- Restore purchase refreshes entitlement.
- Cancelled subscription falls back to Free Active.

---

## Phase 5: Chat Metering Enforcement

### Tasks

1. Add safety classification before billing block.
2. Add pre-chat entitlement check.
3. Add credit reservation before normal generation.
4. Add actual usage metering after AI response.
5. Add ledger debit after usage calculation.
6. Add reservation release on failure.
7. Add usage limit reached response.
8. Add safety response path for zero credits / read-only mode.

### Acceptance criteria

- Credits are charged based on actual usage.
- Concurrent chats do not overspend wallet.
- Failed model calls do not consume credits.
- Usage-limit users are blocked from normal chat.
- Safety-critical messages still receive safe handling.
- Safety classifier is not disabled by any plan state.

---

## Phase 6: Notifications and Reporting

### Tasks

1. Add low-credit notification.
2. Add usage-limit reached notification.
3. Add kid-limit reached notification.
4. Add renewal notification.
5. Add failed payment notification.
6. Add billing reports.
7. Add free-to-paid conversion report.

### Acceptance criteria

- Parent receives useful alerts.
- Kids do not receive payment-related alerts.
- Admin can track conversion, usage, kid-limit reached, and usage-limit reached.

---

## 26. Testing Plan

### 26.1 Free plan tests

| Scenario | Expected result |
|---|---|
| New parent signs up | `account_mode = FREE_ACTIVE`, free monthly credits granted |
| Kid sends message | Credits deducted |
| Free credits reach zero | `usage_limit_reached = true`, `message_write_mode = READ_ONLY` |
| Account mode after free credits reach zero | Still `FREE_ACTIVE` |
| Parent subscribes | `account_mode = SUBSCRIPTION_ACTIVE`, paid credits granted |
| Paid subscription cancelled | Account falls back to `FREE_ACTIVE` |
| Monthly reset occurs | Free credits refreshed for non-paid account |

### 26.2 Kids limit tests

| Scenario | Expected result |
|---|---|
| Free plan allows 1 kid, parent adds first kid | Success |
| Free plan allows 1 kid, parent adds second kid | `KID_LIMIT_REACHED` |
| Admin changes Free Plan max kids to 2 | Parent can add second kid after entitlement refresh |
| Paid Plus allows 2 kids | Parent can add up to 2 kids |
| Subscription cancelled and family has 2 kids but Free allows 1 | Existing profiles remain; extra access follows downgrade rule; no new kids allowed |

### 26.3 Paid subscription tests

| Scenario | Expected result |
|---|---|
| Parent buys Basic plan | Subscription active, credits granted |
| Monthly credits exhausted | Add-on credits used if available |
| No add-on credits | `usage_limit_reached = true`, read-only normal chat |
| Parent buys add-on pack | `usage_limit_reached = false`, kid unlocked |
| Renewal occurs | Monthly credits refreshed |
| Payment fails | Grace/block rules applied, or fallback when expired |

### 26.4 Safety tests

| Scenario | Expected result |
|---|---|
| Free usage limit reached and kid sends normal message | Normal chat blocked, read-only response returned |
| Free usage limit reached and kid sends high-risk message | Safety response returned |
| Paid usage limit reached and kid sends high-risk message | Safety response returned |
| Billing blocked but safety-critical event detected | Safety workflow still runs as per policy |

### 26.5 Ledger tests

| Scenario | Expected result |
|---|---|
| Grant free credits | Ledger has grant event |
| Debit chat usage | Ledger has debit event |
| Failed chat | Reservation released |
| Duplicate purchase webhook | No duplicate grant |
| Admin adjustment | Ledger has adjustment with reason |

### 26.6 Mobile UI tests

| Scenario | Expected result |
|---|---|
| `FREE_ACTIVE` + `usage_limit_reached=false` | Chat composer visible |
| `FREE_ACTIVE` + `usage_limit_reached=true` | Read-only composer visible |
| `SUBSCRIPTION_ACTIVE` + `usage_limit_reached=false` | Chat composer visible |
| `SUBSCRIPTION_ACTIVE` + `usage_limit_reached=true` | Ask Parent button visible |
| `kid_limit_reached=true` | Add kid flow shows upgrade prompt |
| Parent PIN success | Billing screen opens |
| Parent PIN fail | Billing screen blocked |

---

## 27. Security and Abuse Controls

### 27.1 Free plan abuse prevention

Recommended controls:

- Require verified parent email or phone before free usage.
- Limit one free plan per parent account.
- Track repeated signup patterns.
- Track repeated device/account abuse signals.
- Use admin-configured kids limit.
- Voice off for Free Plan unless business approves it.

---

### 27.2 Admin security

- Billing admin actions should be RBAC-protected.
- Credit adjustment should require reason.
- Large adjustment should require approval.
- Rate card activation should be audited.
- Store product changes should be audited.
- Plan content changes should be audited.
- Kids limit changes should be audited.
- Ledger should be immutable.

---

## 28. Important Implementation Decisions

### Decision 1

Use credits as parent-facing unit, not tokens.

### Decision 2

Keep all billing configuration under Admin → Billing.

### Decision 3

Free Plan is the default entitlement for all non-paid users.

### Decision 4

Cancelled/expired paid users fall back to `FREE_ACTIVE`.

### Decision 5

Do not change account mode when limits are reached.

### Decision 6

Use `usage_limit_reached`, `kid_limit_reached`, and `message_write_mode` for limits.

### Decision 7

Kids allowed is admin-configurable for every plan.

### Decision 8

Plan card content is backend-owned.

### Decision 9

No model variation, model tiers, or model catalog in MVP billing.

### Decision 10

Safety is always enabled and never compromised by billing state.

### Decision 11

Monthly credits and add-on credits must be separate buckets.

### Decision 12

Use an immutable credit ledger.

### Decision 13

Backend is the source of truth for all entitlement and credit decisions.

### Decision 14

Mobile app should only display billing state and trigger purchases.

---

## 29. Final Recommended Rule Set

```text
Every parent account always has a billing entitlement.

If there is no active paid subscription:
    Use default Free Plan.
    account_mode = FREE_ACTIVE.

If a paid subscription is cancelled or expired:
    Fall back to default Free Plan.
    account_mode = FREE_ACTIVE.

If free credits are available:
    usage_limit_reached = false.
    message_write_mode = READ_WRITE.
    Kid can chat normally.

If free credits are exhausted:
    account_mode remains FREE_ACTIVE.
    usage_limit_reached = true.
    message_write_mode = READ_ONLY.
    Kid can read previous messages.
    Parent is prompted to subscribe.

If paid subscription is active:
    account_mode = SUBSCRIPTION_ACTIVE.
    Use paid monthly credits first.

If paid monthly credits are exhausted:
    Use add-on credits if available.

If no usable credits remain:
    account_mode does not change.
    usage_limit_reached = true.
    message_write_mode = READ_ONLY.
    Parent can buy add-on credits or upgrade plan.

If active kids count reaches plan max kids:
    kid_limit_reached = true.
    can_add_child = false.
    Parent is prompted to upgrade.

If the message is safety-critical:
    Safety classifier and safe response workflow always run.
    Billing must not block safety.

Admin controls plans, free credits, kids allowed, plan content, credit packs, rate cards, usage rules, and ledger adjustments under Billing.
```

---

## 30. MVP Checklist

### Backend

- [ ] Plans table with backend-owned plan content
- [ ] Default Free Plan support
- [ ] Family billing state table
- [ ] Usage limit reached flag
- [ ] Kid limit reached flag
- [ ] Subscription support
- [ ] Credit packs
- [ ] Credit buckets
- [ ] Credit ledger
- [ ] Global rate cards
- [ ] Usage events
- [ ] Entitlement API
- [ ] Usage summary API
- [ ] Plans API returning content
- [ ] Credit packs API returning content
- [ ] Purchase verification API
- [ ] Chat credit enforcement
- [ ] Kids limit enforcement
- [ ] Monthly credit grant job
- [ ] Read-only message mode response
- [ ] Safety always-on flow

### Admin

- [ ] Billing menu
- [ ] Plans screen
- [ ] Free Plan screen
- [ ] Credit Packs screen
- [ ] Rate Cards screen
- [ ] Subscriptions screen
- [ ] Family Wallet screen
- [ ] Usage Events screen
- [ ] Credit Ledger screen
- [ ] Adjustments screen
- [ ] Store Products screen
- [ ] Reports screen
- [ ] Settings screen
- [ ] Plan content editor
- [ ] Kids allowed configuration
- [ ] No Model Catalog screen for MVP

### Mobile

- [ ] Billing API client
- [ ] Billing state management
- [ ] Parent dashboard credit meter
- [ ] Subscription screen wiring to backend content
- [ ] Add credit screen wiring to backend content
- [ ] Restore purchase flow
- [ ] Kid read-only message mode
- [ ] Ask Parent flow
- [ ] Parent PIN gate
- [ ] Add kid limit handling
- [ ] Chat billing response handling
- [ ] Low credit alerts

---

## 31. Suggested Implementation Order

1. Update database schema and seed Free Plan.
2. Add `family_billing_state` and evaluator.
3. Build entitlement API.
4. Build credit wallet and ledger.
5. Build free plan monthly grant.
6. Build kids allowed enforcement.
7. Build admin Billing screens.
8. Wire mobile parent dashboard to entitlement API.
9. Wire mobile plan cards to backend plan content.
10. Wire kid read-only message mode.
11. Add purchase integration.
12. Add usage metering and chat debit.
13. Add safety-always-on path.
14. Add notifications and reports.
15. Run end-to-end QA.
16. Release with conservative plan values first.

---

## 32. End-to-End Examples

### 32.1 New free user

```text
Parent creates account
→ Backend assigns default Free Plan
→ account_mode = FREE_ACTIVE
→ Backend grants 10 free credits
→ Kid sends message
→ Backend charges 1 credit
→ Remaining credits = 9
→ usage_limit_reached = false
```

---

### 32.2 Free user reaches usage limit

```text
Free credits reach 0
→ account_mode remains FREE_ACTIVE
→ usage_limit_reached = true
→ message_write_mode = READ_ONLY
→ Kid can read old messages
→ Kid cannot send normal new messages
→ Parent sees Subscribe CTA
```

---

### 32.3 Paid subscription cancelled

```text
Parent cancels Plus plan
→ Subscription expires at period end
→ Backend falls back to default Free Plan
→ account_mode = FREE_ACTIVE
→ Free Plan credits and kids limit apply
→ Parent sees upgrade CTA
```

---

### 32.4 Parent subscribes

```text
Parent buys Plus plan
→ Backend verifies purchase
→ Subscription active
→ account_mode = SUBSCRIPTION_ACTIVE
→ Backend grants 50,000 monthly credits
→ usage_limit_reached = false
→ Kid chat unlocked
```

---

### 32.5 Paid user buys add-on credits

```text
Monthly credits exhausted
→ Add-on credits unavailable
→ usage_limit_reached = true
→ Parent buys Medium Pack
→ Backend grants 50,000 add-on credits
→ usage_limit_reached = false
→ Kid chat unlocked
→ Add-on credits do not reset monthly
```

---

### 32.6 Kid limit reached

```text
Free Plan allows 1 kid
→ Parent already has 1 kid profile
→ Parent tries to add second kid
→ Backend returns KID_LIMIT_REACHED
→ account_mode remains FREE_ACTIVE
→ kid_limit_reached = true
→ Parent sees upgrade CTA
```

---

### 32.7 Safety after usage limit

```text
Free credits are 0
→ usage_limit_reached = true
→ Kid sends safety-critical message
→ Backend runs safety classifier
→ Backend returns safe response
→ Parent safety workflow runs if required
→ Normal billing does not block safety
```

---

## 33. Final Architecture Summary

```text
Mobile App
  ↓
Billing APIs
  ↓
Billing Entitlement Service
  ↓
Family Billing State Evaluator
  ↓
Credit Wallet + Ledger
  ↓
Global Rate Card + Usage Metering
  ↓
Chat / Voice / Safety Services
  ↓
Admin Billing Console
```

The clean separation is:

```text
Admin configures billing rules and plan content.
Backend enforces billing rules.
Backend always preserves safety behavior.
Mobile displays billing state and backend-provided content.
Parent pays and manages plans.
Kid only sees safe, simple access states.
```
