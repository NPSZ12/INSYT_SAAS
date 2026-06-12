from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .db import LedgerDB
from .util import new_id, utc_now, json_dumps


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
    """Looks up Azure meter prices and creates fallback estimates when no match exists."""

    def __init__(self, db: LedgerDB, settings: Settings):
        self.db = db
        self.settings = settings

    def quote(self, azure_service: str, meter_name: str, quantity: float, unit: str) -> PriceQuote:
        catalog = self._lookup_catalog_price(azure_service, meter_name)
        if catalog is not None:
            unit_price = float(catalog["unit_price_usd"] or catalog["retail_price_usd"] or 0)
            unit_of_measure = catalog["unit_of_measure"] or unit
            cost = self._cost_from_catalog_unit(quantity, unit, unit_price, unit_of_measure)
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
                raw={"catalog_unit_of_measure": unit_of_measure},
            )

        return self._fallback_quote(azure_service, meter_name, quantity, unit)

    def _lookup_catalog_price(self, azure_service: str, meter_name: str) -> Any | None:
        region = self.settings.azure_region.lower()
        # Exact-ish service and meter lookup first.
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
        # Wider lookup. Useful because Azure service and meter names change over time.
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
    def _cost_from_catalog_unit(quantity: float, source_unit: str, unit_price: float, catalog_unit: str) -> float:
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

    def _fallback_quote(self, azure_service: str, meter_name: str, quantity: float, unit: str) -> PriceQuote:
        svc = azure_service.lower()
        meter = meter_name.lower()
        unit_price = 0.0
        cost = 0.0
        confidence = "low"

        if "document" in svc and "read" in meter and "page" in unit.lower():
            unit_price = self.settings.fallback_ocr_read_price_per_1000_pages
            cost = (quantity / 1000.0) * unit_price
            confidence = "medium"
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
            raw={},
        )


def sync_azure_retail_prices(db: LedgerDB, service_name: str, region: str, currency: str = "USD") -> str:
    """Fetch and store Azure Retail Prices API records.

    The Azure Retail Prices API is unauthenticated and paginated. We intentionally store
    raw JSON so meter-name changes can be audited later.
    """

    pricing_version_id = new_id("PRICE")
    fetched_at = utc_now()
    base_url = "https://prices.azure.com/api/retail/prices"
    filter_expr = f"serviceName eq '{service_name}' and armRegionName eq '{region}'"
    params = {"$filter": filter_expr, "currencyCode": currency}
    url = base_url + "?" + urllib.parse.urlencode(params)

    inserted = 0
    while url:
        with urllib.request.urlopen(url, timeout=60) as response:  # nosec: intended external API call
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

    print(f"Synced {inserted} price rows for service={service_name!r}, region={region!r}, version={pricing_version_id}")
    return pricing_version_id
