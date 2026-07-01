# Pratvim Subscriptions & Billing Implementation Plan

**File:** `subscriptions-and-billing-implementation-plan.md`  
**Product:** Pratvim Mobile App  
**Primary users:** Parents and kids  
**Admin module:** Billing  
**Scope:** Free monthly plan, paid monthly subscriptions, monthly credit limits, add-on credits, token/credit metering, kid read-only mode, mobile app integration, backend/admin implementation.

---

## 1. Objective

Pratvim needs a billing and subscription system where:

1. Every parent account gets a configurable **Free Monthly Plan** if they do not have an active paid subscription.
2. Paid subscriptions provide monthly credits based on the selected plan.
3. Credits are consumed based on AI usage, including input tokens, output tokens, cached tokens, voice usage, and model type.
4. Admin can configure credit conversion rules under the **Billing** section.
5. If credits are exhausted, kids should not see payment screens. Their account should move into **read-only mode** for previous messages.
6. Parents can upgrade to a subscription or buy add-on credits depending on account state.
7. All billing configuration, plans, rate cards, credit packs, usage, and ledger views should come under **Admin Panel → Billing**.
8. The mobile app frontend is already designed, so implementation should wire existing UI screens/states to backend APIs and billing logic without redesigning the app.

---

## 2. Core Product Rules

### 2.1 Parent-facing language

Do not show raw tokens to parents.

Use:

- **Credits**
- **Monthly Credits**
- **Add-on Credits**
- **Free Credits**
- **Credits Remaining**

Avoid exposing:

- input tokens
- output tokens
- cached tokens
- model cost
- provider cost

These should remain internal/admin concepts.

---

## 3. Account Modes

Every family account should always have one clear account mode.

```ts
type AccountMode =
  | 'FREE_ACTIVE'
  | 'FREE_EXHAUSTED_READ_ONLY'
  | 'SUBSCRIPTION_ACTIVE'
  | 'SUBSCRIPTION_EXHAUSTED'
  | 'NO_CREDITS_READ_ONLY'
  | 'BILLING_GRACE'
  | 'BILLING_BLOCKED';
```

### 3.1 Mode behavior

| Account mode | Can kid chat? | Can kid read old messages? | Can parent subscribe? | Can parent buy add-on credits? |
|---|---:|---:|---:|---:|
| `FREE_ACTIVE` | Yes | Yes | Yes | No |
| `FREE_EXHAUSTED_READ_ONLY` | No | Yes | Yes | No |
| `SUBSCRIPTION_ACTIVE` | Yes | Yes | Yes, upgrade/downgrade | Yes |
| `SUBSCRIPTION_EXHAUSTED` | Only if add-on credits exist | Yes | Yes | Yes |
| `NO_CREDITS_READ_ONLY` | No | Yes | Yes | Depends on paid status |
| `BILLING_GRACE` | Yes, limited | Yes | Yes | Yes |
| `BILLING_BLOCKED` | No | Yes | Yes | Depends on paid status |

---

## 4. Free Monthly Plan

### 4.1 Free plan rule

If a parent has no active paid subscription, the account automatically uses the Free Monthly Plan.

Example:

```text
Free Plan = 10 credits/month
```

This value must be configurable from admin.

### 4.2 Free plan restrictions

Recommended MVP restrictions:

| Feature | Free plan behavior |
|---|---|
| Monthly credits | Admin configurable, default 10 |
| Kids allowed | 1 |
| Voice input | Disabled |
| Voice output | Disabled |
| Model tier | Basic / lowest-cost kid-safe model |
| Add-on credits | Not allowed until subscription is active |
| History access | Allowed |
| New chat after exhaustion | Blocked |
| Safety-critical response | Allowed in limited form |

### 4.3 Free plan exhaustion

When free monthly credits reach zero:

- Kid can read previous chats.
- Kid cannot send new normal messages.
- Kid sees soft read-only messaging.
- Parent sees upgrade prompt.
- Parent can buy a paid subscription.
- Add-on credits should not be offered to free users in MVP.

---

## 5. Paid Subscriptions

### 5.1 Paid plan examples

Admin should be able to configure these from Billing.

| Plan | Included monthly credits | Kids allowed | Voice | Model tier |
|---|---:|---:|---:|---|
| Basic | 10,000 | 1 | No | Basic |
| Plus | 50,000 | 2 | Yes | Standard |
| Family | 150,000 | 4 | Yes | Standard/Premium |

Actual plan names, credit values, prices, and limits should be admin configurable.

### 5.2 Subscription behavior

A paid subscription gives:

1. Monthly access.
2. Monthly included credits.
3. Feature entitlements such as voice, number of kids, and model tier.
4. Ability to buy add-on credit packs.

### 5.3 Subscription monthly reset

On each successful renewal:

1. Expire old monthly subscription credit bucket.
2. Create new monthly subscription credit bucket.
3. Preserve add-on credit balance.
4. Update subscription billing period.
5. Refresh entitlement.
6. Notify parent if required.

---

## 6. Add-on Credits

### 6.1 Add-on credit rule

Add-on credits are extra credits bought by parents when subscription credits are low or exhausted.

Recommended MVP rule:

```text
Only paid subscribers can buy add-on credits.
```

This keeps the monetization model simple:

```text
Free user exhausted → subscribe first.
Paid user exhausted → buy add-on credits or upgrade plan.
```

### 6.2 Add-on credit behavior

| Rule | Behavior |
|---|---|
| Purchase type | Consumable in-app product |
| Expiry | No expiry recommended |
| Reset monthly | No |
| Used before monthly credits? | No |
| Used after monthly credits? | Yes |
| Refund support | Ledger adjustment required |

### 6.3 Credit pack examples

| Pack | Credits |
|---|---:|
| Small Pack | 10,000 |
| Medium Pack | 50,000 |
| Large Pack | 150,000 |

Pack amount, product IDs, status, and mapping should be configurable under **Admin → Billing → Credit Packs**.

---

## 7. Credit Consumption Priority

Credits should be consumed in this order:

1. Free monthly credits, only for free accounts.
2. Paid monthly subscription credits.
3. Promotional credits, if configured.
4. Add-on purchased credits.
5. Admin adjustment credits.

For paid accounts, free monthly credits should not be granted in the same period.

---

## 8. Read-only Mode

### 8.1 Kid read-only behavior

When credits are exhausted, kids should enter read-only mode.

Allowed:

- View previous conversations.
- Open old AI responses.
- Scroll chat history.
- Read saved content.
- Ask parent to unlock.

Blocked:

- Send a new normal message.
- Generate a new AI answer.
- Start voice chat.
- Upload new voice input.
- Use premium AI features.

### 8.2 Kid-facing message

Use soft, non-commercial wording:

```text
Your free Pratvim messages for this month are finished. You can still read your old chats. Ask your parent to unlock more Pratvim time.
```

For paid users with no credits:

```text
Pratvim needs a quick refill from your parent to continue. You can still read your old chats.
```

### 8.3 Parent-facing message

For free exhausted:

```text
Free monthly credits are used. Subscribe to keep Pratvim active for your kid.
```

For paid exhausted:

```text
Monthly credits are used. Add extra credits or upgrade your plan to continue chatting.
```

---

## 9. Safety Exception

Pratvim is a child-safe AI product. Safety should not be completely blocked by billing.

### 9.1 Rule

If the child sends a high-risk message after credits are exhausted, allow a limited safety response.

High-risk categories may include:

- self-harm
- grooming
- blackmail
- coercion
- abuse
- bullying escalation
- unsafe meeting request
- immediate danger

### 9.2 Backend rule

```ts
if (creditsRemaining <= 0) {
  const risk = await lightweightClassifier(message);

  if (risk.isHighRisk) {
    return allowLimitedSafetyResponse({
      maxOutputTokens: 100,
      chargeCredits: false,
      notifyParentIfRequired: true,
    });
  }

  return blockNormalChatAndEnableReadOnly();
}
```

### 9.3 Important implementation note

Do not run a full expensive response when no credits are available unless the message is safety-critical. Use a short safety response and parent alert logic.

---

## 10. Admin Panel Structure

All subscription and credit settings should come under:

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
├── Model Catalog
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

### 10.2 Billing → Overview

Purpose: show operational billing summary.

Metrics:

- Active subscriptions
- Free accounts
- Free exhausted accounts
- Paid exhausted accounts
- Add-on credits sold
- Credits consumed today
- Monthly recurring revenue
- Failed renewals
- Billing grace accounts
- Top models by credit consumption

### 10.3 Billing → Plans

Admin can configure paid plans.

Fields:

| Field | Description |
|---|---|
| Plan name | Basic, Plus, Family |
| Plan type | Paid |
| Included monthly credits | Credits granted every billing cycle |
| Monthly price | Display/reference price |
| App Store product ID | iOS subscription product ID |
| Play Store product ID | Android subscription product ID |
| Max kids | Number of kid profiles allowed |
| Voice enabled | Yes/No |
| Allowed model tier | Basic/Standard/Premium |
| Status | Active/Inactive |
| Sort order | Display ordering |

### 10.4 Billing → Free Plan

Admin can configure free monthly access.

Fields:

| Field | Description |
|---|---|
| Free monthly credits | Default 10 |
| Reset frequency | Monthly |
| Max kids | Usually 1 |
| Voice enabled | Usually No |
| Model tier | Basic |
| Read-only after exhaustion | Yes |
| Safety override enabled | Yes |
| Require verified parent email/phone | Recommended |
| Status | Active/Inactive |

### 10.5 Billing → Credit Packs

Admin can configure add-on packs.

Fields:

| Field | Description |
|---|---|
| Pack name | Small/Medium/Large |
| Credit amount | Number of credits granted |
| App Store product ID | iOS consumable product ID |
| Play Store product ID | Android consumable product ID |
| Eligible plans | Which paid plans can buy this |
| Status | Active/Inactive |
| Sort order | Display ordering |

### 10.6 Billing → Model Catalog

Admin can manage model billing metadata.

Fields:

| Field | Description |
|---|---|
| Provider | OpenAI, local, custom, etc. |
| Model key | Internal model identifier |
| Display name | Admin-friendly name |
| Tier | Basic/Standard/Premium |
| Supports text | Yes/No |
| Supports cached input | Yes/No |
| Supports voice | Yes/No |
| Active | Yes/No |

### 10.7 Billing → Rate Cards

Admin configures credit conversion rules.

A rate card should be versioned.

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

Recommended internal-only items:

| Usage type | Recommendation |
|---|---|
| `SAFETY_CLASSIFIER_CALL` | Do not charge parent separately |
| `VALIDATOR_CALL` | Do not charge parent separately |
| `NORMALIZER_CALL` | Do not charge parent separately |

### 10.8 Billing → Subscriptions

Admin can view subscription state by family account.

Columns:

- Family account
- Parent name/email
- Plan
- Store
- Status
- Current period start
- Current period end
- Auto-renew status
- Renewal issue
- Created at

Actions:

- View subscription details
- View wallet
- View ledger
- Grant adjustment credits
- Mark internal note

Do not manually mark paid subscriptions active unless there is a controlled support process.

### 10.9 Billing → Family Wallets

Shows credit balances by family.

Columns:

- Family account
- Account mode
- Monthly credits remaining
- Add-on credits remaining
- Promo credits remaining
- Total credits remaining
- Next reset date
- Last usage date

Actions:

- View buckets
- View ledger
- Add adjustment
- Lock wallet if abuse detected

### 10.10 Billing → Usage Events

Shows AI usage events.

Columns:

- Date/time
- Family
- Kid profile
- Conversation
- Model
- Input tokens
- Cached tokens
- Output tokens
- Voice seconds
- Credits charged
- Request status

Filters:

- Date range
- Family
- Kid
- Plan
- Model
- Usage type
- High usage only

### 10.11 Billing → Credit Ledger

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

### 10.12 Billing → Adjustments

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

### 10.13 Billing → Store Products

Map internal plans/packs to iOS and Android product IDs.

Fields:

- Internal product ID
- Product type: subscription/consumable
- App Store product ID
- Play Store product ID
- Linked plan or credit pack
- Status
- Last verified date

### 10.14 Billing → Billing Alerts

Admin can configure alert thresholds.

Examples:

| Alert | Default |
|---|---:|
| Low credit warning | 20% remaining |
| Very low credit warning | 5% remaining |
| Free exhausted | Enabled |
| Paid exhausted | Enabled |
| Failed renewal | Enabled |
| High usage spike | Enabled |
| Repeated free account creation | Enabled |

### 10.15 Billing → Reports

Reports:

- Free to paid conversion
- Plan distribution
- Credit consumption by plan
- Credit consumption by model
- Add-on pack purchases
- Revenue estimate
- Usage by kid age band
- Usage by day/week/month
- Free plan abuse signals
- Exhaustion funnel

### 10.16 Billing → Settings

Global settings:

| Setting | Purpose |
|---|---|
| Credit display name | Credits / Pratvim Credits |
| Default currency | INR/USD/etc. |
| Grace period days | Billing grace behavior |
| Safety override enabled | Allow limited safety responses with zero credits |
| Free plan enabled | Turn free plan on/off |
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
  max_kids INT NOT NULL DEFAULT 1,
  voice_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  allowed_model_tier VARCHAR(30) NOT NULL DEFAULT 'basic',
  billing_period VARCHAR(20) NOT NULL DEFAULT 'monthly',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INT DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### 11.2 `store_products`

```sql
CREATE TABLE store_products (
  id UUID PRIMARY KEY,
  internal_product_key VARCHAR(120) UNIQUE NOT NULL,
  product_type VARCHAR(30) NOT NULL, -- subscription / consumable
  platform VARCHAR(30) NOT NULL, -- ios / android / web
  store_product_id VARCHAR(200) NOT NULL,
  plan_id UUID NULL REFERENCES plans(id),
  credit_pack_id UUID NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### 11.3 `credit_packs`

```sql
CREATE TABLE credit_packs (
  id UUID PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  credit_amount BIGINT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  eligible_plan_type VARCHAR(30) DEFAULT 'paid',
  sort_order INT DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### 11.4 `subscriptions`

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
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### 11.5 `credit_buckets`

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

### 11.6 `credit_ledger`

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

### 11.7 `model_catalog`

```sql
CREATE TABLE model_catalog (
  id UUID PRIMARY KEY,
  provider VARCHAR(100) NOT NULL,
  model_key VARCHAR(150) NOT NULL,
  display_name VARCHAR(150) NOT NULL,
  tier VARCHAR(30) NOT NULL, -- basic / standard / premium
  supports_text BOOLEAN NOT NULL DEFAULT TRUE,
  supports_voice BOOLEAN NOT NULL DEFAULT FALSE,
  supports_cached_input BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

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

### 11.9 `rate_card_items`

```sql
CREATE TABLE rate_card_items (
  id UUID PRIMARY KEY,
  rate_card_id UUID NOT NULL REFERENCES rate_cards(id),
  model_catalog_id UUID NOT NULL REFERENCES model_catalog(id),
  usage_type VARCHAR(50) NOT NULL,
  unit VARCHAR(50) NOT NULL,
  credits_per_unit BIGINT NOT NULL,
  min_charge_credits BIGINT DEFAULT 0,
  rounding_mode VARCHAR(20) DEFAULT 'ceil',
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### 11.10 `usage_events`

```sql
CREATE TABLE usage_events (
  id UUID PRIMARY KEY,
  family_account_id UUID NOT NULL,
  child_id UUID NULL,
  conversation_id UUID NULL,
  request_id VARCHAR(120) NOT NULL,
  model_catalog_id UUID NOT NULL REFERENCES model_catalog(id),
  rate_card_id UUID NOT NULL REFERENCES rate_cards(id),
  input_tokens BIGINT DEFAULT 0,
  cached_input_tokens BIGINT DEFAULT 0,
  output_tokens BIGINT DEFAULT 0,
  voice_input_seconds NUMERIC(12, 3) DEFAULT 0,
  voice_output_seconds NUMERIC(12, 3) DEFAULT 0,
  credits_charged BIGINT NOT NULL DEFAULT 0,
  provider_cost_estimate_minor BIGINT DEFAULT 0,
  status VARCHAR(30) NOT NULL, -- reserved / completed / failed / refunded
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

## 12. Backend Services

### 12.1 Billing Entitlement Service

Responsibility:

- Determine account mode.
- Determine whether child can chat.
- Determine whether child can use voice.
- Determine model tier.
- Determine whether parent can buy subscription/add-on credits.

Method:

```ts
getEntitlement(familyAccountId: string): BillingEntitlement
```

### 12.2 Credit Wallet Service

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

### 12.3 Usage Metering Service

Responsibility:

- Record model usage.
- Apply active rate card.
- Calculate credits.
- Create usage event.
- Link usage event to ledger debit.

### 12.4 Rate Card Service

Responsibility:

- Manage active rate card.
- Resolve model-specific rates.
- Support draft/active/archive workflow.
- Never modify active rate card in place. Create a new version.

### 12.5 Purchase Verification Service

Responsibility:

- Verify mobile purchases.
- Handle App Store / Play Store / RevenueCat events.
- Prevent duplicate credit grants.
- Activate/cancel subscriptions.
- Grant add-on credits.

### 12.6 Monthly Credit Job

Runs monthly or based on each account billing cycle.

Logic:

```ts
for each familyAccount:
  if hasActivePaidSubscription(familyAccount):
    grantPaidMonthlyCredits(familyAccount)
  else:
    grantFreeMonthlyCredits(familyAccount)
```

Important:

Do not grant free monthly credits to active paid subscribers.

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

Response: free active

```json
{
  "account_mode": "FREE_ACTIVE",
  "can_chat": true,
  "can_read_history": true,
  "can_use_voice": false,
  "can_buy_subscription": true,
  "can_buy_addon_credits": false,
  "allowed_model_tier": "basic",
  "credits": {
    "monthly_free_credits": 10,
    "monthly_remaining": 6,
    "addon_remaining": 0,
    "total_remaining": 6,
    "renews_at": "2026-08-01T00:00:00Z"
  }
}
```

Response: free exhausted

```json
{
  "account_mode": "FREE_EXHAUSTED_READ_ONLY",
  "can_chat": false,
  "can_read_history": true,
  "can_use_voice": false,
  "can_buy_subscription": true,
  "can_buy_addon_credits": false,
  "allowed_model_tier": "basic",
  "upgrade_required": true,
  "credits": {
    "monthly_free_credits": 10,
    "monthly_remaining": 0,
    "addon_remaining": 0,
    "total_remaining": 0,
    "renews_at": "2026-08-01T00:00:00Z"
  }
}
```

Response: paid active

```json
{
  "account_mode": "SUBSCRIPTION_ACTIVE",
  "can_chat": true,
  "can_read_history": true,
  "can_use_voice": true,
  "can_buy_subscription": true,
  "can_buy_addon_credits": true,
  "allowed_model_tier": "standard",
  "plan": {
    "id": "plan_plus",
    "name": "Plus",
    "status": "active",
    "renews_at": "2026-08-01T00:00:00Z"
  },
  "credits": {
    "monthly_plan_credits": 50000,
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
  "plan": {
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
  },
  "alerts": {
    "low_credit": true,
    "credit_exhausted": false
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
      "name": "Basic",
      "monthly_credits": 10000,
      "max_kids": 1,
      "voice_enabled": false,
      "store_product_id": "pratvim_basic_monthly",
      "recommended": false
    },
    {
      "id": "plus",
      "name": "Plus",
      "monthly_credits": 50000,
      "max_kids": 2,
      "voice_enabled": true,
      "store_product_id": "pratvim_plus_monthly",
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

Response:

```json
{
  "eligible": true,
  "packs": [
    {
      "id": "small_pack",
      "name": "Small Pack",
      "credits": 10000,
      "store_product_id": "credits_small_pack"
    },
    {
      "id": "medium_pack",
      "name": "Medium Pack",
      "credits": 50000,
      "store_product_id": "credits_medium_pack"
    }
  ]
}
```

For free users:

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
    "account_mode": "SUBSCRIPTION_ACTIVE"
  }
}
```

Credits exhausted response:

```json
{
  "error_code": "CREDITS_EXHAUSTED",
  "account_mode": "FREE_EXHAUSTED_READ_ONLY",
  "can_read_history": true,
  "parent_required": true,
  "message": "Ask your parent to unlock more Pratvim time."
}
```

---

## 15. Mobile App Implementation Plan

The mobile frontend design is already implemented, so the app work should be limited to wiring, state management, API integration, and conditional rendering.

### 15.1 Mobile architecture

Use existing MVVM + UDF style.

Recommended feature structure:

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

If the current project already has different folders, map these concepts into existing modules without changing the UI design.

---

## 16. Mobile State Model

### 16.1 `BillingState`

```ts
export type BillingState = {
  isLoading: boolean;
  accountMode: AccountMode;
  canChat: boolean;
  canReadHistory: boolean;
  canUseVoice: boolean;
  canBuySubscription: boolean;
  canBuyAddonCredits: boolean;
  allowedModelTier: 'basic' | 'standard' | 'premium';
  plan?: {
    id: string;
    name: string;
    status: string;
    renewsAt?: string;
  };
  credits: {
    monthlyGranted: number;
    monthlyRemaining: number;
    addonRemaining: number;
    totalRemaining: number;
    usedPercent: number;
    renewsAt?: string;
  };
  alerts: {
    lowCredit: boolean;
    creditExhausted: boolean;
  };
  plans: BillingPlan[];
  creditPacks: CreditPack[];
  error?: string;
};
```

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
  | { type: 'CHAT_BILLING_UPDATED'; payload: ChatBillingUpdate };
```

---

## 17. Mobile Screen Wiring

### 17.1 Parent dashboard

On parent dashboard load:

1. Call `GET /v1/billing/entitlement`.
2. Call `GET /v1/billing/usage-summary`.
3. Show usage meter.
4. Show subscription CTA if free user.
5. Show add credit CTA if paid user.

UI states:

| Backend state | Parent dashboard behavior |
|---|---|
| `FREE_ACTIVE` | Show free meter and upgrade CTA |
| `FREE_EXHAUSTED_READ_ONLY` | Show exhausted state and subscribe CTA |
| `SUBSCRIPTION_ACTIVE` | Show plan, usage, add credits, upgrade |
| `SUBSCRIPTION_EXHAUSTED` | Show add credits / upgrade CTA |
| `NO_CREDITS_READ_ONLY` | Show unlock CTA |

### 17.2 Kid chat screen

Before enabling composer:

1. Load entitlement.
2. Check `can_chat`.
3. If `can_chat = true`, show normal composer.
4. If `can_chat = false` and `can_read_history = true`, show read-only composer.

Pseudo-code:

```ts
if (!billing.canChat && billing.canReadHistory) {
  return <ReadOnlyComposer onAskParent={openParentGate} />;
}

return <ChatComposer />;
```

### 17.3 On chat send

After `POST /v1/chat`:

1. If success, append AI response.
2. Update billing state from `response.billing`.
3. If low credit, show parent-only alert later.
4. If exhausted error, switch kid UI to read-only.

Pseudo-code:

```ts
const response = await chatApi.sendMessage(input);

if (response.error_code === 'CREDITS_EXHAUSTED') {
  dispatch({
    type: 'BILLING_LOAD_SUCCEEDED',
    payload: mapExhaustedResponse(response),
  });
  showReadOnlyMode();
  return;
}

dispatch({
  type: 'CHAT_BILLING_UPDATED',
  payload: response.billing,
});
```

### 17.4 Subscription plans screen

On screen open:

1. Call `GET /v1/billing/plans`.
2. Render existing plan cards.
3. On select plan, call native purchase provider.
4. On purchase success, send receipt/token to backend.
5. Refresh entitlement.
6. Navigate to parent dashboard or payment confirmation screen.

### 17.5 Add credits screen

On screen open:

1. Call `GET /v1/billing/credit-packs`.
2. If eligible, show packs.
3. If not eligible, show subscription CTA.
4. On pack purchase, verify purchase with backend.
5. Refresh entitlement.

### 17.6 Restore purchases screen

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
→ Free Plan active
→ Kid can chat until credits finish
→ Free exhausted
→ Kid read-only
→ Parent subscription screen
→ Purchase subscription
→ Subscription active
→ Kid chat unlocked
```

### 18.2 Paid user exhausted flow

```text
Kid sends message
→ Backend returns credits exhausted
→ Kid read-only message
→ Ask Parent
→ Parent PIN gate
→ Add Credits / Upgrade Plan
→ Purchase success
→ Entitlement refresh
→ Kid chat unlocked
```

### 18.3 Existing parent billing flow

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

The backend must be the final authority.

Mobile app checks are only UX helpers. Backend must still enforce:

- subscription status
- free plan limits
- credit availability
- voice entitlement
- model tier entitlement
- kid count limit
- add-on eligibility
- read-only mode

Pseudo-code:

```ts
async function handleChatRequest(request) {
  const entitlement = await billingEntitlementService.getEntitlement(request.familyAccountId);

  if (!entitlement.canChat) {
    const risk = await classifier.quickCheck(request.message);

    if (risk.isHighRisk && entitlement.safetyOverrideEnabled) {
      return generateLimitedSafetyResponse(request);
    }

    return creditsExhaustedReadOnlyResponse(entitlement);
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

### 21.2 Backend should still keep own entitlement

Even if RevenueCat is used, Pratvim backend should keep its own:

- subscriptions table
- wallet table
- ledger table
- usage events
- entitlement API

Reason:

```text
RevenueCat manages purchase state.
Pratvim backend manages credits, AI usage, read-only mode, and safety exceptions.
```

---

## 22. Idempotency Rules

All billing operations must be idempotent.

Use idempotency keys for:

- subscription activation
- subscription renewal
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
chat:request_id:usage_debit
```

Never grant credits twice for the same purchase event.

---

## 23. Notifications

### 23.1 Parent notifications

| Trigger | Message |
|---|---|
| 20% credits left | Credits are running low. Add more or upgrade to avoid interruption. |
| Free credits exhausted | Free monthly credits are used. Subscribe to continue chatting. |
| Paid credits exhausted | Monthly credits are used. Add credits to continue. |
| Subscription renewal | Monthly credits have refreshed. |
| Payment failed | Payment could not be completed. Update billing to keep Pratvim active. |

### 23.2 Kid notifications

Keep messages simple and non-commercial.

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

Do not show every token-level usage event to parents in MVP.

Admin can see detailed usage events.

---

## 25. Implementation Phases

## Phase 1: Backend Foundation

### Tasks

1. Add database tables:
   - `plans`
   - `credit_packs`
   - `store_products`
   - `subscriptions`
   - `credit_buckets`
   - `credit_ledger`
   - `model_catalog`
   - `rate_cards`
   - `rate_card_items`
   - `usage_events`
2. Implement Billing Entitlement Service.
3. Implement Credit Wallet Service.
4. Implement Rate Card Service.
5. Implement Usage Metering Service.
6. Implement monthly free credit grant job.
7. Implement monthly paid credit grant job.
8. Add seed data for Free, Basic, Plus, Family.

### Acceptance criteria

- New family without subscription gets free monthly credits.
- Free credits are consumed correctly.
- Free exhausted account becomes read-only.
- Paid subscription account gets monthly credits.
- Add-on credits are separate from monthly credits.
- Ledger records all grants and debits.

---

## Phase 2: Admin Billing Panel

### Tasks

Under **Admin → Billing**, implement:

1. Billing Overview
2. Plans
3. Free Plan
4. Credit Packs
5. Model Catalog
6. Rate Cards
7. Subscriptions
8. Family Wallets
9. Usage Events
10. Credit Ledger
11. Adjustments
12. Store Products
13. Billing Alerts
14. Reports
15. Billing Settings

### Acceptance criteria

- Admin can configure free monthly credits.
- Admin can configure paid plans.
- Admin can configure credit packs.
- Admin can configure model-based credit rates.
- Admin can activate a new rate card version.
- Admin can view wallet and ledger for each family.
- Admin can manually adjust credits with reason.

---

## Phase 3: Mobile Billing Wiring

### Tasks

1. Add billing API client.
2. Add billing repository.
3. Add billing state/reducer/effects.
4. Wire parent dashboard credit meter.
5. Wire subscription screen to backend plans.
6. Wire add credits screen to backend packs.
7. Wire kid chat screen to entitlement state.
8. Add read-only mode behavior.
9. Add parent PIN gate before billing actions from kid flow.
10. Add restore purchase flow.

### Acceptance criteria

- Parent sees free credits remaining.
- Parent sees paid plan usage.
- Kid can chat when `can_chat = true`.
- Kid cannot chat when `can_chat = false`.
- Kid can still read old messages in read-only mode.
- Parent can navigate to subscription screen when free credits are exhausted.
- Paid parent can navigate to add credits when credits are exhausted.

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

### Acceptance criteria

- Subscription purchase activates plan.
- Monthly credits are granted after subscription activation.
- Add-on credit purchase grants correct credits.
- Duplicate purchase events do not duplicate credits.
- Restore purchase refreshes entitlement.

---

## Phase 5: Chat Metering Enforcement

### Tasks

1. Add pre-chat entitlement check.
2. Add credit reservation before model call.
3. Add actual usage metering after model response.
4. Add ledger debit after usage calculation.
5. Add reservation release on failure.
6. Add exhausted response handling.
7. Add limited safety override.

### Acceptance criteria

- Credits are charged based on actual model usage.
- Concurrent chats do not overspend wallet.
- Failed model calls do not consume credits.
- Exhausted users are blocked from normal chat.
- High-risk safety messages still receive limited safe response.

---

## Phase 6: Notifications and Reporting

### Tasks

1. Add low-credit notification.
2. Add free-exhausted notification.
3. Add paid-exhausted notification.
4. Add renewal notification.
5. Add failed payment notification.
6. Add billing reports.
7. Add free-to-paid conversion report.

### Acceptance criteria

- Parent receives useful alerts.
- Kids do not receive payment-related alerts.
- Admin can track conversion and usage.

---

## 26. Testing Plan

### 26.1 Free plan tests

| Scenario | Expected result |
|---|---|
| New parent signs up | Free monthly credits granted |
| Kid sends message | Credits deducted |
| Free credits reach zero | Kid moves to read-only |
| Parent subscribes | Paid credits granted, kid unlocked |
| Monthly reset occurs | Free credits refreshed for non-paid account |

### 26.2 Paid subscription tests

| Scenario | Expected result |
|---|---|
| Parent buys Basic plan | Subscription active, credits granted |
| Monthly credits exhausted | Use add-on credits if available |
| No add-on credits | Kid read-only |
| Parent buys add-on pack | Kid unlocked |
| Renewal occurs | Monthly credits refreshed |
| Payment fails | Grace/block rules applied |

### 26.3 Ledger tests

| Scenario | Expected result |
|---|---|
| Grant free credits | Ledger has grant event |
| Debit chat usage | Ledger has debit event |
| Failed chat | Reservation released |
| Duplicate purchase webhook | No duplicate grant |
| Admin adjustment | Ledger has adjustment with reason |

### 26.4 Mobile UI tests

| Scenario | Expected result |
|---|---|
| `FREE_ACTIVE` | Chat composer visible |
| `FREE_EXHAUSTED_READ_ONLY` | Read-only composer visible |
| `SUBSCRIPTION_ACTIVE` | Chat composer visible |
| `NO_CREDITS_READ_ONLY` | Ask Parent button visible |
| Parent PIN success | Billing screen opens |
| Parent PIN fail | Billing screen blocked |

---

## 27. Security and Abuse Controls

### 27.1 Free plan abuse prevention

Recommended controls:

- Require verified parent email or phone before free usage.
- Limit one free plan per parent account.
- Limit one kid profile on free plan.
- No voice in free plan.
- Use low-cost model tier for free plan.
- Track repeated signup patterns.
- Add soft device/account abuse signals.

### 27.2 Admin security

- Billing admin actions should be RBAC-protected.
- Credit adjustment should require reason.
- Large adjustment should require approval.
- Rate card activation should be audited.
- Store product changes should be audited.
- Ledger should be immutable.

---

## 28. Important Implementation Decisions

### Decision 1

Use credits as parent-facing unit, not tokens.

### Decision 2

Keep all billing configuration under Admin → Billing.

### Decision 3

Free plan is a real plan, not a hardcoded exception.

### Decision 4

Monthly credits and add-on credits must be separate buckets.

### Decision 5

Use an immutable credit ledger.

### Decision 6

Backend is the source of truth for all entitlement and credit decisions.

### Decision 7

Mobile app should only display billing state and trigger purchases.

### Decision 8

Do not charge parents separately for classifier, validator, and normalization in MVP.

### Decision 9

Free exhausted users become read-only, not fully blocked.

### Decision 10

Safety-critical responses are allowed in limited form even with zero credits.

---

## 29. Final Recommended Rule Set

```text
Every parent account always has a billing entitlement.

If there is no paid subscription:
    Use Free Monthly Plan.

If free credits are available:
    Kid can chat.

If free credits are exhausted:
    Kid can read previous messages only.
    Parent is prompted to subscribe.

If paid subscription is active:
    Use paid monthly credits first.

If paid monthly credits are exhausted:
    Use add-on credits.

If no credits remain:
    Kid account becomes read-only.
    Parent can buy add-on credits or upgrade plan.

If the message is safety-critical:
    Allow limited safety response even when credits are zero.

Admin controls all plans, free credits, credit packs, model rates, usage rules, and ledger adjustments under Billing.
```

---

## 30. MVP Checklist

### Backend

- [ ] Plans table
- [ ] Free plan support
- [ ] Subscription support
- [ ] Credit packs
- [ ] Credit buckets
- [ ] Credit ledger
- [ ] Rate cards
- [ ] Model catalog
- [ ] Usage events
- [ ] Entitlement API
- [ ] Usage summary API
- [ ] Purchase verification API
- [ ] Chat credit enforcement
- [ ] Monthly credit grant job
- [ ] Read-only mode response
- [ ] Safety override

### Admin

- [ ] Billing menu
- [ ] Plans screen
- [ ] Free Plan screen
- [ ] Credit Packs screen
- [ ] Model Catalog screen
- [ ] Rate Cards screen
- [ ] Subscriptions screen
- [ ] Wallet screen
- [ ] Usage Events screen
- [ ] Credit Ledger screen
- [ ] Adjustments screen
- [ ] Reports screen
- [ ] Settings screen

### Mobile

- [ ] Billing API client
- [ ] Billing state management
- [ ] Parent dashboard credit meter
- [ ] Subscription screen wiring
- [ ] Add credit screen wiring
- [ ] Restore purchase flow
- [ ] Kid read-only mode
- [ ] Ask Parent flow
- [ ] Parent PIN gate
- [ ] Chat billing response handling
- [ ] Low credit alerts

---

## 31. Suggested Implementation Order

1. Build backend database and seed billing data.
2. Build entitlement API.
3. Build credit wallet and ledger.
4. Build free plan monthly grant.
5. Build admin Billing screens.
6. Wire mobile parent dashboard.
7. Wire kid read-only mode.
8. Add purchase integration.
9. Add usage metering and chat debit.
10. Add notifications and reports.
11. Run end-to-end QA.
12. Release with limited plan values first.

---

## 32. End-to-End Example

### New free user

```text
Parent creates account
→ Backend grants 10 free credits
→ Kid sends message
→ Backend charges 1 credit
→ Remaining credits = 9
```

### Free user exhausted

```text
Credits reach 0
→ Backend account mode = FREE_EXHAUSTED_READ_ONLY
→ Kid can read old messages
→ Kid cannot send new normal messages
→ Parent sees Subscribe CTA
```

### Parent subscribes

```text
Parent buys Plus plan
→ Backend verifies purchase
→ Subscription active
→ Backend grants 50,000 monthly credits
→ Kid chat unlocked
```

### Paid user buys add-on credits

```text
Monthly credits exhausted
→ Parent buys Medium Pack
→ Backend grants 50,000 add-on credits
→ Kid chat unlocked
→ Add-on credits do not reset monthly
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
Credit Wallet + Ledger
  ↓
Rate Card + Usage Metering
  ↓
Chat / Voice / Safety Services
  ↓
Admin Billing Console
```

The clean separation is:

```text
Admin configures billing rules.
Backend enforces billing rules.
Mobile displays billing state.
Parent pays and manages plans.
Kid only sees safe, simple access states.
```
