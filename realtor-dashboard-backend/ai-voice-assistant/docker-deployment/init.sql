CREATE TABLE IF NOT EXISTS realtors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    phone_number VARCHAR(15),
    business_hours_start TIME,
    business_hours_end TIME,
    voice_preference VARCHAR(50),
    business_address TEXT,
    prompt_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(15),
    source VARCHAR(255),
    status VARCHAR(20) DEFAULT 'new',
    company_id INTEGER REFERENCES companies(id),
    company_name VARCHAR(255),
    reason_for_call TEXT,
    company TEXT,
    last_contact_date TIMESTAMP,
    followupboss_person_id VARCHAR(100) UNIQUE,  -- FollowUpBoss person ID to prevent duplicates
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_leads_followupboss_person_id ON leads(followupboss_person_id);

CREATE TABLE IF NOT EXISTS call_histories (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id),
    call_status VARCHAR(20),
    call_sid VARCHAR(50),
    transcript TEXT,
    company_id INTEGER REFERENCES companies(id),
    company_name VARCHAR(255),
    company TEXT, 
    reason_for_call TEXT,
    call_start_time TIMESTAMP,
    call_end_time TIMESTAMP,
    call_duration INTEGER,
    import_batch_id VARCHAR(50),
    call_attempts INTEGER DEFAULT 0,
    call_direction VARCHAR(10) DEFAULT 'outbound',
    automation_status VARCHAR(20),
    failure_reason TEXT,
    last_call_timestamp TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add to your existing init.sql (not separate database)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_embeddings (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id), -- Links to your existing companies table!
    document_type VARCHAR(50),
    chunk_text TEXT NOT NULL,
    chunk_metadata JSONB,
    embedding vector(768),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);