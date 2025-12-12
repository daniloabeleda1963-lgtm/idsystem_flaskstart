-- Supabase table creation script for UGB RoMove members
-- Run this in your Supabase SQL Editor

-- Create members table
CREATE TABLE IF NOT EXISTS public.members (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    designation TEXT NOT NULL,
    chapter TEXT NOT NULL,
    birthdate DATE NOT NULL,
    blood_type TEXT NOT NULL,
    contact_no TEXT NOT NULL,
    home_address TEXT NOT NULL,
    height TEXT,
    weight TEXT,
    emergency_person_address TEXT,
    emergency_contact_no TEXT,
    issued_date DATE NOT NULL,
    valid_until DATE NOT NULL,
    photo_data TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Enable Row Level Security (RLS)
ALTER TABLE public.members ENABLE ROW LEVEL SECURITY;

-- Create policies for public access (adjust as needed for your security requirements)
CREATE POLICY "Allow public read access" ON public.members
    FOR SELECT USING (true);

CREATE POLICY "Allow public insert access" ON public.members
    FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public update access" ON public.members
    FOR UPDATE USING (true);

CREATE POLICY "Allow public delete access" ON public.members
    FOR DELETE USING (true);

-- Create indexes for better search performance
CREATE INDEX IF NOT EXISTS members_name_idx ON public.members USING gin (to_tsvector('english', name));
CREATE INDEX IF NOT EXISTS members_chapter_idx ON public.members USING gin (to_tsvector('english', chapter));
CREATE INDEX IF NOT EXISTS members_designation_idx ON public.members USING gin (to_tsvector('english', designation));
CREATE INDEX IF NOT EXISTS members_contact_idx ON public.members (contact_no);
CREATE INDEX IF NOT EXISTS members_blood_type_idx ON public.members (blood_type);

-- Create a function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = TIMEZONE('utc'::text, NOW());
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to automatically update updated_at
CREATE TRIGGER update_members_updated_at 
    BEFORE UPDATE ON public.members 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Insert sample data for testing
INSERT INTO public.members (name, designation, chapter, birthdate, blood_type, contact_no, home_address, height, weight, emergency_person_address, emergency_contact_no, issued_date, valid_until) VALUES
('Juan Dela Cruz', 'President', 'Manila Chapter', '1990-01-15', 'O+', '09171234567', '123 Rizal St., Manila, Philippines', '5''8"', '70kg', '456 Bonifacio Ave., Manila', '09187654321', '2024-01-01', '2027-01-01'),
('Maria Santos', 'Vice President', 'Quezon City Chapter', '1992-03-22', 'A+', '09281234567', '789 EDSA, Quezon City, Philippines', '5''4"', '55kg', '321 Commonwealth Ave., QC', '09287654321', '2024-01-01', '2027-01-01'),
('Pedro Garcia', 'Secretary', 'Makati Chapter', '1988-07-10', 'B+', '09391234567', '456 Ayala Ave., Makati City, Philippines', '5''10"', '75kg', '654 Gil Puyat Ave., Makati', '09397654321', '2024-01-01', '2027-01-01'),
('Ana Rodriguez', 'Treasurer', 'Pasig Chapter', '1995-11-05', 'AB+', '09401234567', '321 Ortigas Ave., Pasig City, Philippines', '5''6"', '60kg', '987 C5 Road, Pasig', '09407654321', '2024-01-01', '2027-01-01'),
('Carlos Mendoza', 'Auditor', 'Taguig Chapter', '1987-09-18', 'O-', '09501234567', '789 BGC, Taguig City, Philippines', '5''9"', '68kg', '123 Fort Bonifacio, Taguig', '09507654321', '2024-01-01', '2027-01-01');

-- Create a view for search optimization (optional)
CREATE OR REPLACE VIEW members_search_view AS
SELECT 
    id,
    name,
    designation,
    chapter,
    contact_no,
    blood_type,
    home_address,
    to_tsvector('english', 
        COALESCE(name, '') || ' ' || 
        COALESCE(designation, '') || ' ' || 
        COALESCE(chapter, '') || ' ' || 
        COALESCE(contact_no, '') || ' ' || 
        COALESCE(blood_type, '') || ' ' || 
        COALESCE(home_address, '')
    ) as search_vector
FROM public.members;