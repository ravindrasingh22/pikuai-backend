from app.core.config import settings
from app.db.session import get_connection


def bootstrap_database() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS parent_users (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  full_name TEXT NOT NULL,
                  email TEXT NOT NULL UNIQUE,
                  password_hash TEXT,
                  status TEXT NOT NULL DEFAULT 'active',
                  country TEXT NOT NULL,
                  preferred_language TEXT NOT NULL DEFAULT 'en',
                  two_factor_enabled BOOLEAN NOT NULL DEFAULT false,
                  two_factor_method TEXT,
                  pin_enabled BOOLEAN NOT NULL DEFAULT false,
                  pin_hash TEXT,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  last_login_at TIMESTAMPTZ
                )
                """
            )
            cursor.execute("ALTER TABLE parent_users ADD COLUMN IF NOT EXISTS gender TEXT")
            cursor.execute("ALTER TABLE parent_users ADD COLUMN IF NOT EXISTS phone_number TEXT")
            cursor.execute("ALTER TABLE parent_users ADD COLUMN IF NOT EXISTS city TEXT")
            cursor.execute("ALTER TABLE parent_users ADD COLUMN IF NOT EXISTS timezone TEXT")
            cursor.execute("ALTER TABLE parent_users ADD COLUMN IF NOT EXISTS onboarding_status TEXT DEFAULT 'complete'")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_users (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  full_name TEXT NOT NULL,
                  email TEXT NOT NULL UNIQUE,
                  password_hash TEXT NOT NULL,
                  role TEXT NOT NULL DEFAULT 'admin',
                  status TEXT NOT NULL DEFAULT 'active',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_runtime_config (
                  id BOOLEAN PRIMARY KEY DEFAULT true CHECK (id),
                  enabled BOOLEAN NOT NULL DEFAULT true,
                  provider TEXT NOT NULL DEFAULT 'ollama',
                  base_url TEXT NOT NULL DEFAULT 'http://localhost:11434',
                  model TEXT NOT NULL DEFAULT 'mistral:latest',
                  api_key_optional TEXT,
                  timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 30,
                  temperature DOUBLE PRECISION NOT NULL DEFAULT 0.2,
                  max_tokens INTEGER NOT NULL DEFAULT 280,
                  system_prompt_template TEXT NOT NULL,
                  user_prompt_template TEXT NOT NULL,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO llm_runtime_config (
                  id,
                  enabled,
                  provider,
                  base_url,
                  model,
                  api_key_optional,
                  timeout_seconds,
                  temperature,
                  max_tokens,
                  system_prompt_template,
                  user_prompt_template
                )
                VALUES (
                  true,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s
                )
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    settings.llm_enabled,
                    settings.llm_provider,
                    settings.llm_base_url,
                    settings.llm_model,
                    settings.llm_api_key or None,
                    settings.llm_timeout_seconds,
                    settings.llm_temperature,
                    settings.llm_max_tokens,
                    "You are PikuAI, a child-safe learning assistant.\nAnswer the child's actual question first with useful content, then optional enrichment.\nUse factual accuracy where possible. Be warm, natural, and child-friendly without over-cute filler.\nDo not use generic filler such as 'that is interesting' when a real answer can be given.\nNever expose policy labels or moderation internals in final child text.\nFor unsafe or too-mature requests, avoid abrupt refusal when possible: soften, reduce detail, redirect safely,\nand suggest involving a trusted adult where appropriate.\nAge policy: {age_style_rule}\nAnswer mode policy: {answer_mode_rule}\nChild profile: name={child_name}, age_group={child_age_group}, gender={child_gender}, pattern={child_pattern}.",
                    "Conversation goal:\n{conversation_goal}\n\nResponse style:\n- category: {message_category}\n- answer_mode: {answer_mode}\n- language: {language}\n\nThread memory:\n- rolling_summary: {thread_summary}\n- topic_continuity: {topic_continuity}\n- unresolved_follow_up: {unresolved_follow_up}\n- emotional_hint: {emotional_hint}\n- observed_preferences: {observed_preferences}\n- recent_entities: {recent_entities}\n\nRecent turns (last useful turns only):\n{recent_turns}\n\nSafety metadata:\n- policy_bucket: {policy_bucket}\n- safety_category: {safety_category}\n\nCurrent child message:\n{message}\n\nAnswer instructions:\n1) Give the direct answer first.\n2) Keep age-appropriate depth.\n3) Keep tone warm and natural.\n4) Use continuity only if relevant.\n5) Do not include internal labels in final output.",
                ),
            )
            cursor.execute(
                """
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
                  gender TEXT NOT NULL DEFAULT 'not_disclosed',
                  active_status TEXT NOT NULL DEFAULT 'active',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute("ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS voice_enabled BOOLEAN NOT NULL DEFAULT true")
            cursor.execute("UPDATE child_profiles SET voice_enabled = true WHERE voice_enabled IS NULL")
            cursor.execute("ALTER TABLE child_profiles ALTER COLUMN voice_enabled SET DEFAULT true")
            cursor.execute("ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS avatar_key TEXT NOT NULL DEFAULT 'kid'")
            cursor.execute("ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS gender TEXT NOT NULL DEFAULT 'not_disclosed'")
            cursor.execute("UPDATE child_profiles SET gender = 'not_disclosed' WHERE gender IS NULL")
            cursor.execute("ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS child_pin_enabled BOOLEAN NOT NULL DEFAULT false")
            cursor.execute("ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS child_pin_hash TEXT")
            cursor.execute("ALTER TABLE child_profiles DROP CONSTRAINT IF EXISTS child_profiles_age_band_check")
            cursor.execute(
                """
                UPDATE child_profiles
                SET age_band = CASE age_band
                  WHEN '5-7' THEN '6-8'
                  WHEN '8-10' THEN '9-11'
                  WHEN '11-12' THEN '11-13'
                  WHEN '13-16' THEN '14-17'
                  ELSE age_band
                END
                """
            )
            cursor.execute(
                """
                ALTER TABLE child_profiles
                ADD CONSTRAINT child_profiles_age_band_check
                CHECK (age_band IN ('3-5', '6-8', '9-11', '11-13', '14-17'))
                """
            )
            cursor.execute(
                """
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
                )
                """
            )
            cursor.execute(
                """
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
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_notifications (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
                  child_profile_id UUID REFERENCES child_profiles(id) ON DELETE SET NULL,
                  notification_type TEXT NOT NULL,
                  title TEXT NOT NULL,
                  body TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'unread',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute("ALTER TABLE admin_notifications ADD COLUMN IF NOT EXISTS thread_id UUID")
            cursor.execute("ALTER TABLE admin_notifications ADD COLUMN IF NOT EXISTS message_id UUID")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_threads (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
                  child_profile_id UUID NOT NULL REFERENCES child_profiles(id) ON DELETE CASCADE,
                  title TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'active',
                  last_policy_bucket TEXT NOT NULL DEFAULT 'allowed',
                  last_alert_id_optional UUID,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  thread_id UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
                  parent_user_id UUID NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
                  child_profile_id UUID NOT NULL REFERENCES child_profiles(id) ON DELETE CASCADE,
                  sender_type TEXT NOT NULL CHECK (sender_type IN ('child', 'assistant')),
                  message_text TEXT NOT NULL,
                  rendered_text TEXT NOT NULL,
                  age_band_used TEXT NOT NULL,
                  policy_bucket TEXT NOT NULL,
                  safety_category TEXT NOT NULL,
                  moderation_status TEXT NOT NULL,
                  explanation_code TEXT NOT NULL,
                  explanation_text TEXT NOT NULL,
                  answer_mode TEXT NOT NULL,
                  alert_id_optional UUID,
                  ai_model_used TEXT,
                  metadata_json JSONB NOT NULL DEFAULT '{}',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_threads_parent_child
                ON chat_threads(parent_user_id, child_profile_id, updated_at DESC)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_parent_thread
                ON chat_messages(parent_user_id, thread_id, created_at ASC)
                """
            )
            cursor.execute(
                """
                INSERT INTO parent_users (
                  full_name,
                  email,
                  password_hash,
                  status,
                  country,
                  preferred_language,
                  two_factor_enabled,
                  pin_enabled,
                  pin_hash
                )
                VALUES (
                  'Ravin Singh',
                  'ravin@example.com',
                  crypt('password123', gen_salt('bf')),
                  'active',
                  'IN',
                  'en',
                  true,
                  true,
                  crypt('1234', gen_salt('bf'))
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
                  pin_hash = EXCLUDED.pin_hash,
                  updated_at = now()
                """
            )
            cursor.execute(
                """
                INSERT INTO parent_users (
                  full_name,
                  email,
                  password_hash,
                  status,
                  country,
                  preferred_language,
                  two_factor_enabled,
                  pin_enabled,
                  pin_hash,
                  gender,
                  phone_number,
                  city,
                  timezone,
                  onboarding_status
                )
                VALUES
                  ('Ravin Test 1', 'r1@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'IN', 'en', true, true, crypt('1234', gen_salt('bf')), 'male', '+91-90000-00001', 'Mumbai', 'Asia/Kolkata', 'complete'),
                  ('Ravin Test 2', 'r2@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'IN', 'hi', false, true, crypt('1234', gen_salt('bf')), 'female', '+91-90000-00002', 'Delhi', 'Asia/Kolkata', 'complete'),
                  ('Ravin Test 3', 'r3@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'US', 'en', true, false, NULL, 'other', '+1-415-555-0103', 'San Francisco', 'America/Los_Angeles', 'profile_pending'),
                  ('Ravin Test 4', 'r4@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'GB', 'en', false, false, NULL, 'male', '+44-20-5555-0104', 'London', 'Europe/London', 'complete'),
                  ('Ravin Test 5', 'r5@ravin.co', crypt('password123', gen_salt('bf')), 'pending_verification', 'IN', 'en', false, false, NULL, 'female', '+91-90000-00005', 'Bengaluru', 'Asia/Kolkata', 'email_pending'),
                  ('Ravin Test 6', 'r6@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'CA', 'en', true, true, crypt('1234', gen_salt('bf')), 'other', '+1-604-555-0106', 'Vancouver', 'America/Vancouver', 'complete'),
                  ('Ravin Test 7', 'r7@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'IN', 'hi', true, false, NULL, 'male', '+91-90000-00007', 'Jaipur', 'Asia/Kolkata', 'child_setup_pending'),
                  ('Ravin Test 8', 'r8@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'AU', 'en', false, true, crypt('1234', gen_salt('bf')), 'female', '+61-2-5550-0108', 'Sydney', 'Australia/Sydney', 'complete'),
                  ('Ravin Test 9', 'r9@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'IN', 'en', true, true, crypt('1234', gen_salt('bf')), 'other', '+91-90000-00009', 'Hyderabad', 'Asia/Kolkata', 'complete'),
                  ('Ravin Test 10', 'r10@ravin.co', crypt('password123', gen_salt('bf')), 'active', 'SG', 'en', true, false, NULL, 'female', '+65-5550-0110', 'Singapore', 'Asia/Singapore', 'controls_pending')
                ON CONFLICT (email) DO UPDATE
                SET
                  full_name = EXCLUDED.full_name,
                  password_hash = EXCLUDED.password_hash,
                  status = EXCLUDED.status,
                  country = EXCLUDED.country,
                  preferred_language = EXCLUDED.preferred_language,
                  two_factor_enabled = EXCLUDED.two_factor_enabled,
                  pin_enabled = EXCLUDED.pin_enabled,
                  pin_hash = EXCLUDED.pin_hash,
                  gender = EXCLUDED.gender,
                  phone_number = EXCLUDED.phone_number,
                  city = EXCLUDED.city,
                  timezone = EXCLUDED.timezone,
                  onboarding_status = EXCLUDED.onboarding_status,
                  updated_at = now()
                """
            )
            cursor.execute(
                """
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
                  updated_at = now()
                """
            )
            cursor.execute(
                """
                INSERT INTO child_profiles (
                  parent_user_id,
                  display_name,
                  age_band,
                  auto_upgrade_enabled,
                  auto_upgrade_requires_parent_review,
                  conversation_visibility_rule,
                  daily_time_limit_minutes,
                  topic_restrictions_json,
                  active_status
                )
                SELECT parent.id, child.display_name, child.age_band, child.auto_upgrade_enabled,
                       child.auto_upgrade_requires_parent_review, child.conversation_visibility_rule,
                       child.daily_time_limit_minutes, child.topic_restrictions_json::jsonb,
                       child.active_status
                FROM parent_users parent
                JOIN (
                  VALUES
                    ('r1@ravin.co', 'Mira', '6-8', true, true, 'parent_visible', 20, '["explicit_content"]', 'active'),
                    ('r2@ravin.co', 'Ira', '9-11', true, false, 'parent_visible', 35, '[]', 'active'),
                    ('r3@ravin.co', 'Noah', '11-13', false, true, 'summary_only', 45, '["self_harm"]', 'active'),
                    ('r4@ravin.co', 'Leo', '6-8', true, true, 'parent_visible', 25, '[]', 'active'),
                    ('r5@ravin.co', 'Anaya', '9-11', true, true, 'parent_visible', 30, '["bullying"]', 'active'),
                    ('r6@ravin.co', 'Sam', '11-13', true, false, 'summary_only', 50, '[]', 'active'),
                    ('r7@ravin.co', 'Kabir', '9-11', true, true, 'parent_visible', 30, '["dangerous_instructions"]', 'active'),
                    ('r8@ravin.co', 'Sia', '6-8', true, true, 'parent_visible', 20, '[]', 'active'),
                    ('r9@ravin.co', 'Dev', '11-13', false, true, 'parent_visible', 40, '["explicit_content"]', 'active'),
                    ('r9@ravin.co', 'Tara', '9-11', true, true, 'parent_visible', 30, '[]', 'active'),
                    ('r10@ravin.co', 'Nina', '6-8', true, true, 'parent_visible', 25, '[]', 'active')
                ) AS child(email, display_name, age_band, auto_upgrade_enabled,
                           auto_upgrade_requires_parent_review, conversation_visibility_rule,
                           daily_time_limit_minutes, topic_restrictions_json, active_status)
                  ON child.email = parent.email
                ON CONFLICT DO NOTHING
                """
            )
            cursor.execute(
                """
                DELETE FROM child_profiles child
                USING parent_users parent
                WHERE child.parent_user_id = parent.id
                  AND parent.email = 'r1@ravin.co'
                  AND child.display_name = 'Aarav'
                """
            )
            cursor.execute(
                """
                INSERT INTO parent_control_settings (
                  parent_user_id,
                  transcript_visibility_enabled,
                  content_strictness_level,
                  session_limit_enabled,
                  default_session_limit_minutes,
                  sensitive_topic_alerts_enabled,
                  weekly_summary_enabled,
                  optional_personalization_enabled,
                  retention_policy_code
                )
                SELECT id, true,
                       CASE
                         WHEN email IN ('r3@ravin.co', 'r7@ravin.co', 'r9@ravin.co') THEN 'strict'
                         WHEN email IN ('r4@ravin.co', 'r8@ravin.co') THEN 'low'
                         ELSE 'balanced'
                       END,
                       true,
                       CASE WHEN email IN ('r6@ravin.co') THEN 50 ELSE 30 END,
                       true,
                       true,
                       false,
                       '90_days'
                FROM parent_users
                WHERE email LIKE 'r%@ravin.co' OR email = 'ravin@example.com'
                ON CONFLICT (parent_user_id) DO NOTHING
                """
            )
            cursor.execute(
                """
                INSERT INTO subscriptions (
                  parent_user_id,
                  plan_code,
                  billing_cycle,
                  status,
                  ends_at,
                  auto_renew,
                  payment_provider
                )
                SELECT id,
                       CASE
                         WHEN email IN ('r1@ravin.co', 'r6@ravin.co', 'r9@ravin.co') THEN 'family_plus'
                         WHEN email IN ('r10@ravin.co') THEN 'family_max'
                         ELSE 'starter'
                       END,
                       'monthly',
                       CASE WHEN email = 'r5@ravin.co' THEN 'past_due' ELSE 'active' END,
                       now() + interval '30 days',
                       email <> 'r5@ravin.co',
                       'demo'
                FROM parent_users
                WHERE email LIKE 'r%@ravin.co' OR email = 'ravin@example.com'
                ON CONFLICT DO NOTHING
                """
            )
            cursor.execute(
                """
                INSERT INTO admin_notifications (
                  parent_user_id,
                  child_profile_id,
                  notification_type,
                  title,
                  body,
                  status
                )
                SELECT parent.id, child.id, note.notification_type, note.title, note.body, note.status
                FROM parent_users parent
                JOIN child_profiles child ON child.parent_user_id = parent.id
                JOIN (
                  VALUES
                    ('r3@ravin.co', 'Noah', 'wellbeing', 'Escalation watch', 'Self-harm language policy is enabled for this child.', 'unread'),
                    ('r5@ravin.co', 'Anaya', 'billing', 'Payment attention', 'Subscription is past due; entitlements may downgrade.', 'unread'),
                    ('r7@ravin.co', 'Kabir', 'setup', 'Child setup pending', 'Parent has not completed all child profile settings.', 'read'),
                    ('r9@ravin.co', 'Dev', 'privacy', 'Consent check', 'Transcript visibility and retention should be reviewed.', 'unread')
                ) AS note(email, child_name, notification_type, title, body, status)
                  ON note.email = parent.email AND note.child_name = child.display_name
                WHERE NOT EXISTS (
                  SELECT 1 FROM admin_notifications existing
                  WHERE existing.parent_user_id = parent.id
                    AND existing.title = note.title
                )
                """
            )
        connection.commit()
