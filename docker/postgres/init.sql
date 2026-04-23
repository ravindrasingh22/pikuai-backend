CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS parent_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  country TEXT NOT NULL,
  preferred_language TEXT NOT NULL DEFAULT 'en',
  gender TEXT,
  phone_number TEXT,
  city TEXT,
  timezone TEXT,
  onboarding_status TEXT DEFAULT 'complete',
  two_factor_enabled BOOLEAN NOT NULL DEFAULT false,
  two_factor_method TEXT,
  pin_enabled BOOLEAN NOT NULL DEFAULT false,
  pin_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS admin_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'admin',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS child_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  age_band TEXT NOT NULL CHECK (age_band IN ('3-5', '6-8', '9-11', '11-13', '14-17')),
  birth_month_year_optional TEXT,
  avatar_url_optional TEXT,
  auto_upgrade_enabled BOOLEAN NOT NULL DEFAULT true,
  auto_upgrade_requires_parent_review BOOLEAN NOT NULL DEFAULT true,
  conversation_visibility_rule TEXT NOT NULL DEFAULT 'parent_visible',
  daily_time_limit_minutes INTEGER NOT NULL DEFAULT 30,
  topic_restrictions_json JSONB NOT NULL DEFAULT '[]',
  voice_enabled BOOLEAN NOT NULL DEFAULT true,
  avatar_key TEXT NOT NULL DEFAULT 'kid',
  gender TEXT NOT NULL DEFAULT 'not_disclosed',
  child_pin_enabled BOOLEAN NOT NULL DEFAULT false,
  child_pin_hash TEXT,
  active_status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS parent_control_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_user_id UUID NOT NULL UNIQUE REFERENCES parent_users(id) ON DELETE CASCADE,
  transcript_visibility_enabled BOOLEAN NOT NULL DEFAULT true,
  content_strictness_level TEXT NOT NULL DEFAULT 'balanced',
  session_limit_enabled BOOLEAN NOT NULL DEFAULT true,
  default_session_limit_minutes INTEGER NOT NULL DEFAULT 30,
  sensitive_topic_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
  weekly_summary_enabled BOOLEAN NOT NULL DEFAULT true,
  optional_personalization_enabled BOOLEAN NOT NULL DEFAULT false,
  retention_policy_code TEXT NOT NULL DEFAULT '90_days',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

CREATE TABLE IF NOT EXISTS conversation_threads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  child_profile_id UUID NOT NULL REFERENCES child_profiles(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  created_by TEXT NOT NULL DEFAULT 'child',
  status TEXT NOT NULL DEFAULT 'active',
  last_message_at TIMESTAMPTZ,
  last_policy_bucket TEXT,
  last_alert_id_optional UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id UUID NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
  sender_type TEXT NOT NULL,
  sender_id_optional UUID,
  message_text TEXT NOT NULL,
  rendered_text TEXT NOT NULL,
  age_band_used TEXT NOT NULL,
  policy_bucket TEXT NOT NULL,
  safety_category TEXT NOT NULL,
  moderation_status TEXT NOT NULL,
  explanation_code TEXT NOT NULL,
  explanation_text TEXT NOT NULL,
  ai_model_used TEXT,
  answer_mode TEXT NOT NULL DEFAULT 'short_answer',
  alert_id_optional UUID,
  metadata_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS safety_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
  child_profile_id UUID NOT NULL REFERENCES child_profiles(id) ON DELETE CASCADE,
  thread_id UUID NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
  message_id UUID NOT NULL REFERENCES conversation_messages(id) ON DELETE CASCADE,
  severity TEXT NOT NULL,
  alert_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  review_notes_optional TEXT,
  triggered_reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at_optional TIMESTAMPTZ,
  reviewed_by_optional UUID
);

CREATE TABLE IF NOT EXISTS privacy_consent_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
  consent_type TEXT NOT NULL,
  granted BOOLEAN NOT NULL,
  consent_version TEXT NOT NULL,
  granted_at TIMESTAMPTZ,
  revoked_at_optional TIMESTAMPTZ,
  metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS policy_decision_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID NOT NULL REFERENCES conversation_messages(id) ON DELETE CASCADE,
  input_classification TEXT NOT NULL,
  age_policy_version TEXT NOT NULL,
  generation_policy_version TEXT NOT NULL,
  output_check_result TEXT NOT NULL,
  final_policy_bucket TEXT NOT NULL,
  escalation_triggered BOOLEAN NOT NULL DEFAULT false,
  reason_codes_json JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_child_profiles_parent ON child_profiles(parent_user_id);
CREATE INDEX IF NOT EXISTS idx_threads_child ON conversation_threads(child_profile_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON conversation_messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_alerts_parent_status ON safety_alerts(parent_user_id, status);

INSERT INTO parent_users (
  full_name,
  email,
  password_hash,
  status,
  country,
  preferred_language,
  two_factor_enabled,
  pin_enabled
)
VALUES (
  'Ravin Singh',
  'ravin@example.com',
  crypt('password123', gen_salt('bf')),
  'active',
  'IN',
  'en',
  true,
  true
)
ON CONFLICT (email) DO UPDATE
SET
  full_name = EXCLUDED.full_name,
  password_hash = EXCLUDED.password_hash,
  status = EXCLUDED.status,
  country = EXCLUDED.country,
  preferred_language = EXCLUDED.preferred_language,
  two_factor_enabled = EXCLUDED.two_factor_enabled,
  pin_enabled = EXCLUDED.pin_enabled,
  updated_at = now();

INSERT INTO parent_users (
  full_name,
  email,
  password_hash,
  status,
  country,
  preferred_language,
  two_factor_enabled,
  pin_enabled,
  gender,
  phone_number,
  city,
  timezone,
  onboarding_status
)
VALUES
  ('Ravin Test 1', 'r1@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'IN', 'en', true, true, 'male', '+91-90000-00001', 'Mumbai', 'Asia/Kolkata', 'complete'),
  ('Ravin Test 2', 'r2@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'IN', 'hi', false, true, 'female', '+91-90000-00002', 'Delhi', 'Asia/Kolkata', 'complete'),
  ('Ravin Test 3', 'r3@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'US', 'en', true, false, 'other', '+1-415-555-0103', 'San Francisco', 'America/Los_Angeles', 'profile_pending'),
  ('Ravin Test 4', 'r4@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'GB', 'en', false, false, 'male', '+44-20-5555-0104', 'London', 'Europe/London', 'complete'),
  ('Ravin Test 5', 'r5@ravin.co', crypt('password123', gen_salt('bf')), 'pending_verification', 'IN', 'en', false, false, 'female', '+91-90000-00005', 'Bengaluru', 'Asia/Kolkata', 'email_pending'),
  ('Ravin Test 6', 'r6@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'CA', 'en', true, true, 'other', '+1-604-555-0106', 'Vancouver', 'America/Vancouver', 'complete'),
  ('Ravin Test 7', 'r7@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'IN', 'hi', true, false, 'male', '+91-90000-00007', 'Jaipur', 'Asia/Kolkata', 'child_setup_pending'),
  ('Ravin Test 8', 'r8@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'AU', 'en', false, true, 'female', '+61-2-5550-0108', 'Sydney', 'Australia/Sydney', 'complete'),
  ('Ravin Test 9', 'r9@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'IN', 'en', true, true, 'other', '+91-90000-00009', 'Hyderabad', 'Asia/Kolkata', 'complete'),
  ('Ravin Test 10', 'r10@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'SG', 'en', true, false, 'female', '+65-5550-0110', 'Singapore', 'Asia/Singapore', 'controls_pending')
ON CONFLICT (email) DO UPDATE
SET
  full_name = EXCLUDED.full_name,
  password_hash = EXCLUDED.password_hash,
  status = EXCLUDED.status,
  country = EXCLUDED.country,
  preferred_language = EXCLUDED.preferred_language,
  two_factor_enabled = EXCLUDED.two_factor_enabled,
  pin_enabled = EXCLUDED.pin_enabled,
  gender = EXCLUDED.gender,
  phone_number = EXCLUDED.phone_number,
  city = EXCLUDED.city,
  timezone = EXCLUDED.timezone,
  onboarding_status = EXCLUDED.onboarding_status,
  updated_at = now();

INSERT INTO admin_users (full_name, email, password_hash, role, status)
VALUES (
  'PikuAI Owner',
  'admin@pikuai.local',
  crypt('admin12345', gen_salt('bf')),
  'admin',
  'active'
)
ON CONFLICT (email) DO UPDATE
SET
  full_name = EXCLUDED.full_name,
  password_hash = EXCLUDED.password_hash,
  role = EXCLUDED.role,
  status = EXCLUDED.status,
  updated_at = now();
