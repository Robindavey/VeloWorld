-- Add rider metrics used for simulation personalization
ALTER TABLE users
  ADD COLUMN rider_weight_kg FLOAT NOT NULL DEFAULT 75.0,
  ADD COLUMN ftp_w FLOAT NOT NULL DEFAULT 210.0;
