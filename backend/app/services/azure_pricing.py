from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


AZURE_RETAIL_PRICES_URL = "https://prices.azure.com/api/retail/prices"

_CACHE_TTL_SECONDS = 60 * 60 * 12
_PRICE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


@dataclass
class AzureRetailPrice:
    meter_name: str
    product_name: str
    service_name: str
    sku_name: str
    arm_region_name: str
    unit_of_measure: str
    currency_code: str
    retail_price: float
    unit_price: float
    effective_start_date: str | None
    source: str = "azure_retail_prices_api"

    def to_dict(self) -> dict[str, Any]:
        return {
            "meter_name": self.meter_name,
            "product_name": self.product_name,
            "service_name": self.service_name,
            "sku_name": self.sku_name,
            "arm_region_name": self.arm_region_name,
            "unit_of_measure": self.unit_of_measure,
            "currency_code": self.currency_code,
            "retail_price": self.retail_price,
            "unit_price": self.unit_price,
            "effective_start_date": self.effective_start_date,
            "source": self.source,
        }


def _cache_get(key: str) -> dict[str, Any] | None:
    cached = _PRICE_CACHE.get(key)
    if not cached:
        return None

    cached_at, payload = cached
    if time.time() - cached_at > _CACHE_TTL_SECONDS:
        _PRICE_CACHE.pop(key, None)
        return None

    return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    _PRICE_CACHE[key] = (time.time(), payload)


def _retail_filter(parts: list[str]) -> str:
    return " and ".join(parts)


def _request_retail_prices(filter_expression: str) -> list[dict[str, Any]]:
    params = {
        "$filter": filter_expression,
    }

    response = requests.get(
        AZURE_RETAIL_PRICES_URL,
        params=params,
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    items = data.get("Items") or []

    next_page = data.get("NextPageLink")
    while next_page:
        next_response = requests.get(next_page, timeout=20)
        next_response.raise_for_status()
        next_data = next_response.json()
        items.extend(next_data.get("Items") or [])
        next_page = next_data.get("NextPageLink")

    return items


def _pick_lowest_consumption_price(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = []

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

        if numeric_price < 0:
            continue

        usable.append((numeric_price, item))

    if not usable:
        return None

    usable.sort(key=lambda row: row[0])
    return usable[0][1]


def lookup_document_intelligence_read_price(
    *,
    arm_region_name: str = "centralus",
    currency_code: str = "USD",
) -> dict[str, Any]:
    """Lookup current retail price for Azure AI Document Intelligence Read.

    This returns Microsoft retail pricing, not discounted contract pricing and
    not actual billed cost. It is suitable for pre-run quoting.
    """

    cache_key = f"document-intelligence-read:{arm_region_name}:{currency_code}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    candidate_filters = [
        _retail_filter(
            [
                "serviceName eq 'Azure AI Document Intelligence'",
                f"armRegionName eq '{arm_region_name}'",
                f"currencyCode eq '{currency_code}'",
            ]
        ),
        _retail_filter(
            [
                "serviceName eq 'Azure Cognitive Services'",
                f"armRegionName eq '{arm_region_name}'",
                f"currencyCode eq '{currency_code}'",
            ]
        ),
    ]

    all_items: list[dict[str, Any]] = []

    for filter_expression in candidate_filters:
        try:
            items = _request_retail_prices(filter_expression)
            all_items.extend(items)
        except Exception:
            continue

    read_candidates = []
    for item in all_items:
        text = " ".join(
            [
                str(item.get("productName") or ""),
                str(item.get("meterName") or ""),
                str(item.get("skuName") or ""),
            ]
        ).lower()

        if "read" in text and (
            "document" in text
            or "form recognizer" in text
            or "intelligence" in text
        ):
            read_candidates.append(item)

    selected = _pick_lowest_consumption_price(read_candidates)

    if not selected:
        fallback_per_1000 = float(
            os.getenv("APC_FALLBACK_DOCUMENT_INTELLIGENCE_READ_PER_1000", "1.5")
        )

        payload = {
            "status": "fallback",
            "reason": "azure_retail_prices_api_no_matching_read_meter",
            "service_name": "Azure AI Document Intelligence",
            "meter_name": "Read",
            "arm_region_name": arm_region_name,
            "currency_code": currency_code,
            "unit_of_measure": "1K Pages",
            "retail_price": fallback_per_1000,
            "unit_price": fallback_per_1000,
            "source": "fallback_env_or_default",
        }
        _cache_set(cache_key, payload)
        return payload

    payload = AzureRetailPrice(
        meter_name=str(selected.get("meterName") or ""),
        product_name=str(selected.get("productName") or ""),
        service_name=str(selected.get("serviceName") or ""),
        sku_name=str(selected.get("skuName") or ""),
        arm_region_name=str(selected.get("armRegionName") or arm_region_name),
        unit_of_measure=str(selected.get("unitOfMeasure") or ""),
        currency_code=str(selected.get("currencyCode") or currency_code),
        retail_price=float(selected.get("retailPrice") or 0),
        unit_price=float(selected.get("unitPrice") or selected.get("retailPrice") or 0),
        effective_start_date=selected.get("effectiveStartDate"),
    ).to_dict()

    payload["status"] = "current_retail_rate"

    _cache_set(cache_key, payload)
    return payload


def calculate_document_intelligence_read_quote(
    *,
    pages: int,
    arm_region_name: str = "centralus",
    currency_code: str = "USD",
) -> dict[str, Any]:
    price = lookup_document_intelligence_read_price(
        arm_region_name=arm_region_name,
        currency_code=currency_code,
    )

    page_count = max(int(pages or 0), 0)
    unit_price = float(price.get("unit_price") or price.get("retail_price") or 0)
    unit_of_measure = str(price.get("unit_of_measure") or "")

    normalized_unit = unit_of_measure.lower()
    if "1k" in normalized_unit or "1000" in normalized_unit:
        estimated_cost = (page_count / 1000) * unit_price
        billing_unit_pages = 1000
    else:
        estimated_cost = page_count * unit_price
        billing_unit_pages = 1

    return {
        "status": "estimated_from_current_azure_retail_price",
        "page_count": page_count,
        "estimated_cost_usd": round(estimated_cost, 8),
        "billing_unit_pages": billing_unit_pages,
        "price": price,
        "actual_cost_status": "pending_azure_cost_management_ingestion",
        "actual_cost_usd": None,
    }