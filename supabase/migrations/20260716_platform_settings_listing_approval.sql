-- Platform settings for admin toggles (listing approval, etc.)
CREATE TABLE IF NOT EXISTS public.platform_settings (
  key text PRIMARY KEY,
  value jsonb NOT NULL DEFAULT 'null'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid NULL
);

ALTER TABLE public.platform_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS platform_settings_select_authenticated ON public.platform_settings;
CREATE POLICY platform_settings_select_authenticated
  ON public.platform_settings FOR SELECT TO authenticated
  USING (true);

DROP POLICY IF EXISTS platform_settings_select_anon ON public.platform_settings;
CREATE POLICY platform_settings_select_anon
  ON public.platform_settings FOR SELECT TO anon
  USING (true);

DROP POLICY IF EXISTS platform_settings_admin_write ON public.platform_settings;
CREATE POLICY platform_settings_admin_write
  ON public.platform_settings FOR ALL TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.is_admin IS TRUE
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.is_admin IS TRUE
    )
  );

INSERT INTO public.platform_settings (key, value)
VALUES ('require_listing_approval', 'true'::jsonb)
ON CONFLICT (key) DO NOTHING;

GRANT SELECT ON public.platform_settings TO authenticated, anon;
GRANT INSERT, UPDATE, DELETE ON public.platform_settings TO authenticated;
