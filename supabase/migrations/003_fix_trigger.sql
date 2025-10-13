-- Fix avatar URL generation in trigger function
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS handle_new_user();

-- Simplified function to handle new user creation
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  user_name TEXT;
  user_account_type TEXT;
BEGIN
  -- Get name and account type from metadata
  user_name := COALESCE(NEW.raw_user_meta_data->>'name', NEW.email);
  user_account_type := COALESCE(NEW.raw_user_meta_data->>'account_type', 'individual');

  -- Insert into users table with simplified avatar URL
  INSERT INTO users (id, email, name, account_type, avatar_url, role, status)
  VALUES (
    NEW.id,
    NEW.email,
    user_name,
    user_account_type::account_type,
    'https://ui-avatars.com/api/?name=User&background=6366f1',
    'user'::user_role,
    'active'::user_status
  );
  
  -- Create initial user stats
  INSERT INTO user_stats (user_id, total_donations, total_trades, total_food_saved, total_impact_score)
  VALUES (NEW.id, 0, 0, 0.0, 0);
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Recreate the trigger
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();
