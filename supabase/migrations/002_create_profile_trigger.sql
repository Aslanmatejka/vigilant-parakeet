-- Clean up any existing triggers
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS handle_new_user();

-- Function to automatically create user profile on signup
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  user_name TEXT;
  user_account_type TEXT;
  avatar_url_value TEXT;
BEGIN
  -- Get values with proper defaults
  user_name := COALESCE(NEW.raw_user_meta_data->>'name', NEW.email);
  user_account_type := COALESCE(NEW.raw_user_meta_data->>'account_type', 'individual');
  
  -- Create a simple avatar URL without encoding issues
  avatar_url_value := COALESCE(
    NEW.raw_user_meta_data->>'avatar_url',
    'https://ui-avatars.com/api/?name=' || replace(user_name, ' ', '+') || '&background=random'
  );

  INSERT INTO users (id, email, name, account_type, avatar_url, role, status)
  VALUES (
    NEW.id,
    NEW.email,
    user_name,
    user_account_type::account_type,
    avatar_url_value,
    'user'::user_role,
    'active'::user_status
  );
  
  -- Create initial user stats
  INSERT INTO user_stats (user_id, total_donations, total_trades, total_food_saved, total_impact_score)
  VALUES (NEW.id, 0, 0, 0.0, 0);
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to call the function when a user signs up
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();
