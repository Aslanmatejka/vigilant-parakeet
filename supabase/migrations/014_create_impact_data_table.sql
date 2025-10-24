/*
  # Create Impact Data Table

  1. New Tables
    - `impact_data`
      - `id` (uuid, primary key)
      - `date` (date) - Date of the impact record
      - `food_saved_kg` (numeric) - Amount of food saved in kilograms
      - `people_helped` (integer) - Number of people helped
      - `meals_provided` (integer) - Number of meals provided
      - `co2_reduced_kg` (numeric) - CO2 emissions reduced in kilograms
      - `waste_diverted_kg` (numeric) - Waste diverted from landfills in kilograms
      - `volunteer_hours` (numeric) - Volunteer hours contributed
      - `partner_organizations` (integer) - Number of partner organizations
      - `notes` (text) - Additional notes or context
      - `created_at` (timestamptz)
      - `updated_at` (timestamptz)
      - `created_by` (uuid, foreign key to users)

  2. Security
    - Enable RLS on `impact_data` table
    - Add policies for admin-only access
*/

CREATE TABLE IF NOT EXISTS impact_data (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date date NOT NULL,
  food_saved_kg numeric DEFAULT 0,
  people_helped integer DEFAULT 0,
  meals_provided integer DEFAULT 0,
  co2_reduced_kg numeric DEFAULT 0,
  waste_diverted_kg numeric DEFAULT 0,
  volunteer_hours numeric DEFAULT 0,
  partner_organizations integer DEFAULT 0,
  notes text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  created_by uuid REFERENCES users(id),
  UNIQUE(date)
);

ALTER TABLE impact_data ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can view all impact data"
  ON impact_data
  FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND users.is_admin = true
    )
  );

CREATE POLICY "Admins can insert impact data"
  ON impact_data
  FOR INSERT
  TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND users.is_admin = true
    )
  );

CREATE POLICY "Admins can update impact data"
  ON impact_data
  FOR UPDATE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND users.is_admin = true
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND users.is_admin = true
    )
  );

CREATE POLICY "Admins can delete impact data"
  ON impact_data
  FOR DELETE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND users.is_admin = true
    )
  );

CREATE INDEX IF NOT EXISTS impact_data_date_idx ON impact_data(date DESC);
CREATE INDEX IF NOT EXISTS impact_data_created_by_idx ON impact_data(created_by);
