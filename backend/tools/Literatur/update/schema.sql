-- Paper Database Schema
-- Cache untuk SLR - paper metadata + source tracking

CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- Trigram similarity untuk fuzzy matching

-- Table 1: Papers (master table)
CREATE TABLE papers (
    id SERIAL PRIMARY KEY,
    doi VARCHAR(255) UNIQUE,
    title TEXT NOT NULL,
    title_normalized VARCHAR(255) GENERATED ALWAYS AS (lower(regexp_replace(title, '[^a-z0-9]+', '', 'gi'))) STORED,
    authors JSONB,  -- ["Author1", "Author2"]
    year INTEGER,
    venue TEXT,
    venue_type VARCHAR(50),  -- journal, conference, preprint, etc.
    abstract TEXT,
    citations INTEGER,
    is_open_access BOOLEAN DEFAULT FALSE,
    url TEXT,
    pdf_url TEXT,
    source VARCHAR(50),  -- Primary source (openalex, arxiv, etc.)
    source_id VARCHAR(255),  -- ID from primary source
    paper_type VARCHAR(50),  -- journal-article, conference-paper, preprint, etc.
    publisher VARCHAR(255),
    -- Full-text search
    title_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, ''))) STORED,
    abstract_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(abstract, ''))) STORED,
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    -- Constraints
    CHECK (doi IS NOT NULL OR source_id IS NOT NULL)
);

-- Indexes for fast lookup
CREATE UNIQUE INDEX idx_papers_doi ON papers(doi);
CREATE UNIQUE INDEX idx_papers_title_normalized ON papers(title_normalized);
CREATE INDEX idx_papers_year ON papers(year DESC);
CREATE INDEX idx_papers_source ON papers(source);
CREATE INDEX idx_papers_venue_type ON papers(venue_type);
CREATE INDEX idx_papers_is_open_access ON papers(is_open_access);
CREATE INDEX idx_papers_citations ON papers(citations DESC);

-- Full-text search indexes
CREATE INDEX idx_papers_title_tsv ON papers USING GIN (title_tsv);
CREATE INDEX idx_papers_abstract_tsv ON papers USING GIN (abstract_tsv);
CREATE INDEX idx_papers_title_trgm ON papers USING GIN (title gin_trgm_ops);

-- Table 2: Paper Sources (track which papers came from which source)
CREATE TABLE paper_sources (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER REFERENCES papers(id) ON DELETE CASCADE,
    source VARCHAR(50) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (paper_id, source)
);

CREATE INDEX idx_paper_sources_source ON paper_sources(source);
CREATE INDEX idx_paper_sources_paper_id ON paper_sources(paper_id);

-- Table 3: SLR Jobs (track SLR queries)
CREATE TABLE slr_jobs (
    id SERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    query_normalized VARCHAR(255) GENERATED ALWAYS AS (lower(regexp_replace(query, '[^a-z0-9]+', '', 'gi'))) STORED,
    sources JSONB,  -- ["openalex", "arxiv", ...]
    limit_per_source INTEGER,
    status VARCHAR(50) DEFAULT 'pending',  -- pending, running, completed, failed
    total_papers INTEGER DEFAULT 0,
    cached_papers INTEGER DEFAULT 0,
    new_papers INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX idx_slr_jobs_query_normalized ON slr_jobs(query_normalized);
CREATE INDEX idx_slr_jobs_status ON slr_jobs(status);

-- Table 4: SLR Papers (mapping SLR job to papers found)
CREATE TABLE slr_papers (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES slr_jobs(id) ON DELETE CASCADE,
    paper_id INTEGER REFERENCES papers(id) ON DELETE CASCADE,
    relevance_score FLOAT,  -- Score from API (if available)
    rank INTEGER,  -- Position in results
    UNIQUE (job_id, paper_id)
);

CREATE INDEX idx_slr_papers_job_id ON slr_papers(job_id);
CREATE INDEX idx_slr_papers_paper_id ON slr_papers(paper_id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_papers_updated_at
    BEFORE UPDATE ON papers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- View: Papers with all sources
CREATE VIEW papers_with_sources AS
SELECT 
    p.*,
    array_agg(ps.source) AS all_sources
FROM papers p
LEFT JOIN paper_sources ps ON p.id = ps.paper_id
GROUP BY p.id;

-- View: SLR job summary
CREATE VIEW slr_job_summary AS
SELECT 
    j.*,
    COUNT(sp.paper_id) AS paper_count
FROM slr_jobs j
LEFT JOIN slr_papers sp ON j.id = sp.job_id
GROUP BY j.id;
