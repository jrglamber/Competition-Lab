import os
import psycopg
from psycopg.rows import dict_row

SCHEMA = r'''
CREATE TABLE IF NOT EXISTS competitions (
 id BIGSERIAL PRIMARY KEY, operator TEXT NOT NULL, external_id TEXT NOT NULL,
 title TEXT NOT NULL, url TEXT NOT NULL, prize_value_gbp NUMERIC, ticket_price_gbp NUMERIC,
 max_tickets INTEGER, closes_at TIMESTAMPTZ, guaranteed BOOLEAN,
 scope TEXT NOT NULL DEFAULT 'eligible', status TEXT NOT NULL DEFAULT 'open',
 health TEXT NOT NULL DEFAULT 'unknown', health_reason TEXT, last_seen_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(operator, external_id));
CREATE TABLE IF NOT EXISTS snapshots (
 id BIGSERIAL PRIMARY KEY, competition_id BIGINT NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
 observed_at TIMESTAMPTZ NOT NULL DEFAULT now(), sold_count INTEGER, remaining_count INTEGER,
 nominal_ev NUMERIC, conservative_final_field INTEGER, conservative_ev NUMERIC,
 sales_velocity_per_hour NUMERIC, data_json JSONB NOT NULL DEFAULT '{}'::jsonb);
CREATE INDEX IF NOT EXISTS snapshots_comp_time ON snapshots(competition_id, observed_at DESC);
CREATE TABLE IF NOT EXISTS entries (
 id BIGSERIAL PRIMARY KEY, competition_id BIGINT NOT NULL REFERENCES competitions(id), entered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 tickets INTEGER NOT NULL, stake_gbp NUMERIC NOT NULL, sold_count_at_entry INTEGER,
 nominal_ev_at_entry NUMERIC, conservative_ev_at_entry NUMERIC, conservative_final_field_at_entry INTEGER,
 expected_prize_gbp NUMERIC, expected_profit_gbp NUMERIC, notes TEXT,
 winnings_gbp NUMERIC, settled_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
'''

def conn():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row)

def init_db():
    with conn() as c:
        c.execute(SCHEMA)
