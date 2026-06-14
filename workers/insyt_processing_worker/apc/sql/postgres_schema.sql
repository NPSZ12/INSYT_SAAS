-- Production-oriented PostgreSQL schema draft for Azure Database for PostgreSQL.
-- This mirrors the local SQLite schema but uses JSONB and timestamptz.

CREATE TABLE IF NOT EXISTS processing_job (
    job_id text PRIMARY KEY,
    matter_id text NOT NULL,
    client_id text NOT NULL,
    created_at timestamptz NOT NULL,
    completed_at timestamptz,
    status text NOT NULL,
    source_bytes bigint NOT NULL DEFAULT 0,
    source_file_count bigint NOT NULL DEFAULT 0,
    expanded_bytes bigint NOT NULL DEFAULT 0,
    processed_bytes bigint NOT NULL DEFAULT 0,
    unique_doc_count bigint NOT NULL DEFAULT 0,
    duplicate_doc_count bigint NOT NULL DEFAULT 0,
    denist_suppressed_count bigint NOT NULL DEFAULT 0,
    ocr_page_count bigint NOT NULL DEFAULT 0,
    exception_count bigint NOT NULL DEFAULT 0,
    estimated_azure_cost_usd numeric(18,6) NOT NULL DEFAULT 0,
    estimated_client_bill_usd numeric(18,6) NOT NULL DEFAULT 0,
    effective_cost_per_source_gb numeric(18,6) NOT NULL DEFAULT 0,
    effective_cost_per_unique_doc numeric(18,6) NOT NULL DEFAULT 0,
    effective_cost_per_ocr_page numeric(18,6) NOT NULL DEFAULT 0,
    pricing_version_id text,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS processing_stage_run (
    stage_run_id text PRIMARY KEY,
    job_id text NOT NULL REFERENCES processing_job(job_id),
    matter_id text NOT NULL,
    stage_name text NOT NULL,
    worker_name text NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    status text NOT NULL,
    duration_ms bigint NOT NULL DEFAULT 0,
    files_in bigint NOT NULL DEFAULT 0,
    files_out bigint NOT NULL DEFAULT 0,
    bytes_in bigint NOT NULL DEFAULT 0,
    bytes_out bigint NOT NULL DEFAULT 0,
    documents_in bigint NOT NULL DEFAULT 0,
    documents_out bigint NOT NULL DEFAULT 0,
    pages_in bigint NOT NULL DEFAULT 0,
    pages_out bigint NOT NULL DEFAULT 0,
    exceptions bigint NOT NULL DEFAULT 0,
    retry_count bigint NOT NULL DEFAULT 0,
    cpu_seconds_estimated numeric(18,6) NOT NULL DEFAULT 0,
    memory_gib_seconds_estimated numeric(18,6) NOT NULL DEFAULT 0,
    estimated_cost_usd numeric(18,6) NOT NULL DEFAULT 0,
    metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS file_processing_metrics (
    file_id text PRIMARY KEY,
    matter_id text NOT NULL,
    job_id text NOT NULL REFERENCES processing_job(job_id),
    custodian_id text,
    original_path text NOT NULL,
    normalized_path text NOT NULL,
    extension text,
    mime_type text,
    source_bytes bigint NOT NULL DEFAULT 0,
    expanded_bytes bigint NOT NULL DEFAULT 0,
    page_count bigint NOT NULL DEFAULT 0,
    text_bytes bigint NOT NULL DEFAULT 0,
    has_native_text boolean NOT NULL DEFAULT false,
    requires_ocr boolean NOT NULL DEFAULT false,
    ocr_pages_submitted bigint NOT NULL DEFAULT 0,
    ocr_pages_succeeded bigint NOT NULL DEFAULT 0,
    ocr_pages_failed bigint NOT NULL DEFAULT 0,
    is_duplicate boolean NOT NULL DEFAULT false,
    duplicate_of_file_id text,
    is_denisted boolean NOT NULL DEFAULT false,
    family_id text,
    parent_file_id text,
    doc_id text,
    md5 text,
    sha1 text,
    sha256 text,
    stage_status_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    exception_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_file_metrics_job ON file_processing_metrics(job_id);
CREATE INDEX IF NOT EXISTS idx_file_metrics_hash ON file_processing_metrics(job_id, sha256);
CREATE INDEX IF NOT EXISTS idx_file_metrics_doc_id ON file_processing_metrics(job_id, doc_id);
CREATE INDEX IF NOT EXISTS idx_file_metrics_family ON file_processing_metrics(job_id, family_id);
CREATE INDEX IF NOT EXISTS idx_file_metrics_container ON file_processing_metrics(job_id, is_container, is_extracted, source_container_file_id);

CREATE TABLE IF NOT EXISTS container_expansion_event (
    event_id TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL,
    job_id TEXT NOT NULL REFERENCES processing_job(job_id),
    source_file_id TEXT NOT NULL REFERENCES file_processing_metrics(file_id),
    parent_container_file_id TEXT,
    container_path TEXT NOT NULL,
    original_container_path TEXT NOT NULL,
    container_depth INTEGER NOT NULL DEFAULT 0,
    compressed_bytes BIGINT NOT NULL DEFAULT 0,
    extracted_bytes BIGINT NOT NULL DEFAULT 0,
    extracted_file_count INTEGER NOT NULL DEFAULT 0,
    nested_container_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    exception_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_container_expansion_job ON container_expansion_event(job_id);


CREATE TABLE IF NOT EXISTS review_promotion_event (
    event_id TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    original_path TEXT NOT NULL,
    native_output_path TEXT NOT NULL,
    text_output_path TEXT NOT NULL,
    status TEXT NOT NULL,
    text_source TEXT NOT NULL,
    exception_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES processing_job(job_id),
    FOREIGN KEY(file_id) REFERENCES file_processing_metrics(file_id)
);

CREATE INDEX IF NOT EXISTS idx_review_promotion_job ON review_promotion_event(job_id);

CREATE TABLE IF NOT EXISTS cost_event (
    cost_event_id text PRIMARY KEY,
    matter_id text NOT NULL,
    job_id text NOT NULL REFERENCES processing_job(job_id),
    stage_run_id text REFERENCES processing_stage_run(stage_run_id),
    file_id text REFERENCES file_processing_metrics(file_id),
    event_time timestamptz NOT NULL,
    azure_service text NOT NULL,
    azure_resource_id text,
    meter_name text NOT NULL,
    meter_id text,
    region text,
    quantity numeric(18,6) NOT NULL,
    unit_of_measure text NOT NULL,
    unit_price_usd numeric(18,8) NOT NULL,
    estimated_cost_usd numeric(18,6) NOT NULL,
    price_source text NOT NULL,
    price_effective_date timestamptz,
    confidence text NOT NULL,
    cost_type text NOT NULL DEFAULT 'estimated',
    notes text,
    raw_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_cost_event_job ON cost_event(job_id);
CREATE INDEX IF NOT EXISTS idx_cost_event_stage ON cost_event(stage_run_id);
CREATE INDEX IF NOT EXISTS idx_cost_event_service ON cost_event(azure_service, meter_name);

CREATE TABLE IF NOT EXISTS azure_price_catalog (
    pricing_version_id text NOT NULL,
    fetched_at timestamptz NOT NULL,
    service_name text,
    service_family text,
    product_name text,
    sku_name text,
    meter_name text,
    meter_id text,
    arm_region_name text,
    location text,
    unit_of_measure text,
    retail_price_usd numeric(18,8),
    unit_price_usd numeric(18,8),
    currency_code text,
    effective_start_date timestamptz,
    tier_minimum_units numeric(18,6),
    price_type text,
    raw_price_json jsonb NOT NULL,
    PRIMARY KEY(pricing_version_id, meter_id, arm_region_name, sku_name, effective_start_date, tier_minimum_units)
);

CREATE INDEX IF NOT EXISTS idx_price_catalog_lookup
ON azure_price_catalog(service_name, meter_name, arm_region_name, effective_start_date);

CREATE TABLE IF NOT EXISTS denist_hash (
    hash_value text PRIMARY KEY,
    hash_type text NOT NULL,
    source_name text NOT NULL,
    source_version text,
    created_at timestamptz NOT NULL
);
