PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS processing_job (
    job_id TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    source_bytes INTEGER NOT NULL DEFAULT 0,
    source_file_count INTEGER NOT NULL DEFAULT 0,
    compressed_source_bytes INTEGER NOT NULL DEFAULT 0,
    expanded_bytes INTEGER NOT NULL DEFAULT 0,
    expanded_file_count INTEGER NOT NULL DEFAULT 0,
    container_file_count INTEGER NOT NULL DEFAULT 0,
    extracted_file_count INTEGER NOT NULL DEFAULT 0,
    container_exception_count INTEGER NOT NULL DEFAULT 0,
    max_container_depth INTEGER NOT NULL DEFAULT 0,
    expansion_ratio REAL NOT NULL DEFAULT 1.0,
    processed_bytes INTEGER NOT NULL DEFAULT 0,
    unique_doc_count INTEGER NOT NULL DEFAULT 0,
    duplicate_doc_count INTEGER NOT NULL DEFAULT 0,
    denist_suppressed_count INTEGER NOT NULL DEFAULT 0,
    ocr_page_count INTEGER NOT NULL DEFAULT 0,
    exception_count INTEGER NOT NULL DEFAULT 0,
    estimated_azure_cost_usd REAL NOT NULL DEFAULT 0,
    estimated_client_bill_usd REAL NOT NULL DEFAULT 0,
    effective_cost_per_source_gb REAL NOT NULL DEFAULT 0,
    effective_cost_per_unique_doc REAL NOT NULL DEFAULT 0,
    effective_cost_per_ocr_page REAL NOT NULL DEFAULT 0,
    pricing_version_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS processing_stage_run (
    stage_run_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    matter_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    worker_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    files_in INTEGER NOT NULL DEFAULT 0,
    files_out INTEGER NOT NULL DEFAULT 0,
    bytes_in INTEGER NOT NULL DEFAULT 0,
    bytes_out INTEGER NOT NULL DEFAULT 0,
    documents_in INTEGER NOT NULL DEFAULT 0,
    documents_out INTEGER NOT NULL DEFAULT 0,
    pages_in INTEGER NOT NULL DEFAULT 0,
    pages_out INTEGER NOT NULL DEFAULT 0,
    exceptions INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    cpu_seconds_estimated REAL NOT NULL DEFAULT 0,
    memory_gib_seconds_estimated REAL NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(job_id) REFERENCES processing_job(job_id)
);

CREATE TABLE IF NOT EXISTS file_processing_metrics (
    file_id TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    custodian_id TEXT,
    original_path TEXT NOT NULL,
    normalized_path TEXT NOT NULL,
    extension TEXT,
    mime_type TEXT,
    source_bytes INTEGER NOT NULL DEFAULT 0,
    expanded_bytes INTEGER NOT NULL DEFAULT 0,
    is_container INTEGER NOT NULL DEFAULT 0,
    is_extracted INTEGER NOT NULL DEFAULT 0,
    source_container_file_id TEXT,
    container_depth INTEGER NOT NULL DEFAULT 0,
    container_path TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    text_bytes INTEGER NOT NULL DEFAULT 0,
    has_native_text INTEGER NOT NULL DEFAULT 0,
    requires_ocr INTEGER NOT NULL DEFAULT 0,
    ocr_pages_submitted INTEGER NOT NULL DEFAULT 0,
    ocr_pages_succeeded INTEGER NOT NULL DEFAULT 0,
    ocr_pages_failed INTEGER NOT NULL DEFAULT 0,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    duplicate_of_file_id TEXT,
    is_denisted INTEGER NOT NULL DEFAULT 0,
    family_id TEXT,
    parent_file_id TEXT,
    doc_id TEXT,
    promoted_to_review INTEGER NOT NULL DEFAULT 0,
    native_output_path TEXT,
    text_output_path TEXT,
    review_export_status TEXT,
    md5 TEXT,
    sha1 TEXT,
    sha256 TEXT,
    stage_status_json TEXT NOT NULL DEFAULT '{}',
    exception_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES processing_job(job_id)
);

CREATE INDEX IF NOT EXISTS idx_file_metrics_job ON file_processing_metrics(job_id);
CREATE INDEX IF NOT EXISTS idx_file_metrics_hash ON file_processing_metrics(job_id, sha256);
CREATE INDEX IF NOT EXISTS idx_file_metrics_doc_id ON file_processing_metrics(job_id, doc_id);
CREATE INDEX IF NOT EXISTS idx_file_metrics_family ON file_processing_metrics(job_id, family_id);
CREATE INDEX IF NOT EXISTS idx_file_metrics_container ON file_processing_metrics(job_id, is_container, is_extracted, source_container_file_id);

CREATE TABLE IF NOT EXISTS container_expansion_event (
    event_id TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    source_file_id TEXT NOT NULL,
    parent_container_file_id TEXT,
    container_path TEXT NOT NULL,
    original_container_path TEXT NOT NULL,
    container_depth INTEGER NOT NULL DEFAULT 0,
    compressed_bytes INTEGER NOT NULL DEFAULT 0,
    extracted_bytes INTEGER NOT NULL DEFAULT 0,
    extracted_file_count INTEGER NOT NULL DEFAULT 0,
    nested_container_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    exception_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES processing_job(job_id),
    FOREIGN KEY(source_file_id) REFERENCES file_processing_metrics(file_id)
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
    cost_event_id TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    stage_run_id TEXT,
    file_id TEXT,
    event_time TEXT NOT NULL,
    azure_service TEXT NOT NULL,
    azure_resource_id TEXT,
    meter_name TEXT NOT NULL,
    meter_id TEXT,
    region TEXT,
    quantity REAL NOT NULL,
    unit_of_measure TEXT NOT NULL,
    unit_price_usd REAL NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    price_source TEXT NOT NULL,
    price_effective_date TEXT,
    confidence TEXT NOT NULL,
    cost_type TEXT NOT NULL DEFAULT 'estimated',
    notes TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(job_id) REFERENCES processing_job(job_id),
    FOREIGN KEY(stage_run_id) REFERENCES processing_stage_run(stage_run_id),
    FOREIGN KEY(file_id) REFERENCES file_processing_metrics(file_id)
);

CREATE INDEX IF NOT EXISTS idx_cost_event_job ON cost_event(job_id);
CREATE INDEX IF NOT EXISTS idx_cost_event_stage ON cost_event(stage_run_id);
CREATE INDEX IF NOT EXISTS idx_cost_event_service ON cost_event(azure_service, meter_name);

CREATE TABLE IF NOT EXISTS azure_price_catalog (
    pricing_version_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    service_name TEXT,
    service_family TEXT,
    product_name TEXT,
    sku_name TEXT,
    meter_name TEXT,
    meter_id TEXT,
    arm_region_name TEXT,
    location TEXT,
    unit_of_measure TEXT,
    retail_price_usd REAL,
    unit_price_usd REAL,
    currency_code TEXT,
    effective_start_date TEXT,
    tier_minimum_units REAL,
    price_type TEXT,
    raw_price_json TEXT NOT NULL,
    PRIMARY KEY(pricing_version_id, meter_id, arm_region_name, sku_name, effective_start_date, tier_minimum_units)
);

CREATE INDEX IF NOT EXISTS idx_price_catalog_lookup
ON azure_price_catalog(service_name, meter_name, arm_region_name, effective_start_date);

CREATE TABLE IF NOT EXISTS denist_hash (
    hash_value TEXT PRIMARY KEY,
    hash_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_version TEXT,
    created_at TEXT NOT NULL
);
