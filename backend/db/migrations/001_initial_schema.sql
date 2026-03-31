-- Initial database schema for VeloWorld MVP
-- Migration: 001_initial_schema.sql

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    bio TEXT,
    rider_weight_kg FLOAT DEFAULT 70.0,
    ftp_w FLOAT DEFAULT 200.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Routes table
CREATE TABLE routes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    distance_m FLOAT NOT NULL,
    elevation_gain_m FLOAT,
    source_format TEXT NOT NULL CHECK (source_format IN ('gpx', 'fit', 'tcx')),
    s3_key TEXT NOT NULL,
    processing_status TEXT NOT NULL DEFAULT 'queued' CHECK (processing_status IN ('queued', 'processing', 'ready', 'failed')),
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Rides table
CREATE TABLE rides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rider_id UUID REFERENCES users(id) ON DELETE CASCADE,
    route_id UUID REFERENCES routes(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_s INTEGER,
    distance_m FLOAT,
    elevation_gain_m FLOAT,
    avg_power_w FLOAT,
    avg_speed_kph FLOAT,
    max_power_w FLOAT,
    max_speed_kph FLOAT,
    total_energy_kj FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Route processing jobs table
CREATE TABLE route_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id UUID REFERENCES routes(id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (stage IN ('ingestion', 'map_matching', 'terrain', 'road_mesh', 'environment', 'packaging')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'complete', 'failed')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_routes_owner_id ON routes(owner_id);
CREATE INDEX idx_routes_processing_status ON routes(processing_status);
CREATE INDEX idx_rides_rider_id ON rides(rider_id);
CREATE INDEX idx_rides_route_id ON rides(route_id);
CREATE INDEX idx_route_jobs_route_id ON route_jobs(route_id);
CREATE INDEX idx_route_jobs_status ON route_jobs(status);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_routes_updated_at BEFORE UPDATE ON routes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();