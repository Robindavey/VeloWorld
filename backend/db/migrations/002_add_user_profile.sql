-- Add profile fields to the users table
ALTER TABLE users
  ADD COLUMN name TEXT,
  ADD COLUMN bio TEXT;
