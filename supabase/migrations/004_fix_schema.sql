-- Fix schema qualification issue in trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS handle_new_user();

-- Recreate function with explicit schema qualification
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  user_name TEXT;
  user_account_type TEXT;
BEGIN
  -- Get name and account type from metadata
  user_name := COALESCE(NEW.raw_user_meta_data->>'name', NEW.email);
  user_account_type := COALESCE(NEW.raw_user_meta_data->>'account_type', 'individual');

  -- Insert into public.users table with explicit schema
  INSERT INTO public.users (id, email, name, account_type, avatar_url, role, status)
  VALUES (
    NEW.id,
    NEW.email,
    user_name,
    user_account_type::public.account_type,
    COALESCE(
      NEW.raw_user_meta_data->>'avatar_url',
      'https://ui-avatars.com/api/?name=' || replace(COALESCE(user_name, 'User'), ' ', '+') || '&background=6366f1&color=ffffff&size=150'
    ),
    'user'::public.user_role,
    'active'::public.user_status
  );
  
  -- Create initial user stats with explicit schema
  INSERT INTO public.user_stats (user_id, total_donations, total_trades, total_food_saved, total_impact_score)
  VALUES (NEW.id, 0, 0, 0.0, 0);
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Recreate the trigger
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
