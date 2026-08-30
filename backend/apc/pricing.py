from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .db import LedgerDB
from .util import new_id, utc_now, json_dumps


AZURE_RETAIL_PRICES_URL = "https://prices.azure.com/api/retail/prices"


@dataclass(frozen=True)
class PriceQuote:
    azure_service: str
    meter_name: str
    quantity: float
    unit_of_measure: str
    unit_price_usd: float
    estimated_cost_usd: float
    price_source: str
    price_effective_date: str | None
    confidence: str
    meter_id: str | None = None
    raw: dict[str, Any] | None = None


class PricingEngine:
    """Looks up Azure meter prices and creates estimates from current Azure retail pricing.

    Estimated costs are not actual billed Azure costs. Actual cost will be populated
    later from Azure Cost Management ingestion.
    """

    def __init__(self, db: LedgerDB, settings: Settings):
        self.db = db
        self.settings = settings

    def quote(
        self,
        azure_service: str,
        meter_name: str,
        quantity: float,
        unit: str,
    ) -> PriceQuote:
        if self._is_document_read_quote(azure_service, meter_name, unit):
            live_quote = self._quote_document_intelligence_read_pages(
                quantity=quantity,
                unit=unit,
            )
            if live_quote is not None:
                return live_quote

        catalog = self._lookup_catalog_price(azure_service, meter_name)
        if catalog is not None:
            unit_price = float(
                catalog["unit_price_usd"] or catalog["retail_price_usd"] or 0
            )
            catalog_unit_of_measure = catalog["unit_of_measure"] or unit
            cost = self._cost_from_catalog_unit(
                quantity,
                unit,
                unit_price,
                catalog_unit_of_measure,
            )
            return PriceQuote(
                azure_service=azure_service,
                meter_name=meter_name,
                quantity=quantity,
                unit_of_measure=unit,
                unit_price_usd=unit_price,
                estimated_cost_usd=cost,
                price_source="azure_price_catalog",
                price_effective_date=catalog["effective_start_date"],
                confidence="medium",
                meter_id=catalog["meter_id"],
                raw={
                    "catalog_unit_of_measure": catalog_unit_of_measure,
                    "actual_cost_status": "pending_azure_cost_management_ingestion",
                    "actual_cost_usd": None,
                },
            )

        return self._fallback_quote(azure_service, meter_name, quantity, unit)

    @staticmethod
    def _is_document_read_quote(
        azure_service: str,
        meter_name: str,
        unit: str,
    ) -> bool:
        svc = str(azure_service or "").lower()
        meter = str(meter_name or "").lower()
        measure = str(unit or "").lower()

        return (
            ("document" in svc or "form recognizer" in svc or "intelligence" in svc)
            and "read" in meter
            and "page" in measure
        )

    def _quote_document_intelligence_read_pages(
        self,
        quantity: float,
        unit: str,
    ) -> PriceQuote | None:
        region = str(getattr(self.settings, "azure_region", "") or "centralus").lower()
        currency = "USD"

        price = lookup_document_intelligence_read_price(
            arm_region_name=region,
            currency_code=currency,
        )

        if price.get("status") != "current_retail_rate":
            return None

        unit_price = float(price.get("unit_price") or price.get("retail_price") or 0)
        unit_of_measure = str(price.get("unit_of_measure") or "")
        cost = self._cost_from_catalog_unit(
            quantity,
            unit,
            unit_price,
            unit_of_measure,
        )

        return PriceQuote(
            azure_service=str(price.get("product_name") or "Azure Document Intelligence"),
            meter_name=str(price.get("meter_name") or "S0 Batch Read Pages"),
            quantity=quantity,
            unit_of_measure=unit,
            unit_price_usd=unit_price,
            estimated_cost_usd=cost,
            price_source="azure_retail_prices_api_current_rate",
            price_effective_date=price.get("effective_start_date"),
            confidence="high",
            meter_id=price.get("meter_id"),
            raw={
                "pricing_basis": "azure_retail_prices_api",
                "meter_unit_of_measure": unit_of_measure,
                "retail_price_payload": price,
                "actual_cost_status": "pending_azure_cost_management_ingestion",
                "actual_cost_usd": None,
            },
        )

    def _lookup_catalog_price(self, azure_service: str, meter_name: str) -> Any | None:
        region = self.settings.azure_region.lower()

        row = self.db.query_one(
            """
            SELECT * FROM azure_price_catalog
            WHERE lower(coalesce(service_name,'')) LIKE ?
              AND lower(coalesce(meter_name,'')) LIKE ?
              AND lower(coalesce(arm_region_name,'')) IN (?, '')
              AND coalesce(price_type, 'Consumption') IN ('Consumption', 'OnDemand')
            ORDER BY effective_start_date DESC, tier_minimum_units ASC
            LIMIT 1
            """,
            (f"%{azure_service.lower()}%", f"%{meter_name.lower()}%", region),
        )
        if row:
            return row

        return self.db.query_one(
            """
            SELECT * FROM azure_price_catalog
            WHERE lower(coalesce(meter_name,'')) LIKE ?
              AND lower(coalesce(arm_region_name,'')) IN (?, '')
            ORDER BY effective_start_date DESC, tier_minimum_units ASC
            LIMIT 1
            """,
            (f"%{meter_name.lower()}%", region),
        )

    @staticmethod
    def _cost_from_catalog_unit(
        quantity: float,
        source_unit: str,
        unit_price: float,
        catalog_unit: str,
    ) -> float:
        u = (catalog_unit or "").lower().replace(",", "")
        source = (source_unit or "").lower()

        if "1k" in u or "1000" in u or "1 k" in u:
            return (quantity / 1000.0) * unit_price

        if "10k" in u or "10000" in u or "10 k" in u:
            return (quantity / 10000.0) * unit_price

        if "hour" in u and "second" in source:
            return (quantity / 3600.0) * unit_price

        if "month" in u and ("gb-day" in source or "gib-day" in source):
            return (quantity / 30.0) * unit_price

        return quantity * unit_price

    def _fallback_quote(
        self,
        azure_service: str,
        meter_name: str,
        quantity: float,
        unit: str,
    ) -> PriceQuote:
        svc = azure_service.lower()
        meter = meter_name.lower()
        unit_price = 0.0
        cost = 0.0
        confidence = "low"

        if "document" in svc and "read" in meter and "page" in unit.lower():
            unit_price = self.settings.fallback_ocr_read_price_per_1000_pages
            cost = (quantity / 1000.0) * unit_price
            confidence = "fallback_only"
        elif "container" in svc and "vcpu" in meter:
            unit_price = self.settings.fallback_containerapps_vcpu_second_price
            cost = quantity * unit_price
        elif "container" in svc and ("memory" in meter or "gib" in meter):
            unit_price = self.settings.fallback_containerapps_memory_gib_second_price
            cost = quantity * unit_price
        elif "storage" in svc and "write" in meter:
            unit_price = self.settings.fallback_blob_write_10k_price
            cost = (quantity / 10000.0) * unit_price
        elif "storage" in svc and "read" in meter:
            unit_price = self.settings.fallback_blob_read_10k_price
            cost = (quantity / 10000.0) * unit_price

        return PriceQuote(
            azure_service=azure_service,
            meter_name=meter_name,
            quantity=quantity,
            unit_of_measure=unit,
            unit_price_usd=unit_price,
            estimated_cost_usd=cost,
            price_source="fallback_config",
            price_effective_date=None,
            confidence=confidence,
            raw={
                "actual_cost_status": "pending_azure_cost_management_ingestion",
                "actual_cost_usd": None,
            },
        )


def _retail_filter(parts: list[str]) -> str:
    return " and ".join(parts)


def _request_retail_prices(
    filter_expression: str,
    *,
    max_pages: int = 3,
) -> list[dict[str, Any]]:
    params = {
        "$filter": filter_expression,
    }

    url = AZURE_RETAIL_PRICES_URL + "?" + urllib.parse.urlencode(params)

    items: list[dict[str, Any]] = []
    page_count = 0

    while url and page_count < max_pages:
        with urllib.request.urlopen(url, timeout=30) as response:  # nosec: intended Azure Retail Prices API call
            payload = json.loads(response.read().decode("utf-8"))

        items.extend(payload.get("Items", []) or [])
        url = payload.get("NextPageLink")
        page_count += 1

    return items


def _pick_document_intelligence_read_price(
    items: list[dict[str, Any]],
) -> dict[str, Any] | None:
    preferred: list[tuple[float, float, dict[str, Any]]] = []
    fallback: list[tuple[float, float, dict[str, Any]]] = []

    for item in items:
        price_type = str(item.get("type") or "").lower()
        if price_type and price_type != "consumption":
            continue

        price = item.get("retailPrice")
        if price is None:
            price = item.get("unitPrice")

        try:
            numeric_price = float(price)
        except Exception:
            continue
        
        try:
            tier_minimum = float(item.get("tierMinimumUnits") or 0)
        except Exception:
            tier_minimum = 0.0

        if numeric_price <= 0:
            continue

        combined = " ".join(
            [
                str(item.get("serviceName") or ""),
                str(item.get("productName") or ""),
                str(item.get("meterName") or ""),
                str(item.get("skuName") or ""),
            ]
        ).lower()

        excluded = any(
            phrase in combined
            for phrase in [
                "commitment",
                "connected",
                "overage",
                "container",
                "free",
            ]
        )

        if excluded:
            fallback.append((tier_minimum, numeric_price, item))
            continue

        preferred.append((tier_minimum, numeric_price, item))
        
    if preferred:
        preferred.sort(
            key=lambda row: (
                row[0],  # lowest tierMinimumUnits first
                row[1],  # then price only as tie-breaker
            )
        )
        return preferred[0][2]

    if fallback:
        fallback.sort(
            key=lambda row: (
                row[0],
                row[1],
            )
        )
        return fallback[0][2]

    return None


def lookup_document_intelligence_read_price(
    *,
    arm_region_name: str = "centralus",
    currency_code: str = "USD",
) -> dict[str, Any]:
    """Lookup current retail price for Azure Document Intelligence S0 Read pages."""

    candidate_filters = [
        _retail_filter(
            [
                "serviceFamily eq 'AI + Machine Learning'",
                f"armRegionName eq '{arm_region_name}'",
                f"currencyCode eq '{currency_code}'",
            ]
        ),
        _retail_filter(
            [
                "serviceName eq 'Foundry Tools'",
                f"armRegionName eq '{arm_region_name}'",
                f"currencyCode eq '{currency_code}'",
            ]
        ),
        _retail_filter(
            [
                "productName eq 'Azure Document Intelligence'",
                f"armRegionName eq '{arm_region_name}'",
                f"currencyCode eq '{currency_code}'",
            ]
        ),
    ]

    all_items: list[dict[str, Any]] = []
    query_errors: list[str] = []

    for filter_expression in candidate_filters:
        try:
            all_items.extend(
                _request_retail_prices(
                    filter_expression,
                    max_pages=3,
                )
            )
        except Exception as exc:
            query_errors.append(f"{filter_expression}: {exc}")

    seen: set[str] = set()
    unique_items: list[dict[str, Any]] = []

    for item in all_items:
        key = "|".join(
            [
                str(item.get("meterId") or ""),
                str(item.get("meterName") or ""),
                str(item.get("productName") or ""),
                str(item.get("skuName") or ""),
                str(item.get("armRegionName") or ""),
                str(item.get("retailPrice") or ""),
            ]
        )

        if key in seen:
            continue

        seen.add(key)
        unique_items.append(item)

    read_candidates: list[dict[str, Any]] = []

    for item in unique_items:
        service_name = str(item.get("serviceName") or "").lower()
        product_name = str(item.get("productName") or "").lower()
        meter_name = str(item.get("meterName") or "").lower()
        sku_name = str(item.get("skuName") or "").lower()

        combined = " ".join(
            [
                service_name,
                product_name,
                meter_name,
                sku_name,
            ]
        )

        is_document_product = any(
            phrase in combined
            for phrase in [
                "azure document intelligence",
                "document intelligence",
                "form recognizer",
            ]
        )

        is_read_meter = "read" in meter_name or "read" in sku_name

        wrong_product = any(
            phrase in combined
            for phrase in [
                "openai",
                "speech",
                "translator",
                "search",
                "language",
                "vision",
                "face",
                "anomaly",
            ]
        )

        if is_document_product and is_read_meter and not wrong_product:
            read_candidates.append(item)

    selected = _pick_document_intelligence_read_price(read_candidates)

    if not selected:
        fallback_per_1000 = float(
            os.getenv("APC_FALLBACK_DOCUMENT_INTELLIGENCE_READ_PER_1000", "1.5")
        )

        return {
            "status": "fallback",
            "reason": "azure_retail_prices_api_no_matching_standard_s0_read_meter",
            "service_name": "Azure Document Intelligence",
            "meter_name": "S0 Batch Read Pages",
            "arm_region_name": arm_region_name,
            "currency_code": currency_code,
            "unit_of_measure": "1K",
            "retail_price": fallback_per_1000,
            "unit_price": fallback_per_1000,
            "source": "fallback_env_or_default",
            "candidate_count": len(read_candidates),
            "searched_item_count": len(unique_items),
            "query_error_count": len(query_errors),
            "query_errors": query_errors[:5],
        }

    return {
        "status": "current_retail_rate",
        "meter_id": selected.get("meterId"),
        "meter_name": selected.get("meterName"),
        "product_name": selected.get("productName"),
        "service_name": selected.get("serviceName"),
        "sku_name": selected.get("skuName"),
        "arm_region_name": selected.get("armRegionName") or arm_region_name,
        "unit_of_measure": selected.get("unitOfMeasure") or "",
        "currency_code": selected.get("currencyCode") or currency_code,
        "retail_price": float(selected.get("retailPrice") or 0),
        "unit_price": float(selected.get("unitPrice") or selected.get("retailPrice") or 0),
        "effective_start_date": selected.get("effectiveStartDate"),
        "source": "azure_retail_prices_api",
        "candidate_count": len(read_candidates),
        "searched_item_count": len(unique_items),
        "query_error_count": len(query_errors),
    }


def sync_azure_retail_prices(
    db: LedgerDB,
    service_name: str,
    region: str,
    currency: str = "USD",
) -> str:
    """Fetch and store Azure Retail Prices API records.

    The Azure Retail Prices API is unauthenticated and paginated. We intentionally store
    raw JSON so meter-name changes can be audited later.
    """

    pricing_version_id = new_id("PRICE")
    fetched_at = utc_now()
    filter_expr = f"serviceName eq '{service_name}' and armRegionName eq '{region}' and currencyCode eq '{currency}'"
    params = {"$filter": filter_expr}
    url = AZURE_RETAIL_PRICES_URL + "?" + urllib.parse.urlencode(params)

    inserted = 0

    while url:
        with urllib.request.urlopen(url, timeout=60) as response:  # nosec: intended Azure Retail Prices API call
            payload = json.loads(response.read().decode("utf-8"))

        for item in payload.get("Items", []):
            db.execute(
                """
                INSERT OR REPLACE INTO azure_price_catalog (
                    pricing_version_id, fetched_at, service_name, service_family,
                    product_name, sku_name, meter_name, meter_id, arm_region_name,
                    location, unit_of_measure, retail_price_usd, unit_price_usd,
                    currency_code, effective_start_date, tier_minimum_units,
                    price_type, raw_price_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    pricing_version_id,
                    fetched_at,
                    item.get("serviceName"),
                    item.get("serviceFamily"),
                    item.get("productName"),
                    item.get("skuName"),
                    item.get("meterName"),
                    item.get("meterId"),
                    item.get("armRegionName"),
                    item.get("location"),
                    item.get("unitOfMeasure"),
                    item.get("retailPrice"),
                    item.get("unitPrice"),
                    item.get("currencyCode"),
                    item.get("effectiveStartDate"),
                    item.get("tierMinimumUnits"),
                    item.get("type") or item.get("priceType"),
                    json_dumps(item),
                ),
            )
            inserted += 1

        url = payload.get("NextPageLink")

    print(
        f"Synced {inserted} price rows for service={service_name!r}, "
        f"region={region!r}, version={pricing_version_id}"
    )

    return pricing_version_id