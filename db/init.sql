CREATE TABLE war_cases (
    case_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analyst_id    VARCHAR(100) NOT NULL,
    institution   VARCHAR(200) NOT NULL,
    input_text    TEXT NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'draft',
    confidence    NUMERIC(4,3),
    goaml_xml     TEXT,
    narrative_fr  TEXT,
    risk_level    VARCHAR(20),
    submitted     BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE war_entities (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       UUID REFERENCES war_cases(case_id),
    name          VARCHAR(500) NOT NULL,
    name_arabic   VARCHAR(500),
    entity_type   VARCHAR(20) NOT NULL,
    is_pep        BOOLEAN DEFAULT FALSE,
    sanctions_hit BOOLEAN DEFAULT FALSE,
    sanctions_data JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE war_corrections (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       UUID REFERENCES war_cases(case_id),
    analyst_id    VARCHAR(100) NOT NULL,
    approved      BOOLEAN NOT NULL,
    corrections   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cases_analyst ON war_cases(analyst_id);
CREATE INDEX idx_cases_status ON war_cases(status);
CREATE INDEX idx_entities_case ON war_entities(case_id);
