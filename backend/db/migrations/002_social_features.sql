-- Social features: follow requests and saved route collections
-- Migration: 002_social_features.sql

CREATE TABLE follow_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT follow_requests_requester_target_unique UNIQUE (requester_id, target_id),
    CONSTRAINT follow_requests_no_self_follow CHECK (requester_id <> target_id)
);

CREATE TABLE route_collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collector_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    route_id UUID NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT route_collections_unique UNIQUE (collector_id, route_id)
);

CREATE INDEX idx_follow_requests_requester ON follow_requests(requester_id);
CREATE INDEX idx_follow_requests_target_status ON follow_requests(target_id, status);
CREATE INDEX idx_follow_requests_status ON follow_requests(status);
CREATE INDEX idx_route_collections_collector ON route_collections(collector_id);
CREATE INDEX idx_route_collections_route ON route_collections(route_id);

CREATE TRIGGER update_follow_requests_updated_at
BEFORE UPDATE ON follow_requests
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
