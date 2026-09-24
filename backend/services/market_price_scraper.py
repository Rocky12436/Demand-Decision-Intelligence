"""
backend/services/market_price_scraper.py
----------------------------------------
Scrapes real-time commodity prices from the official Government of India portal:
Ministry of Consumer Affairs, Food and Public Distribution - Price Monitoring Division (PMD)
URL: https://fcainfoweb.nic.in/Default.aspx

Hardened with:
- Dedicated HTML parsing function testable against saved fixtures (no live network in tests)
- Exponential backoff retry logic (1s, 2s, 4s)
- Realistic User-Agent and connection timeout handling
- Persistence to `PriceObservation` database table (append-only)
- Graceful fallback to DB cached last-good response and JSON cache
- Stale tracking: `is_stale` flag if > 24 hours, `suppress_stocking_decisions` if > 7 days
"""

import json
import logging
import re
import ssl
import time
import urllib.request
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.market_price import PriceObservation

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
CACHE_FILE = REPORTS_DIR / "live_market_prices.json"

FCA_URL = "https://fcainfoweb.nic.in/Default.aspx"

# Category mapping based on PMD GridView layouts
CATEGORY_MAPPING = {
    "Rice": "Grains & Pulses",
    "Wheat": "Grains & Pulses",
    "Atta (Wheat)": "Grains & Pulses",
    "Gram Dal": "Grains & Pulses",
    "Tur/Arhar Dal": "Grains & Pulses",
    "Urad Dal": "Grains & Pulses",
    "Moong Dal": "Grains & Pulses",
    "Masoor Dal": "Grains & Pulses",
    "Broken Rice": "Grains & Pulses",
    "Groundnut Oil (Packed)": "Edible Oils",
    "Mustard Oil (Packed)": "Edible Oils",
    "Vanaspati (Packed)": "Edible Oils",
    "Soya Oil (Packed)": "Edible Oils",
    "Sunflower Oil (Packed)": "Edible Oils",
    "Palm Oil (Packed)": "Edible Oils",
    "Potato": "Vegetables",
    "Onion": "Vegetables",
    "Tomato": "Vegetables",
    "Sugar": "Daily Essentials",
    "Gur": "Daily Essentials",
    "Milk @": "Daily Essentials",
    "Tea Loose": "Daily Essentials",
    "Salt Pack (Iodised)": "Daily Essentials",
    "Bajra (whole)": "Additional Millets",
    "Jowar (whole)": "Additional Millets",
    "Ragi": "Additional Millets",
    "Maize": "Additional Millets",
    "Barley": "Additional Millets",
}


def parse_pmd_html(html: str) -> Dict[str, Any]:
    """
    Parses raw PMD HTML to extract reporting date and retail commodity prices.
    Pure parsing function decoupled from network calls.
    """
    date_match = re.search(r'id="[^"]*lblDate1">([^<]+)<', html)
    as_on_date = date_match.group(1).strip() if date_match else datetime.now().strftime("%d/%m/%Y")

    comm_names = re.findall(r'lblCommName">([^<]+)<', html)
    prices = re.findall(r'lblPrices">([0-9.]+)<', html)

    items: List[Dict[str, Any]] = []
    if comm_names and prices:
        seen = set()
        for name, price in zip(comm_names, prices):
            clean_name = name.strip()
            if clean_name in seen:
                continue
            seen.add(clean_name)
            category = CATEGORY_MAPPING.get(clean_name, "Grains & Essentials")
            items.append({
                "commodity": clean_name,
                "price_inr_per_kg": float(price),
                "category": category,
                "unit": "₹ / Kg",
                "as_on_date": as_on_date,
                "source": "Ministry of Consumer Affairs, Food and Public Distribution (PMD)"
            })

    return {
        "status": "live",
        "as_on_date": as_on_date,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_commodities": len(items),
        "source_url": FCA_URL,
        "commodities": items,
        "is_stale": False,
        "stale_days": 0,
        "suppress_stocking_decisions": False,
    }


def persist_observations_to_db(db: Session, commodities: List[Dict[str, Any]], as_on_date_str: str) -> int:
    """
    Saves scraped commodity prices as new records in price_observations table.
    Does not overwrite or wipe historical data (append-only).
    """
    try:
        # Parse DD/MM/YYYY into date
        try:
            obs_date = datetime.strptime(as_on_date_str, "%d/%m/%Y").date()
        except Exception:
            obs_date = date.today()

        count = 0
        for item in commodities:
            comm_code = item["commodity"].upper().replace(" ", "_").replace("(", "").replace(")", "").replace("@", "").strip("_")
            obs = PriceObservation(
                commodity_code=comm_code,
                market_name="National_Average",
                observed_date=obs_date,
                wholesale_price=None,
                retail_price=item["price_inr_per_kg"],
                unit="Rs/kg",
                source="fcainfoweb.nic.in",
            )
            db.add(obs)
            count += 1
        db.commit()
        return count
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to persist price observations to DB: {e}")
        return 0


def fetch_from_db_cache(db: Session) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent price observation snapshot from the database.
    """
    try:
        latest_date = db.query(func.max(PriceObservation.observed_date)).scalar()
        if not latest_date:
            return None

        rows = (
            db.query(PriceObservation)
            .filter(PriceObservation.observed_date == latest_date)
            .all()
        )
        if not rows:
            return None

        stale_days = (date.today() - latest_date).days
        is_stale = stale_days >= 1
        suppress = stale_days > 7

        items = []
        for r in rows:
            # Reconstruct original title name from code
            clean_name = r.commodity_code.replace("_", " ").title()
            items.append({
                "commodity": clean_name,
                "price_inr_per_kg": r.retail_price,
                "category": CATEGORY_MAPPING.get(clean_name, "Grains & Essentials"),
                "unit": "₹ / Kg",
                "as_on_date": latest_date.strftime("%d/%m/%Y"),
                "source": r.source,
            })

        return {
            "status": "cached_db",
            "as_on_date": latest_date.strftime("%d/%m/%Y"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "total_commodities": len(items),
            "source_url": FCA_URL,
            "commodities": items,
            "is_stale": is_stale,
            "stale_days": stale_days,
            "suppress_stocking_decisions": suppress,
        }
    except Exception as e:
        logger.error(f"Failed to fetch cached price observations from DB: {e}")
        return None


def fetch_live_commodity_prices(
    db: Optional[Session] = None,
    force_refresh: bool = False,
    max_retries: int = 3,
    backoff_delays: Tuple[float, ...] = (1.0, 2.0, 4.0),
) -> Dict[str, Any]:
    """
    Fetches real-time commodity prices from fcainfoweb.nic.in with exponential backoff.
    Falls back to cached DB observations, file cache, and default backup without wiping history.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Attempt live scrape with exponential backoff
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(FCA_URL, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=8) as response:
                html = response.read().decode("utf-8", errors="ignore")

            parsed = parse_pmd_html(html)
            if parsed.get("commodities"):
                # Save to DB if session provided
                if db is not None:
                    persist_observations_to_db(db, parsed["commodities"], parsed["as_on_date"])

                # Also write to file cache
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(parsed, f, indent=2, ensure_ascii=False)

                logger.info(f"Successfully scraped {len(parsed['commodities'])} commodities from PMD portal.")
                return parsed
        except Exception as e:
            last_err = e
            logger.warning(f"PMD Scraper attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < len(backoff_delays):
                time.sleep(backoff_delays[attempt])

    logger.warning(f"All {max_retries} live scrape attempts failed ({last_err}). Falling back to cached data.")

    # 2. Fallback to Database Cache
    if db is not None:
        db_cache = fetch_from_db_cache(db)
        if db_cache and db_cache.get("commodities"):
            logger.info("Using DB cache for commodity prices.")
            return db_cache

    # 3. Fallback to File Cache
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                cached["status"] = "cached_file"
                # Determine staleness
                try:
                    as_on = datetime.strptime(cached.get("as_on_date", ""), "%d/%m/%Y").date()
                    stale_days = (date.today() - as_on).days
                except Exception:
                    stale_days = 2
                cached["is_stale"] = stale_days >= 1
                cached["stale_days"] = max(0, stale_days)
                cached["suppress_stocking_decisions"] = stale_days > 7
                return cached
        except Exception:
            pass

    # 4. Built-in emergency fallback dataset
    default_items = [
        {"commodity": "Rice", "price_inr_per_kg": 46.11, "category": "Grains & Pulses", "unit": "₹ / Kg"},
        {"commodity": "Wheat", "price_inr_per_kg": 31.87, "category": "Grains & Pulses", "unit": "₹ / Kg"},
        {"commodity": "Atta (Wheat)", "price_inr_per_kg": 37.52, "category": "Grains & Pulses", "unit": "₹ / Kg"},
        {"commodity": "Gram Dal", "price_inr_per_kg": 88.23, "category": "Grains & Pulses", "unit": "₹ / Kg"},
        {"commodity": "Tur/Arhar Dal", "price_inr_per_kg": 124.43, "category": "Grains & Pulses", "unit": "₹ / Kg"},
        {"commodity": "Urad Dal", "price_inr_per_kg": 122.63, "category": "Grains & Pulses", "unit": "₹ / Kg"},
        {"commodity": "Moong Dal", "price_inr_per_kg": 112.03, "category": "Grains & Pulses", "unit": "₹ / Kg"},
        {"commodity": "Mustard Oil (Packed)", "price_inr_per_kg": 201.42, "category": "Edible Oils", "unit": "₹ / Kg"},
        {"commodity": "Groundnut Oil (Packed)", "price_inr_per_kg": 206.84, "category": "Edible Oils", "unit": "₹ / Kg"},
        {"commodity": "Sunflower Oil (Packed)", "price_inr_per_kg": 193.56, "category": "Edible Oils", "unit": "₹ / Kg"},
        {"commodity": "Potato", "price_inr_per_kg": 23.12, "category": "Vegetables", "unit": "₹ / Kg"},
        {"commodity": "Onion", "price_inr_per_kg": 54.22, "category": "Vegetables", "unit": "₹ / Kg"},
        {"commodity": "Tomato", "price_inr_per_kg": 39.04, "category": "Vegetables", "unit": "₹ / Kg"},
        {"commodity": "Sugar", "price_inr_per_kg": 58.24, "category": "Daily Essentials", "unit": "₹ / Kg"},
        {"commodity": "Milk @", "price_inr_per_kg": 61.40, "category": "Daily Essentials", "unit": "₹ / Kg"},
        {"commodity": "Tea Loose", "price_inr_per_kg": 274.08, "category": "Daily Essentials", "unit": "₹ / Kg"},
        {"commodity": "Salt Pack (Iodised)", "price_inr_per_kg": 22.09, "category": "Daily Essentials", "unit": "₹ / Kg"},
    ]

    emergency_date = datetime.now().strftime("%d/%m/%Y")
    fallback = {
        "status": "emergency_fallback",
        "as_on_date": emergency_date,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_commodities": len(default_items),
        "source_url": FCA_URL,
        "commodities": default_items,
        "is_stale": True,
        "stale_days": 1,
        "suppress_stocking_decisions": False,
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(fallback, f, indent=2, ensure_ascii=False)

    return fallback
