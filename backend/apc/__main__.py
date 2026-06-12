from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .config import DEFAULT_SETTINGS, Settings
from .db import LedgerDB
from .orchestrator import run_local_pipeline
from .pricing import sync_azure_retail_prices
from .reports import export_job_report, job_cost_report, latest_job_id
from .azure_layout import AzureRoutingConfig, build_azure_routing_summary, build_review_promotion_blob_plan, export_azure_plan
from .azure_blob_adapter import (
    azure_list_uploads,
    azure_download_uploads,
    azure_upload_review_outputs,
    azure_upload_report_files,
    AzureDependencyError,
)
from .azure_job_runner import run_azure_processing_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apc", description="Azure Processing Center v0.9")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the local telemetry-first processing pipeline")
    run.add_argument("--input", required=True, help="Input directory. ZIP files inside this folder are expanded locally in v0.4.")
    run.add_argument("--db", default=DEFAULT_SETTINGS.db_path, help="SQLite ledger path")
    run.add_argument("--matter-id", required=True)
    run.add_argument("--client-id", required=True)
    run.add_argument("--custodian-id")
    run.add_argument("--doc-prefix", default="INSYT")
    run.add_argument("--denist-hash-file")
    run.add_argument("--enable-ocr-dry-run", action="store_true")
    run.add_argument("--enable-live-ocr", action="store_true")
    run.add_argument("--promote-review-ready", action="store_true", help="Create review-ready source/native and source/text output using assigned Doc IDs")
    run.add_argument("--output-root", help="Output root for local review-ready promotion. Defaults to <input_parent>/.apc_review_output")

    report = sub.add_parser("report", help="Print a job cost report")
    report.add_argument("--db", default=DEFAULT_SETTINGS.db_path)
    group = report.add_mutually_exclusive_group(required=True)
    group.add_argument("--job-id")
    group.add_argument("--latest", action="store_true")
    report.add_argument("--export-dir", help="Optional directory for TXT/JSON/CSV report exports")

    price = sub.add_parser("price-sync", help="Sync Azure Retail Prices API records into the local ledger")
    price.add_argument("--db", default=DEFAULT_SETTINGS.db_path)
    price.add_argument("--service-name", required=True, help="Exact Azure serviceName filter")
    price.add_argument("--region", default=DEFAULT_SETTINGS.azure_region, help="Azure armRegionName, e.g. eastus")
    price.add_argument("--currency", default="USD")


    azure = sub.add_parser("azure-plan", help="Validate Azure storage routing and generate dry-run Blob read/write plans")
    azure.add_argument("--workspace", default="capture", choices=["capture", "discovery", "summaries"], help="INSYT workspace")
    azure.add_argument("--client", required=True, help="INSYT client folder/id")
    azure.add_argument("--project", required=True, help="INSYT project folder/id")
    azure.add_argument("--processing-account", default=None, help="Processing storage account. Defaults to INSYT_PROCESSING_STORAGE_ACCOUNT or insytprodstorage")
    azure.add_argument("--review-account", default=None, help="Review output storage account. Defaults to INSYT_REVIEW_STORAGE_ACCOUNT or cdsintakestorage")
    azure.add_argument("--processing-container", default=None, help="Processing container. Defaults to insyt-<workspace>")
    azure.add_argument("--review-container", default=None, help="Review output container. Defaults to insyt-<workspace>")
    azure.add_argument("--azure-write", action="store_true", help="Mark plan as write-enabled for planning only. Use azure-upload-review for actual writes.")
    azure.add_argument("--allow-same-account", action="store_true", help="Allow same storage account for processing and review outputs for intentional non-production tests")
    azure.add_argument("--db", default=DEFAULT_SETTINGS.db_path, help="SQLite ledger path if creating a job-specific promotion plan")
    job_group = azure.add_mutually_exclusive_group(required=False)
    job_group.add_argument("--job-id")
    job_group.add_argument("--latest", action="store_true")
    azure.add_argument("--export-dir", help="Optional directory for Azure routing JSON/CSV exports")


    azure_list = sub.add_parser("azure-list-uploads", help="List blobs from the processing upload path in insytprodstorage")
    azure_list.add_argument("--workspace", default="capture", choices=["capture", "discovery", "summaries"])
    azure_list.add_argument("--client", required=True)
    azure_list.add_argument("--project", required=True)
    azure_list.add_argument("--processing-account", default=None)
    azure_list.add_argument("--review-account", default=None)
    azure_list.add_argument("--processing-container", default=None)
    azure_list.add_argument("--review-container", default=None)
    azure_list.add_argument("--allow-same-account", action="store_true")
    azure_list.add_argument("--export-dir")

    azure_dl = sub.add_parser("azure-download-uploads", help="Download processing uploads to local/worker temp staging. In production this is Azure worker temp storage, not a personal computer.")
    azure_dl.add_argument("--workspace", default="capture", choices=["capture", "discovery", "summaries"])
    azure_dl.add_argument("--client", required=True)
    azure_dl.add_argument("--project", required=True)
    azure_dl.add_argument("--destination", required=True, help="Local or Azure-worker temp staging folder")
    azure_dl.add_argument("--processing-account", default=None)
    azure_dl.add_argument("--review-account", default=None)
    azure_dl.add_argument("--processing-container", default=None)
    azure_dl.add_argument("--review-container", default=None)
    azure_dl.add_argument("--allow-same-account", action="store_true")
    azure_dl.add_argument("--overwrite", action="store_true")
    azure_dl.add_argument("--export-dir")

    azure_upload = sub.add_parser("azure-upload-review", help="Upload local review-ready source/native and source/text outputs to cdsintakestorage. Requires --azure-write.")
    azure_upload.add_argument("--workspace", default="capture", choices=["capture", "discovery", "summaries"])
    azure_upload.add_argument("--client", required=True)
    azure_upload.add_argument("--project", required=True)
    azure_upload.add_argument("--local-review-root", required=True, help="Folder containing source/native and source/text created by --promote-review-ready")
    azure_upload.add_argument("--processing-account", default=None)
    azure_upload.add_argument("--review-account", default=None)
    azure_upload.add_argument("--processing-container", default=None)
    azure_upload.add_argument("--review-container", default=None)
    azure_upload.add_argument("--allow-same-account", action="store_true")
    azure_upload.add_argument("--azure-write", action="store_true", help="Required before any Azure write is performed")
    azure_upload.add_argument("--overwrite", action="store_true")
    azure_upload.add_argument("--db", default=DEFAULT_SETTINGS.db_path)
    jg = azure_upload.add_mutually_exclusive_group(required=True)
    jg.add_argument("--job-id")
    jg.add_argument("--latest", action="store_true")
    azure_upload.add_argument("--export-dir")


    azure_run = sub.add_parser("azure-run", help="Run the full Azure intake -> processing -> review upload flow. Writes require --azure-write.")
    azure_run.add_argument("--workspace", default="capture", choices=["capture", "discovery", "summaries"])
    azure_run.add_argument("--client", required=True)
    azure_run.add_argument("--project", required=True)
    azure_run.add_argument("--matter-id", required=True)
    azure_run.add_argument("--doc-prefix", default="INSYT")
    azure_run.add_argument("--db", default=DEFAULT_SETTINGS.db_path)
    azure_run.add_argument("--processing-account", default=None)
    azure_run.add_argument("--review-account", default=None)
    azure_run.add_argument("--processing-container", default=None)
    azure_run.add_argument("--review-container", default=None)
    azure_run.add_argument("--allow-same-account", action="store_true")
    azure_run.add_argument("--enable-ocr-dry-run", action="store_true")
    azure_run.add_argument("--enable-live-ocr", action="store_true")
    azure_run.add_argument("--azure-write", action="store_true", help="Required before review-ready outputs/reports are uploaded to cdsintakestorage")
    azure_run.add_argument("--overwrite", action="store_true")
    azure_run.add_argument("--staging-root", default=".apc_azure_runs", help="Worker temp staging root. In production this is Azure worker temp storage.")
    azure_run.add_argument("--output-root", default=".apc_azure_review_output", help="Temporary review-ready output root before Azure promotion")
    azure_run.add_argument("--export-dir", default=".\reports", help="Report/export directory")
    azure_run.add_argument("--clean-staging", action="store_true", help="Delete downloaded staging files and temporary review output after successful run")

    api = sub.add_parser("api", help="Run the FastAPI Processing Center API using uvicorn")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8090)
    api.add_argument("--reload", action="store_true")

    init = sub.add_parser("init-db", help="Initialize the local database schema")
    init.add_argument("--db", default=DEFAULT_SETTINGS.db_path)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "api":
        try:
            import uvicorn  # type: ignore
        except Exception:
            print("FastAPI server dependencies are not installed. Run: pip install -e .[api,azure]", file=sys.stderr)
            return 2
        uvicorn.run("apc.api:app", host=args.host, port=args.port, reload=args.reload)
        return 0

    if args.command == "init-db":
        db = LedgerDB(args.db)
        try:
            db.init_schema()
            print(f"Initialized database: {args.db}")
        finally:
            db.close()
        return 0

    if args.command == "run":
        db = LedgerDB(args.db)
        settings = DEFAULT_SETTINGS
        try:
            db.init_schema()
            job_id = run_local_pipeline(
                db=db,
                settings=settings,
                input_dir=args.input,
                matter_id=args.matter_id,
                client_id=args.client_id,
                doc_prefix=args.doc_prefix,
                custodian_id=args.custodian_id,
                denist_hash_file=args.denist_hash_file,
                enable_ocr_dry_run=args.enable_ocr_dry_run,
                enable_live_ocr=args.enable_live_ocr,
                promote_review_ready=args.promote_review_ready,
                output_root=args.output_root,
            )
            print(f"Created job: {job_id}")
            print(f"Run report: python -m apc report --db {args.db} --job-id {job_id}")
        finally:
            db.close()
        return 0

    if args.command == "report":
        db = LedgerDB(args.db)
        try:
            db.init_schema()
            job_id = latest_job_id(db) if args.latest else args.job_id
            if not job_id:
                print("No jobs found.", file=sys.stderr)
                return 2
            print(job_cost_report(db, job_id))
            if args.export_dir:
                exported = export_job_report(db, job_id, args.export_dir)
                print("\nExported report files:")
                for label, path in exported.items():
                    print(f"- {label}: {path}")
        finally:
            db.close()
        return 0


    if args.command == "azure-plan":
        routing = AzureRoutingConfig.from_args(
            workspace=args.workspace,
            client=args.client,
            project=args.project,
            processing_account=args.processing_account,
            review_account=args.review_account,
            processing_container=args.processing_container,
            review_container=args.review_container,
            azure_write=args.azure_write,
            allow_same_account=args.allow_same_account,
        )
        warnings = routing.validate()
        db = LedgerDB(args.db)
        try:
            db.init_schema()
            job_id = latest_job_id(db) if args.latest else args.job_id
            promotion_plan = build_review_promotion_blob_plan(db, job_id, routing) if job_id else []
            summary = build_azure_routing_summary(routing, job_id=job_id, promotion_count=len(promotion_plan))
            print("Azure Processing Center Routing Plan")
            print(f"Mode: {'AZURE WRITE ENABLED' if routing.azure_write else 'DRY RUN ONLY'}")
            print(f"Workspace: {routing.workspace}")
            print(f"Client: {routing.client}")
            print(f"Project: {routing.project}")
            print("")
            print("Processing / staging account")
            print(f"- Account: {routing.processing_account}")
            print(f"- Container: {routing.processing_container}")
            for label, path in routing.processing_paths().items():
                print(f"- {label}: {path}")
            print("")
            print("Review-ready output account")
            print(f"- Account: {routing.review_account}")
            print(f"- Container: {routing.review_container}")
            for label, path in routing.review_paths().items():
                print(f"- {label}: {path}")
            if job_id:
                print("")
                print(f"Promotion plan from job {job_id}")
                print(f"- Reviewable docs planned: {len(promotion_plan)}")
                for row in promotion_plan[:5]:
                    print(f"- {row['doc_id']}: {row['native_blob_path']} | {row['text_blob_path']}")
                if len(promotion_plan) > 5:
                    print(f"- ... {len(promotion_plan)-5} more")
            if warnings:
                print("")
                print("Warnings")
                for warning in warnings:
                    print(f"- {warning}")
            if args.export_dir:
                exported = export_azure_plan(args.export_dir, job_id, summary, promotion_plan)
                print("\nExported Azure plan files:")
                for label, path in exported.items():
                    print(f"- {label}: {path}")
        finally:
            db.close()
        return 0


    if args.command == "azure-list-uploads":
        routing = AzureRoutingConfig.from_args(
            workspace=args.workspace,
            client=args.client,
            project=args.project,
            processing_account=args.processing_account,
            review_account=args.review_account,
            processing_container=args.processing_container,
            review_container=args.review_container,
            azure_write=False,
            allow_same_account=args.allow_same_account,
        )
        try:
            warnings = routing.validate()
            rows = azure_list_uploads(routing, export_dir=args.export_dir)
            print("Azure Processing Uploads")
            print(f"Account: {routing.processing_account}")
            print(f"Container: {routing.processing_container}")
            print(f"Prefix: {routing.processing_paths()['uploads']}")
            print(f"Uploads found: {len(rows)}")
            for row in rows[:20]:
                print(f"- {row['name']} ({row['size']} bytes)")
            if len(rows) > 20:
                print(f"- ... {len(rows)-20} more")
            if warnings:
                print("\nWarnings")
                for warning in warnings:
                    print(f"- {warning}")
            if args.export_dir:
                print(f"\nExported upload list: {args.export_dir}\\azure_processing_uploads.json")
        except AzureDependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0

    if args.command == "azure-download-uploads":
        routing = AzureRoutingConfig.from_args(
            workspace=args.workspace,
            client=args.client,
            project=args.project,
            processing_account=args.processing_account,
            review_account=args.review_account,
            processing_container=args.processing_container,
            review_container=args.review_container,
            azure_write=False,
            allow_same_account=args.allow_same_account,
        )
        try:
            warnings = routing.validate()
            rows = azure_download_uploads(routing, args.destination, overwrite=args.overwrite, export_dir=args.export_dir)
            print("Azure Processing Upload Download")
            print(f"Source: {routing.processing_account}/{routing.processing_container}/{routing.processing_paths()['uploads']}")
            print(f"Destination: {args.destination}")
            print(f"Files handled: {len(rows)}")
            for row in rows[:20]:
                print(f"- {row['status']}: {row['blob_name']} -> {row['local_path']}")
            if len(rows) > 20:
                print(f"- ... {len(rows)-20} more")
            if warnings:
                print("\nWarnings")
                for warning in warnings:
                    print(f"- {warning}")
        except AzureDependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0

    if args.command == "azure-upload-review":
        routing = AzureRoutingConfig.from_args(
            workspace=args.workspace,
            client=args.client,
            project=args.project,
            processing_account=args.processing_account,
            review_account=args.review_account,
            processing_container=args.processing_container,
            review_container=args.review_container,
            azure_write=args.azure_write,
            allow_same_account=args.allow_same_account,
        )
        db = LedgerDB(args.db)
        try:
            db.init_schema()
            job_id = latest_job_id(db) if args.latest else args.job_id
            payload = azure_upload_review_outputs(
                db=db,
                routing=routing,
                job_id=job_id,
                local_review_root=args.local_review_root,
                azure_write=args.azure_write,
                overwrite=args.overwrite,
                export_dir=args.export_dir,
            )
            print("Azure Review Output Upload")
            print(f"Mode: AZURE WRITE ENABLED")
            print(f"Job: {job_id}")
            print(f"Review output: {routing.review_account}/{routing.review_container}")
            print(f"Uploaded items: {sum(1 for r in payload['uploads'] if r['status'] == 'uploaded')}")
            failures = [r for r in payload['uploads'] if r['status'] != 'uploaded']
            print(f"Failures/skips: {len(failures)}")
            for row in payload['uploads'][:20]:
                print(f"- {row['status']}: {row['blob_path']}")
            if len(payload['uploads']) > 20:
                print(f"- ... {len(payload['uploads'])-20} more")
        except AzureDependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        finally:
            db.close()
        return 0

    if args.command == "azure-run":
        routing = AzureRoutingConfig.from_args(
            workspace=args.workspace,
            client=args.client,
            project=args.project,
            processing_account=args.processing_account,
            review_account=args.review_account,
            processing_container=args.processing_container,
            review_container=args.review_container,
            azure_write=args.azure_write,
            allow_same_account=args.allow_same_account,
        )
        db = LedgerDB(args.db)
        try:
            db.init_schema()
            result = run_azure_processing_job(
                db=db,
                routing=routing,
                matter_id=args.matter_id,
                doc_prefix=args.doc_prefix,
                enable_ocr_dry_run=args.enable_ocr_dry_run,
                enable_live_ocr=args.enable_live_ocr,
                azure_write=args.azure_write,
                overwrite=args.overwrite,
                staging_root=args.staging_root,
                output_root=args.output_root,
                export_dir=args.export_dir,
                clean_staging=args.clean_staging,
                upload_status=True,
            )
            print("Azure Processing Center End-to-End Run")
            print(f"Mode: {'AZURE WRITE ENABLED' if args.azure_write else 'DRY RUN OUTPUT UPLOAD'}")
            print(f"Workspace: {routing.workspace}")
            print(f"Client: {routing.client}")
            print(f"Project: {routing.project}")
            print(f"Processing source: {routing.processing_account}/{routing.processing_container}/{routing.processing_paths()['uploads']}")
            print(f"Review output: {routing.review_account}/{routing.review_container}")
            for warning in result.warnings:
                print(f"Warning: {warning}")
            print(f"Downloaded/staged uploads: {len([r for r in result.downloads if r.get('status') in {'downloaded', 'skipped_exists'}])}")
            if result.job_id:
                print(f"Created job: {result.job_id}")
            if result.local_review_root:
                print(f"Local/worker review output: {result.local_review_root}")
            if result.report_files:
                print("Exported local report files:")
                for label, path in result.report_files.items():
                    print(f"- {label}: {path}")
            if result.review_upload:
                uploaded = sum(1 for r in result.review_upload['uploads'] if r['status'] == 'uploaded')
                failures = [r for r in result.review_upload['uploads'] if r['status'] != 'uploaded']
                print(f"Uploaded review Native/Text items: {uploaded}")
                print(f"Review upload failures/skips: {len(failures)}")
            if result.report_upload:
                print(f"Uploaded report/manifest files: {len(result.report_upload['uploaded_reports'])}")
            if result.status_upload:
                print(f"Uploaded job status: {result.status_upload['blob_path']}")
            print(f"Run status: {result.status}")
            print("Run complete.")
            return 0 if result.status == "completed" else 2
        except AzureDependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        finally:
            db.close()

    if args.command == "price-sync":
        db = LedgerDB(args.db)
        try:
            db.init_schema()
            sync_azure_retail_prices(db, service_name=args.service_name, region=args.region, currency=args.currency)
        finally:
            db.close()
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
