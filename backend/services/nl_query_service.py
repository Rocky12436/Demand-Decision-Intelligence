"""
Guarded Natural Language Query Layer (Prompt 5.5)
Project: Demand-Decision-Intelligence

Enforces safety: DO NOT let an LLM write free SQL against the database.
1. Whitelist of parameterized query templates.
2. User intent parsed into strict JSON Pydantic schema.
3. Server-side bound parameters with caller's dataset_id scope applied.
4. Result rows phrased into natural language prose.
5. Verifiable underlying tabular/chart data displayed alongside prose.
6. Rate-limiting, audit logging, and safe fallback.
"""

import re
import unicodedata
import time
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_

from backend.models.demand import DailyProductDemand
from backend.models.product import Product
from backend.models.inventory import InventoryRecommendation, InventoryState
from backend.models.procurement import SupplierProduct, PurchaseOrder, PurchaseOrderLine, Supplier
from backend.models.market_price import CommodityMapping, PriceObservation
from backend.models.dead_stock import DeadStockRecord
from backend.models.calendar import CalendarEvent
from backend.models.forecast import ForecastRun, ForecastEvaluation
from backend.models.chat import ChatSession, ChatMessage
from backend.services.dataset_service import resolve_dataset


WHITELISTED_TEMPLATES = [
    "stockout_risk_before",
    "top_n_by",
    "demand_for",
    "compare_periods",
    "items_below_rop",
    "price_movers",
    "dead_stock",
    "forecast_accuracy_for",
    "executive_kpi_summary",
    "supplier_po_summary",
    "upcoming_festivals",
    "model_benchmarks",
    "inventory_health_overview",
    "bot_help_and_overview",
]


class ParsedQueryIntent(BaseModel):
    template_name: str = Field(..., description="Must match one of the whitelisted templates")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


def detect_query_language(query_text: str) -> str:
    """
    Detects if the user's query is in Hindi/Hinglish or English.
    Returns 'hi' for Hindi/Hinglish, 'en' for English.
    """
    q = query_text.strip()
    # Check for Devanagari script characters
    devanagari_count = sum(1 for ch in q if '\u0900' <= ch <= '\u097F')
    if devanagari_count >= 2:
        return 'hi'
    # Check for common Hindi/Hinglish words
    q_lower = q.lower()
    
    # Strong single-word Hindi indicators that immediately signify Hindi/Hinglish
    strong_markers = [
        'namaste', 'kaise', 'batao', 'bataiye', 'bata', 'chahiye', 'khatam', 'khatm',
        'fasa', 'bikri', 'saman', 'dukaan', 'paisa', 'munafa', 'fayda', 'faida',
        'karein', 'kare', 'karo', 'hoga', 'hogi', 'hona', 'kisko', 'kaunsa',
        'kitna', 'kitni', 'kitne', 'sabse', 'zyada', 'jyada', 'suniye', 'sunao',
        'mangwana', 'kharidna', 'bechna', 'sasta', 'mehenga', 'chhoot', 'bhav'
    ]
    if any(re.search(r'\b' + re.escape(w) + r'\b', q_lower) for w in strong_markers):
        return 'hi'

    hindi_markers = [
        'kya', 'kaise', 'kisko', 'kitna', 'kitni', 'kitne', 'kaunsa', 'kaun',
        'mujhe', 'batao', 'dikhao', 'bata', 'dikha', 'hai', 'hain', 'nahi',
        'sabse', 'jyada', 'zyada', 'kam', 'wala', 'wale', 'wali',
        'dukaan', 'saman', 'paisa', 'bikri', 'order', 'karo', 'kare',
        'mangwana', 'kharidna', 'bechna', 'stock', 'maal', 'cheez',
        'aaj', 'kal', 'abhi', 'pehle', 'baad', 'mahina', 'hafta',
        'reorder', 'khatam', 'fasa', 'bhejo', 'sunao', 'suniye',
        'accha', 'theek', 'sahi', 'galat', 'zaroor', 'zaroori',
        'chahiye', 'karein', 'hoga', 'hogi', 'hona', 'kuch', 'meri',
        'mera', 'apna', 'apne', 'bhi', 'ab', 'se', 'me', 'mein',
        'par', 'ko', 'ki', 'ka', 'ke', 'aur', 'toh', 'taaki', 'namaste'
    ]
    matches = sum(1 for word in hindi_markers if re.search(r'\b' + re.escape(word) + r'\b', q_lower))
    if matches >= 1:
        return 'hi'
    return 'en'


def make_hinglish_prose(template_name: str, data: dict) -> str:
    """
    Generates a simple Hinglish prose response for non-technical users.
    data dict contains template-specific values needed for the prose.
    """
    tpl = template_name

    if tpl == "stockout_risk_before":
        count = data.get('count', 0)
        target_date = data.get('target_date', '')
        days_ahead = data.get('days_ahead', 30)
        top_skus = data.get('top_skus', '')
        if count > 0:
            return (
                f"⚠️ Alert: {count} items ka stock {target_date} se pehle khatam ho jayega ({days_ahead} din baaki hain). "
                f"Sabse zyada urgent items hain: {top_skus}. "
                f"Inke liye abhi order dena zaroori hai, nahi toh bikri ruk jayegi."
            )
        return f"✅ Acchi baat hai! Sabhi items ka stock {target_date} tak sufficient hai. Koi chinta nahi."

    elif tpl == "dead_stock":
        total_capital = data.get('total_capital', 0)
        count = data.get('count', 0)
        days = data.get('days_threshold', 90)
        monthly = data.get('monthly_storage', 0)
        return (
            f"📦 Aapke paas {count} items hain jo {days}+ din se nahi bike. "
            f"In mein ₹{total_capital:,.0f} ka paisa fasa hua hai. "
            f"Har mahine ₹{monthly:,.0f} ka storage kharcha bhi lag raha hai. "
            f"Inhe discount pe bechna ya supplier ko return karna best rahega."
        )

    elif tpl == "items_below_rop":
        count = data.get('count', 0)
        if count > 0:
            return (
                f"🔴 Abhi {count} items ka stock Reorder Level se neeche hai. "
                f"Matlab ye items jaldi khatam ho sakte hain. "
                f"Inke liye turant naya order supplier ko bhejein."
            )
        return "✅ Badhiya! Abhi kisi bhi item ka stock Reorder Level se neeche nahi hai. Sab theek chal raha hai."

    elif tpl == "top_n_by":
        n = data.get('n', 10)
        metric = data.get('metric', 'demand')
        top_sku = data.get('top_sku', 'N/A')
        top_value = data.get('top_value', 0)
        metric_hindi = 'bikri' if metric == 'demand' else ('kamai' if metric == 'revenue' else metric)
        return (
            f"📊 Ye hain aapke top {n} sabse zyada {metric_hindi} wale products. "
            f"#1 pe hai {top_sku} jiske {top_value:,.0f} units bike. "
            f"In products ka stock hamesha ready rakhein."
        )

    elif tpl == "price_movers":
        count = data.get('count', 0)
        thresh = data.get('threshold', 5)
        return (
            f"📈 {count} items ke daam {thresh}%+ badh rahe hain. "
            f"Agar zaroorat ho toh abhi advance mein khareed lo, baad mein aur mehenga hoga. "
            f"Neeche table mein details hain."
        )

    elif tpl == "demand_for":
        sku = data.get('sku', '')
        total_qty = data.get('total_qty', 0)
        avg_qty = data.get('avg_qty', 0)
        days = data.get('days', 0)
        return (
            f"📋 SKU {sku} ki pichle {days} din ki bikri: Total {total_qty:,.0f} units "
            f"(roz average {avg_qty:.1f} units). "
            f"Is hisaab se stock plan karein."
        )

    elif tpl == "forecast_accuracy_for":
        sku = data.get('sku', '')
        best_model = data.get('best_model', 'N/A')
        wape = data.get('wape', None)
        wape_str = f" (accuracy: {100 - wape:.1f}%)" if wape else ""
        return (
            f"🎯 SKU {sku} ke liye sabse accha prediction model hai: {best_model}{wape_str}. "
            f"Is model ki prediction ke hisaab se stock rakhein toh nuksan kam hoga."
        )

    elif tpl == "bot_help_and_overview":
        return (
            "👋 Namaste! Main aapka **DemandIQ Copilot** hoon.\n\n"
            "Aap mujhse apni dukaan ke baare mein kuch bhi puch sakte hain:\n"
            "• **Stock khatam hoga kya?** — 'Kaunsa saman Diwali se pehle khatam hoga?'\n"
            "• **Reorder karna hai** — 'Kisko reorder karna chahiye?'\n"
            "• **Dead stock** — 'Kitna paisa fasa hua hai jo nahi bik raha?'\n"
            "• **Top bikri** — 'Sabse zyada kya bik raha hai?'\n"
            "• **Daam badh rahe** — 'Kaunse saman ke daam badh rahe hain?'\n"
            "• **Overall status** — 'Meri dukaan kaise chal rahi hai?'"
        )

    elif tpl == "executive_kpi_summary":
        total = data.get('total_products', 0)
        rop = data.get('rop_breaches', 0)
        dead = data.get('dead_stock_capital', 0)
        pos = data.get('active_pos', 0)
        po_spend = data.get('po_spend', 0)
        return (
            f"📊 **Aapki Dukaan ki Summary:**\n"
            f"• **Total Products:** {total} items track ho rahe hain\n"
            f"• **Stock Kam Hai:** {rop} items mein stock bahut kam hai, turant order karna chahiye\n"
            f"• **Paisa Fasa Hai:** ₹{float(dead):,.0f} ka maal pada hai jo bik nahi raha\n"
            f"• **Orders Chalte Hain:** {pos} orders abhi suppliers ke paas hain (₹{float(po_spend):,.0f})\n\n"
            f"💡 Sabse pehle kam stock wale items ka order bhejein aur dead stock pe discount lagaein."
        )

    elif tpl == "supplier_po_summary":
        count = data.get('count', 0)
        total_spend = data.get('total_spend', 0)
        return (
            f"📋 Aapke {count} recent Purchase Orders hain, total ₹{total_spend:,.0f} ka. "
            f"Neeche table mein har order ki detail hai - status, delivery date, aur amount."
        )

    elif tpl == "upcoming_festivals":
        count = data.get('count', 0)
        return (
            f"🎉 Aane wale {count} festivals/holidays ki list neeche hai. "
            f"In tyohaaron se pehle stock badha lo taaki bikri miss na ho. "
            f"Suppliers ko advance mein order bhejo."
        )

    elif tpl == "model_benchmarks":
        count = data.get('count', 0)
        return (
            f"🤖 {count} AI prediction models ki performance neeche hai. "
            f"Sabse acche models ko system automatically use karta hai stock planning ke liye."
        )

    elif tpl == "inventory_health_overview":
        count = data.get('count', 0)
        return (
            f"📦 {count} items ki stock health neeche di gayi hai. "
            f"Jinpe 'CRITICAL' ya 'WARNING' likha hai unka turant order dein. "
            f"Baaki items ka stock abhi safe hai."
        )

    # Fallback
    return "Query ka jawab mil gaya hai. Neeche table mein details dekhein."


def parse_natural_language_intent(query_text: str) -> Optional[ParsedQueryIntent]:
    """
    Parses a user question into a validated query template intent.
    Uses pattern matching and semantic classification to prevent free-form SQL injection.
    """
    q = query_text.lower().strip()

    # 4. Items below ROP / Reorder (Checked early to catch speech transcripts like 'किसकी रिकॉर्डर काम है')
    # e.g., "Which items are below ROP?", "What should I reorder now?", "किसकी रिकॉर्डर काम है", "kisko reorder kare"
    if any(k in q for k in [
        "below rop", "reorder", "under reorder point", "re-order", "rop",
        "रिकॉर्डर", "रिकार्डर", "रीऑर्डर", "रिऑर्डर", "कम है", "काम है",
        "kisko reorder", "kiska reorder", "reorder level", "kya order",
        "kya mangwana", "kya kharidna", "kisko mangwana", "order list",
        "stock kam", "स्टॉक कम", "maal kam", "kam stock", "order karna hai",
        "order kiska", "order kisko", "reorder karna", "reorder point"
    ]):
        return ParsedQueryIntent(
            template_name="items_below_rop",
            parameters={},
            confidence=0.92
        )

    # 1. Stockout risk before date / festival
    # e.g., "Which SKUs will stock out before Diwali?", "What items will run out before 2024-11-01?", "kaunsa saman khatam hoga"
    if any(k in q for k in ["stock out", "stockout", "run out", "khatam", "khatm", "खत्म", "आउट ऑफ स्टॉक"]) or (
        any(k in q for k in ["diwali", "eid", "दिवाली", "त्योहार", "festival"]) and any(k in q for k in ["out", "risk", "khatam", "खत्म", "stock", "स्टॉक"])
    ):
        target = "diwali"
        if any(k in q for k in ["diwali", "दिवाली"]):
            target = "2024-11-01"
        elif any(k in q for k in ["eid", "ईद"]):
            target = "2024-04-11"
        else:
            # Look for YYYY-MM-DD
            m = re.search(r'\d{4}-\d{2}-\d{2}', q)
            target = m.group(0) if m else (date.today() + timedelta(days=30)).isoformat()

        return ParsedQueryIntent(
            template_name="stockout_risk_before",
            parameters={"target_date": target},
            confidence=0.95
        )

    # 2. Dead stock / capital locked up
    # e.g., "What's my total capital tied up in dead stock?", "Show dead stock", "kitna paisa fasa hai"
    if any(k in q for k in ["dead stock", "deadstock", "slow moving", "capital tied up", "obsolete", "fasa", "paisa fasa", "फंसा", "पैसा"]):
        days = 90
        m = re.search(r'(\d+)\s*days?', q)
        if m:
            days = int(m.group(1))
        return ParsedQueryIntent(
            template_name="dead_stock",
            parameters={"days_threshold": days},
            confidence=0.95
        )

    # 3. Top N by metric
    # e.g., "Show me the top 10 SKUs by forecast error last month", "Top 5 products by demand", "sabse jyada bikne wale"
    if any(k in q for k in ["top", "sabse jyada", "sabse zyada", "सबसे ज्यादा", "सबसे अधिक", "best selling", "bikri"]):
        n = 10
        m_n = re.search(r'(?:top|सबसे ज्यादा)\s*(\d+)', q)
        if m_n:
            n = int(m_n.group(1))

        metric = "demand"
        if any(k in q for k in ["error", "wape", "inaccurate"]):
            metric = "forecast_error"
        elif any(k in q for k in ["sales", "volume", "quantity", "bikri", "बिक्री"]):
            metric = "demand"
        elif any(k in q for k in ["revenue", "value", "cost", "kamai", "कमाई"]):
            metric = "revenue"
        elif any(k in q for k in ["stockout", "risk"]):
            metric = "stockout_risk"

        return ParsedQueryIntent(
            template_name="top_n_by",
            parameters={"metric": metric, "n": n},
            confidence=0.92
        )

    # 5. Price movers / rising commodity prices / forward buy
    # e.g., "Which products should I buy now given prices are rising?", "Price movers"
    if any(k in q for k in ["prices are rising", "price rising", "price mover", "forward buy", "price surge", "commodities", "kimat", "keemat", "दाम बढ़ रहे"]):
        return ParsedQueryIntent(
            template_name="price_movers",
            parameters={"direction": "rising", "threshold_pct": 5.0},
            confidence=0.90
        )

    # 6. Demand for SKU
    # e.g., "What is the demand for SKU 19512?", "Demand for product 391306"
    m_sku = re.search(r'(?:sku|product|item)\s*(?:#|id)?\s*([a-zA-Z0-9_-]+)', q)
    if m_sku and any(k in q for k in ["demand", "sales", "forecast"]):
        sku_id = m_sku.group(1)
        return ParsedQueryIntent(
            template_name="demand_for",
            parameters={"product_id": sku_id, "horizon_days": 14},
            confidence=0.88
        )

    # 7. Forecast accuracy for SKU
    if m_sku and any(k in q for k in ["accuracy", "wape", "mape", "error"]):
        sku_id = m_sku.group(1)
        return ParsedQueryIntent(
            template_name="forecast_accuracy_for",
            parameters={"product_id": sku_id},
            confidence=0.88
        )

    # 8. Greetings & Copilot Capabilities
    # e.g., "hi", "hello", "hey", "help", "who are you", "what can you do", "capabilities"
    if any(q.startswith(k) for k in ["hi", "hello", "hey", "help"]) or any(k in q for k in ["who are you", "what can you do", "capabilities", "guide me", "how to use"]):
        return ParsedQueryIntent(
            template_name="bot_help_and_overview",
            parameters={},
            confidence=0.98
        )

    # 9. Executive KPI / Supply Chain Overview
    # e.g., "how is my supply chain?", "business overview", "kpi summary", "general status", "dashboard summary", "overall health"
    if any(k in q for k in ["supply chain", "overview", "kpi", "business health", "general status", "summary", "portfolio health", "status overview"]):
        return ParsedQueryIntent(
            template_name="executive_kpi_summary",
            parameters={},
            confidence=0.92
        )

    # 10. Purchase Orders & Suppliers
    # e.g., "who are my suppliers?", "show purchase orders", "po status", "procurement", "open orders"
    if any(k in q for k in ["purchase order", "po status", "procurement", "supplier", "vendor", "open pos", "open order"]):
        return ParsedQueryIntent(
            template_name="supplier_po_summary",
            parameters={},
            confidence=0.91
        )

    # 11. Upcoming Festivals & Calendar Events
    # e.g., "what upcoming festivals?", "festivals", "holidays", "calendar events", "upcoming events"
    if any(k in q for k in ["festival", "holiday", "calendar event", "upcoming event", "surge window"]):
        return ParsedQueryIntent(
            template_name="upcoming_festivals",
            parameters={},
            confidence=0.90
        )

    # 12. Model Performance & Benchmarks
    # e.g., "which model is best?", "model performance", "accuracy comparison", "models", "benchmark"
    if any(k in q for k in ["which model", "best model", "model performance", "accuracy comparison", "benchmark", "champion model"]):
        return ParsedQueryIntent(
            template_name="model_benchmarks",
            parameters={},
            confidence=0.90
        )

    # 13. Inventory Health & Stock Levels
    # e.g., "inventory status", "stock level", "inventory health", "how much stock", "stock on hand"
    if any(k in q for k in ["inventory status", "stock level", "inventory health", "stock on hand", "safety stock balance"]):
        return ParsedQueryIntent(
            template_name="inventory_health_overview",
            parameters={},
            confidence=0.89
        )

    # Reject unmapped queries
    return None


def execute_guarded_template(
    db: Session,
    intent: ParsedQueryIntent,
    dataset_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Executes a whitelisted query template with strict server-side dataset scoping.
    """
    t_start = time.perf_counter()
    target_dataset = resolve_dataset(db, None, dataset_id)
    tpl = intent.template_name
    params = intent.parameters

    if tpl not in WHITELISTED_TEMPLATES:
        raise ValueError(f"Template '{tpl}' is not permitted.")

    # 1. Template: stockout_risk_before
    if tpl == "stockout_risk_before":
        target_date_str = params.get("target_date", (date.today() + timedelta(days=30)).isoformat())
        try:
            target_date = date.fromisoformat(target_date_str)
        except Exception:
            target_date = date.today() + timedelta(days=30)

        days_ahead = max(1, (target_date - date.today()).days)

        # Find items where current_stock < avg_daily_demand * days_ahead
        recs = db.query(InventoryRecommendation).filter(
            InventoryRecommendation.dataset_id == target_dataset.id,
            InventoryRecommendation.avg_daily_demand > 0,
        ).all()

        at_risk = []
        for r in recs:
            days_of_supply = round(r.current_stock / r.avg_daily_demand, 1)
            if days_of_supply < days_ahead:
                at_risk.append({
                    "product_id": r.product_id,
                    "current_stock": r.current_stock,
                    "avg_daily_demand": r.avg_daily_demand,
                    "days_of_supply": days_of_supply,
                    "stockout_projected_date": (date.today() + timedelta(days=int(days_of_supply))).isoformat(),
                    "recommended_reorder": r.recommended_order_qty or round(r.reorder_point - r.current_stock, 1),
                })

        at_risk.sort(key=lambda x: x["days_of_supply"])
        table_rows = at_risk[:15]

        # Generate prose
        count = len(at_risk)
        if count > 0:
            top_skus = ", ".join([f"SKU {it['product_id']} ({it['days_of_supply']} days)" for it in table_rows[:3]])
            prose = (
                f"We identified {count} SKUs projected to stock out before {target_date.isoformat()} ({days_ahead} days away). "
                f"The highest urgency items are {top_skus}. "
                f"Immediate purchase orders are recommended to replenish safety buffers."
            )
        else:
            prose = f"All active SKUs have sufficient stock to cover demand through {target_date.isoformat()}."
            top_skus = ""

        # Store Hinglish data for language-aware response
        _hinglish_data = {'count': count, 'target_date': target_date.isoformat(), 'days_ahead': days_ahead, 'top_skus': top_skus}

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, _hinglish_data),
            "table": {
                "columns": ["product_id", "current_stock", "avg_daily_demand", "days_of_supply", "stockout_projected_date", "recommended_reorder"],
                "rows": table_rows,
                "total_count": count,
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 2. Template: dead_stock
    elif tpl == "dead_stock":
        days_thresh = int(params.get("days_threshold", 90))
        ds_records = db.query(DeadStockRecord).filter(
            DeadStockRecord.dataset_id == target_dataset.id,
            DeadStockRecord.status == "ACTIVE",
            DeadStockRecord.days_without_sales >= days_thresh,
        ).order_by(desc(DeadStockRecord.capital_tied_up)).all()

        total_capital = round(sum(float(r.capital_tied_up or 0.0) for r in ds_records), 2)
        total_monthly_storage = round(sum(float(r.monthly_holding_cost or 0.0) for r in ds_records), 2)

        table_rows = [
            {
                "product_id": r.product_id,
                "on_hand": r.on_hand_quantity,
                "capital_tied_up": r.capital_tied_up,
                "monthly_holding_cost": r.monthly_holding_cost,
                "days_without_sales": r.days_without_sales,
                "recommended_action": r.recommended_action,
                "optimal_discount_pct": f"{int(r.optimal_discount_pct * 100)}%" if r.optimal_discount_pct else "—",
            }
            for r in ds_records[:15]
        ]

        prose = (
            f"Your total working capital tied up in dead stock (>= {days_thresh} days inactive) is "
            f"${total_capital:,.2f} across {len(ds_records)} SKUs. "
            f"This inventory incurs an ongoing storage drag of ${total_monthly_storage:,.2f}/month. "
            f"Clearance markdowns and supplier returns are prioritized in the table below."
        )

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'total_capital': total_capital, 'count': len(ds_records), 'days_threshold': days_thresh, 'monthly_storage': total_monthly_storage}),
            "table": {
                "columns": ["product_id", "on_hand", "capital_tied_up", "monthly_holding_cost", "days_without_sales", "recommended_action", "optimal_discount_pct"],
                "rows": table_rows,
                "total_count": len(ds_records),
                "summary": {"total_capital_tied_up": total_capital, "monthly_storage_drag": total_monthly_storage},
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 3. Template: items_below_rop
    elif tpl == "items_below_rop":
        recs = db.query(InventoryRecommendation).filter(
            InventoryRecommendation.dataset_id == target_dataset.id,
            InventoryRecommendation.current_stock <= InventoryRecommendation.reorder_point,
        ).order_by(InventoryRecommendation.priority.desc()).all()

        table_rows = [
            {
                "product_id": r.product_id,
                "current_stock": r.current_stock,
                "reorder_point": r.reorder_point,
                "safety_stock": r.safety_stock,
                "recommended_order_qty": r.recommended_order_qty,
                "priority": r.priority,
                "risk_status": r.risk_status,
            }
            for r in recs[:20]
        ]

        prose = (
            f"There are currently {len(recs)} SKUs operating below their Reorder Point (ROP) in this dataset. "
            f"These items require urgent procurement orders to prevent stockouts during supplier lead times."
        )

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'count': len(recs)}),
            "table": {
                "columns": ["product_id", "current_stock", "reorder_point", "safety_stock", "recommended_order_qty", "priority", "risk_status"],
                "rows": table_rows,
                "total_count": len(recs),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 4. Template: top_n_by
    elif tpl == "top_n_by":
        n = min(50, int(params.get("n", 10)))
        metric = params.get("metric", "demand")

        agg_q = db.query(
            DailyProductDemand.product_id,
            func.sum(DailyProductDemand.total_quantity).label("total_demand"),
            func.avg(DailyProductDemand.total_quantity).label("avg_demand"),
            func.sum(DailyProductDemand.total_sales_value).label("total_revenue"),
        ).filter(DailyProductDemand.dataset_id == target_dataset.id).group_by(DailyProductDemand.product_id)

        if metric == "revenue":
            agg_q = agg_q.order_by(desc("total_revenue"))
        else:
            agg_q = agg_q.order_by(desc("total_demand"))

        rows = agg_q.limit(n).all()
        table_rows = [
            {
                "rank": idx + 1,
                "product_id": r.product_id,
                "total_demand": round(float(r.total_demand or 0), 1),
                "avg_daily_demand": round(float(r.avg_demand or 0), 2),
                "total_revenue": round(float(r.total_revenue or 0), 2),
            }
            for idx, r in enumerate(rows)
        ]

        prose = (
            f"Here are the top {len(rows)} products ranked by {metric}. "
            f"The #1 SKU is {table_rows[0]['product_id'] if table_rows else 'N/A'} "
            f"with {table_rows[0]['total_demand'] if table_rows else 0} units sold."
        )

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'n': len(rows), 'metric': metric, 'top_sku': table_rows[0]['product_id'] if table_rows else 'N/A', 'top_value': table_rows[0]['total_demand'] if table_rows else 0}),
            "table": {
                "columns": ["rank", "product_id", "total_demand", "avg_daily_demand", "total_revenue"],
                "rows": table_rows,
                "total_count": len(rows),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 5. Template: price_movers
    elif tpl == "price_movers":
        thresh = float(params.get("threshold_pct", 5.0))
        # Fetch price observations with notable deltas
        obs = db.query(PriceObservation).filter(
            PriceObservation.price_change_pct >= thresh
        ).order_by(desc(PriceObservation.price_change_pct)).limit(15).all()

        table_rows = [
            {
                "commodity": o.commodity_name,
                "market": o.market_name,
                "price": o.price_rs_per_kg,
                "price_change_pct": f"+{o.price_change_pct:.1f}%",
                "trend": o.trend_direction,
                "action": "Forward Buy Recommended" if o.price_change_pct >= 10.0 else "Monitor",
            }
            for o in obs
        ]

        prose = (
            f"We detected {len(table_rows)} commodity products with significant price surges (>= {thresh}%). "
            f"Forward-buying or early procurement before further inflation is advised for these items."
        )

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'count': len(table_rows), 'threshold': thresh}),
            "table": {
                "columns": ["commodity", "market", "price", "price_change_pct", "trend", "action"],
                "rows": table_rows,
                "total_count": len(table_rows),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 6. Template: demand_for
    elif tpl == "demand_for":
        sku_id = str(params.get("product_id", ""))
        demands = db.query(DailyProductDemand).filter(
            DailyProductDemand.dataset_id == target_dataset.id,
            DailyProductDemand.product_id == sku_id,
        ).order_by(desc(DailyProductDemand.date)).limit(30).all()

        total_qty = sum(float(d.total_quantity or 0) for d in demands)
        total_amt = sum(float(d.total_amount or 0) for d in demands)
        avg_qty = round(total_qty / max(1, len(demands)), 2)

        table_rows = [
            {
                "product_id": sku_id,
                "date": d.date.isoformat() if hasattr(d.date, "isoformat") else str(d.date),
                "units_sold": d.total_quantity,
                "revenue": f"${float(d.total_amount or 0):,.2f}",
                "city_name": getattr(d, "city_name", "ALL") or "ALL",
            }
            for d in demands[:15]
        ]

        if demands:
            prose = (
                f"Historical demand for SKU {sku_id}: Over the last {len(demands)} recorded days, "
                f"total demand reached {total_qty:,.0f} units (averaging {avg_qty} units/day) "
                f"generating ${total_amt:,.2f} in revenue."
            )
        else:
            prose = f"No historical sales data found for SKU '{sku_id}' in dataset '{target_dataset.name}'."

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'sku': sku_id, 'total_qty': total_qty, 'avg_qty': avg_qty, 'days': len(demands)}),
            "table": {
                "columns": ["product_id", "date", "units_sold", "revenue", "city_name"],
                "rows": table_rows,
                "total_count": len(demands),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 7. Template: forecast_accuracy_for
    elif tpl == "forecast_accuracy_for":
        sku_id = str(params.get("product_id", ""))
        evals = db.query(ForecastEvaluation).filter(
            ForecastEvaluation.dataset_id == target_dataset.id,
            ForecastEvaluation.product_id == sku_id,
        ).all()

        table_rows = [
            {
                "model_name": e.model_name,
                "wape": f"{e.wape:.2f}%" if e.wape is not None else "—",
                "mape": f"{e.mape:.2f}%" if e.mape is not None else "—",
                "rmse": f"{e.rmse:.2f}" if e.rmse is not None else "—",
                "mae": f"{e.mae:.2f}" if e.mae is not None else "—",
                "evaluated_at": e.evaluation_date.strftime("%Y-%m-%d") if e.evaluation_date else "Recent",
            }
            for e in evals
        ]

        best_model_name = 'N/A'
        best_wape = None
        if table_rows:
            best_model = min(evals, key=lambda x: x.wape if x.wape is not None else 999.0)
            best_model_name = best_model.model_name
            best_wape = best_model.wape
            prose = (
                f"Forecast accuracy for SKU {sku_id}: Evaluated across {len(evals)} benchmarked models. "
                f"Top performing model is {best_model.model_name} with WAPE of "
                f"{best_model.wape:.2f}%." if best_model.wape is not None else f"Top model is {best_model.model_name}."
            )
        else:
            prose = f"No model evaluations found for SKU '{sku_id}'. Generating fresh forecasts will compute backtesting metrics."

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'sku': sku_id, 'best_model': best_model_name, 'wape': best_wape}),
            "table": {
                "columns": ["model_name", "wape", "mape", "rmse", "mae", "evaluated_at"],
                "rows": table_rows,
                "total_count": len(table_rows),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 8. Template: bot_help_and_overview
    elif tpl == "bot_help_and_overview":
        prose = (
            "👋 Hello! I am your **DemandIQ Decision Intelligence Copilot**.\n\n"
            "I operate directly over your live PostgreSQL and DuckDB inventory records with zero SQL injection risk. "
            "You can ask me questions about:\n"
            "• **Stockouts & ROP**: Which items are below reorder buffer or projected to stock out?\n"
            "• **Dead Stock**: How much capital is tied up in inactive inventory?\n"
            "• **Top Demand SKUs**: Which products drive the highest revenue or sales volume?\n"
            "• **Price Fluctuations**: Which commodities are experiencing price surges?\n"
            "• **Procurement & POs**: Status of pending purchase orders and vendor spend.\n"
            "• **Holiday Surge**: Impact of upcoming festivals like Diwali or Eid."
        )
        capabilities = [
            {"category": "Stockout Risk", "sample_prompt": "Which SKUs will stock out before Diwali?", "description": "Checks projected stockouts vs safety buffers"},
            {"category": "Working Capital", "sample_prompt": "What's my total capital tied up in dead stock?", "description": "Quantifies obsolete inventory and holding drag"},
            {"category": "Replenishment", "sample_prompt": "Which items are currently below ROP?", "description": "Lists SKUs requiring immediate purchase orders"},
            {"category": "Top Performers", "sample_prompt": "Show me the top 10 SKUs by sales volume", "description": "Ranks products by total units sold and revenue"},
            {"category": "Market Prices", "sample_prompt": "Which products should I buy now given prices are rising?", "description": "Identifies commodity forward-buy opportunities"},
            {"category": "Portfolio Health", "sample_prompt": "How is my supply chain?", "description": "Executive scorecard of overall inventory risk and spend"},
        ]
        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {}),
            "table": {
                "columns": ["category", "sample_prompt", "description"],
                "rows": capabilities,
                "total_count": len(capabilities),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 9. Template: executive_kpi_summary
    elif tpl == "executive_kpi_summary":
        total_products = db.query(Product).count()
        rop_breaches = db.query(InventoryRecommendation).filter(
            InventoryRecommendation.dataset_id == target_dataset.id,
            InventoryRecommendation.current_stock <= InventoryRecommendation.reorder_point,
        ).count()
        dead_stock_capital = db.query(func.sum(DeadStockRecord.capital_tied_up)).filter(
            DeadStockRecord.dataset_id == target_dataset.id,
            DeadStockRecord.status == "ACTIVE",
        ).scalar() or 0.0
        po_spend = db.query(func.sum(PurchaseOrder.total_value)).filter(
            PurchaseOrder.dataset_id == target_dataset.id,
        ).scalar() or 0.0
        active_pos = db.query(PurchaseOrder).filter(
            PurchaseOrder.dataset_id == target_dataset.id,
            PurchaseOrder.status.in_(["DRAFT", "PENDING", "APPROVED", "ISSUED"]),
        ).count()

        kpi_rows = [
            {"metric": "Portfolio Catalog Size", "value": f"{total_products} SKUs", "status": "ACTIVE", "impact": "Operational Scope"},
            {"metric": "Stockout Risk (Below ROP)", "value": f"{rop_breaches} SKUs", "status": "URGENT" if rop_breaches > 0 else "HEALTHY", "impact": "Immediate PO Required"},
            {"metric": "Frozen Dead Stock Capital", "value": f"${float(dead_stock_capital):,.2f}", "status": "WARNING" if dead_stock_capital > 0 else "CLEAR", "impact": "Capital Reclamation"},
            {"metric": "Active Purchase Order Spend", "value": f"${float(po_spend):,.2f}", "status": "IN_PROGRESS", "impact": f"{active_pos} Open POs"},
        ]

        prose = (
            f"📊 **Executive Supply Chain Health Summary** for '{target_dataset.name}':\n"
            f"• **Catalog Scope**: {total_products} active SKUs monitored.\n"
            f"• **Immediate Replenishment**: {rop_breaches} SKUs have fallen below their Reorder Point.\n"
            f"• **Working Capital Drag**: ${float(dead_stock_capital):,.2f} tied up in inactive dead stock.\n"
            f"• **Procurement Pipeline**: {active_pos} active purchase orders totaling ${float(po_spend):,.2f}.\n\n"
            f"Recommended Action: Issue purchase orders for below-ROP SKUs and review markdown strategies for dead stock."
        )

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'total_products': total_products, 'rop_breaches': rop_breaches, 'dead_stock_capital': dead_stock_capital, 'active_pos': active_pos, 'po_spend': po_spend}),
            "table": {
                "columns": ["metric", "value", "status", "impact"],
                "rows": kpi_rows,
                "total_count": len(kpi_rows),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 10. Template: supplier_po_summary
    elif tpl == "supplier_po_summary":
        pos = db.query(PurchaseOrder).filter(
            PurchaseOrder.dataset_id == target_dataset.id,
        ).order_by(desc(PurchaseOrder.created_at)).limit(20).all()

        total_spend = sum(float(p.total_value or 0) for p in pos)
        table_rows = [
            {
                "po_number": p.po_number,
                "supplier_id": p.supplier_id,
                "status": p.status,
                "total_value": f"${float(p.total_value or 0):,.2f}",
                "expected_delivery": p.expected_delivery_date.strftime("%Y-%m-%d") if p.expected_delivery_date else "TBD",
                "triggered_by": p.triggered_by or "SYSTEM",
            }
            for p in pos
        ]

        prose = (
            f"Procurement Status: Found {len(pos)} recent purchase orders totaling ${total_spend:,.2f}. "
            f"Open orders are currently tracked across supplier lead-time fulfillment windows."
        )

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'count': len(pos), 'total_spend': total_spend}),
            "table": {
                "columns": ["po_number", "supplier_id", "status", "total_value", "expected_delivery", "triggered_by"],
                "rows": table_rows,
                "total_count": len(pos),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 11. Template: upcoming_festivals
    elif tpl == "upcoming_festivals":
        events = db.query(CalendarEvent).order_by(CalendarEvent.event_date.asc()).limit(15).all()
        table_rows = [
            {
                "event_name": ev.event_name,
                "event_date": ev.event_date.strftime("%Y-%m-%d") if hasattr(ev.event_date, "strftime") else str(ev.event_date),
                "event_type": ev.event_type,
                "surge_window_before_days": ev.impact_window_before,
                "surge_window_after_days": ev.impact_window_after,
                "region": ev.region or "ALL",
            }
            for ev in events
        ]

        prose = (
            f"Calendar Surge Analysis: {len(events)} holiday events and demand surge windows are scheduled in the calendar. "
            f"Supplier lead times should be buffered ahead of these dates to prevent festive stockouts."
        )

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'count': len(events)}),
            "table": {
                "columns": ["event_name", "event_date", "event_type", "surge_window_before_days", "surge_window_after_days", "region"],
                "rows": table_rows,
                "total_count": len(events),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 12. Template: model_benchmarks
    elif tpl == "model_benchmarks":
        evals = db.query(ForecastEvaluation).filter(
            ForecastEvaluation.dataset_id == target_dataset.id,
        ).order_by(ForecastEvaluation.wape.asc()).limit(20).all()

        table_rows = [
            {
                "model_name": e.model_name,
                "product_id": e.product_id,
                "wape": f"{e.wape:.2f}%" if e.wape is not None else "—",
                "rmse": f"{e.rmse:.2f}" if e.rmse is not None else "—",
                "mape": f"{e.mape:.2f}%" if e.mape is not None else "—",
            }
            for e in evals
        ]

        prose = (
            f"Forecasting Model Benchmark: Displaying {len(evals)} top evaluation runs ranked by WAPE accuracy. "
            f"Models with lowest WAPE are automatically promoted to Champion status for inventory replenishment."
        )

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'count': len(evals)}),
            "table": {
                "columns": ["model_name", "product_id", "wape", "rmse", "mape"],
                "rows": table_rows,
                "total_count": len(evals),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # 13. Template: inventory_health_overview
    elif tpl == "inventory_health_overview":
        recs = db.query(InventoryRecommendation).filter(
            InventoryRecommendation.dataset_id == target_dataset.id,
        ).order_by(InventoryRecommendation.current_stock.asc()).limit(20).all()

        table_rows = [
            {
                "product_id": r.product_id,
                "current_stock": r.current_stock,
                "reorder_point": r.reorder_point,
                "safety_stock": r.safety_stock,
                "risk_status": r.risk_status,
                "recommended_order": r.recommended_order_qty or 0,
            }
            for r in recs
        ]

        prose = (
            f"Inventory Health: Monitored {len(recs)} active SKUs against safety stock and lead-time demand buffers. "
            f"Review items flagged with 'CRITICAL' or 'WARNING' for immediate stock replenishment."
        )

        return {
            "template_name": tpl,
            "prose": prose,
            "prose_hi": make_hinglish_prose(tpl, {'count': len(recs)}),
            "table": {
                "columns": ["product_id", "current_stock", "reorder_point", "safety_stock", "risk_status", "recommended_order"],
                "rows": table_rows,
                "total_count": len(recs),
            },
            "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
        }

    # Default fallback
    return {
        "template_name": tpl,
        "prose": "Query executed successfully, but returned no matching data.",
        "table": {"columns": [], "rows": [], "total_count": 0},
        "execution_ms": round((time.perf_counter() - t_start) * 1000, 2),
    }


def generate_smart_database_advisory(
    db: Session,
    query_text: str,
    user_lang: str,
    target_dataset: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Zero-API Database-Grounded Business & Retail Advisory Engine.
    Answers open-ended retail strategy, profit, discount, supplier, stock management,
    and advisory questions using real live figures from the PostgreSQL database
    without any external paid APIs.
    """
    q = query_text.lower().strip()

    # 1. Fetch live metrics from database
    total_products = 0
    critical_count = 0
    dead_capital = 0.0
    dead_count = 0
    top_sku = "N/A"
    top_qty = 0
    top_rev = 0.0
    active_pos_count = 0
    po_spend = 0.0

    if target_dataset:
        try:
            total_products = db.query(func.count(DailyProductDemand.product_id.distinct())).filter(DailyProductDemand.dataset_id == target_dataset.id).scalar() or db.query(Product).count() or 0
        except Exception:
            total_products = 0

        try:
            crit_recs = db.query(InventoryRecommendation).filter(
                InventoryRecommendation.dataset_id == target_dataset.id,
                InventoryRecommendation.current_stock <= InventoryRecommendation.reorder_point,
            ).all()
            critical_count = len(crit_recs)
        except Exception:
            critical_count = 0

        try:
            dead_items = db.query(DeadStockRecord).filter(
                DeadStockRecord.dataset_id == target_dataset.id
            ).all()
            dead_count = len(dead_items)
            dead_capital = sum(float(d.capital_tied_up or 0) for d in dead_items)
        except Exception:
            dead_count = 0
            dead_capital = 0.0

        try:
            top_demands = db.query(
                DailyProductDemand.product_id,
                func.sum(DailyProductDemand.total_quantity).label("qty"),
                func.sum(DailyProductDemand.total_sales_value).label("rev"),
            ).filter(
                DailyProductDemand.dataset_id == target_dataset.id
            ).group_by(DailyProductDemand.product_id).order_by(desc("qty")).first()

            if top_demands:
                top_sku = str(top_demands.product_id)
                top_qty = int(top_demands.qty or 0)
                top_rev = float(top_demands.rev or 0)
        except Exception:
            pass

        try:
            pos = db.query(PurchaseOrder).filter(PurchaseOrder.dataset_id == target_dataset.id).all()
            active_pos_count = len(pos)
            po_spend = sum(float(p.total_value or 0) for p in pos)
        except Exception:
            pass

    # 2. Semantic Theme Matching
    # Theme A: Profit / Margin / Munafa / Kamai / Growth
    if any(k in q for k in ["profit", "munafa", "kamai", "fayda", "faida", "margin", "growth", "bikri badhaye", "sales badhaye", "paisa kaise kamaye"]):
        template_type = "profit_advisory"
        if user_lang == 'hi':
            prose = (
                f"💡 **Dukaan ka Munafa (Profit) badhane ke liye 3 zaroori steps:**\n\n"
                f"1. **Fast Movers pe Focus:** Aapka #1 selling product hai SKU {top_sku} ({top_qty} units sold, ₹{top_rev:,.0f} revenue). Iska stock kabhi khatam mat hone do kyunki yahi sabse zyada munafa deta hai.\n"
                f"2. **Fasa Hua Paisa Nikalo:** Dead stock me ₹{dead_capital:,.0f} fasa hua hai across {dead_count} items. Ispe 25% clearance offer laga kar turant cash nikalo taaki storage kharcha bache.\n"
                f"3. **Stockout Se Bacho:** {critical_count} items reorder point se neeche hain. Inka turant order bhejo taaki customer laut kar na jaye."
            )
        else:
            prose = (
                f"💡 **3 Key Actions to Maximize Retail Profits:**\n\n"
                f"1. **Protect Fast Movers:** SKU {top_sku} is your top revenue driver ({top_qty} units sold, ₹{top_rev:,.0f} sales). Never allow stockouts on this line.\n"
                f"2. **Liquidate Trapped Capital:** You have ₹{dead_capital:,.0f} locked in {dead_count} slow-moving SKUs. Run a targeted discount to release working capital.\n"
                f"3. **Prevent Stockout Losses:** {critical_count} items breached safe thresholds. Order immediate replenishments to protect customer fill-rate."
            )
        table_rows = [
            {"metric": "Top Revenue SKU", "value": f"SKU {top_sku} (₹{top_rev:,.0f})", "status": "Core Driver"},
            {"metric": "Trapped Dead Capital", "value": f"₹{dead_capital:,.0f} ({dead_count} SKUs)", "status": "Needs Clearance"},
            {"metric": "Low Stock SKUs", "value": f"{critical_count} items", "status": "Urgent Replenish"},
        ]
        suggested = ["Sabse zyada kya bik raha hai?", "Kisko reorder karna chahiye?", "Kitna dead stock fasa hai?"]

    # Theme B: Discount / Offer / Clearance / Sasta
    elif any(k in q for k in ["discount", "offer", "chhoot", "clearance", "sasta", "sale", "kitna discount", "discount kitna"]):
        template_type = "discount_strategy"
        if user_lang == 'hi':
            prose = (
                f"🏷️ **Store Discount Strategy (Munafa bachane ke hisaab se):**\n\n"
                f"• **Top Selling Items (jaise SKU {top_sku}):** Inpe 0% discount rakhein, ye full price par achhi bikti hain.\n"
                f"• **Normal Moving Items:** 10% se 15% bundle discount ('Buy 2 Get ₹50 Off') se basket size badhayein.\n"
                f"• **Dead Stock ({dead_count} items, ₹{dead_capital:,.0f} fasa):** Inpe 25% se 40% clearance discount dein taaki locked paisa wapas nikal sake."
            )
        else:
            prose = (
                f"🏷️ **Recommended Store Discounting Policy:**\n\n"
                f"• **Top Velocity SKUs (e.g. SKU {top_sku}):** 0% discount. Maintain full gross margin.\n"
                f"• **Regular Moving Products:** 10-15% promotional bundle discount to increase basket value.\n"
                f"• **Dead Inventory ({dead_count} items, ₹{dead_capital:,.0f} trapped):** 25-40% clearance markdown to stop storage drag."
            )
        table_rows = [
            {"inventory_type": "Fast Moving (Top Sellers)", "recommended_discount": "0% (Full Margin)", "rationale": "High organic demand"},
            {"inventory_type": "Regular Moving", "recommended_discount": "10% - 15%", "rationale": "Promotional bundle uplift"},
            {"inventory_type": f"Dead Stock ({dead_count} items)", "recommended_discount": "25% - 40%", "rationale": f"Recover ₹{dead_capital:,.0f} locked capital"},
        ]
        suggested = ["Kitna paisa dead stock mein fasa hai?", "Sabse zyada kya bik raha hai?", "Kisko reorder karna chahiye?"]

    # Theme C: Supplier / Vendor / Purchase Order / Kharidari
    elif any(k in q for k in ["supplier", "vendor", "order kab", "order kaise", "purchase", "kharid", "mangwaye", "delivery", "deal"]):
        template_type = "supplier_guidance"
        if user_lang == 'hi':
            prose = (
                f"📦 **Supplier & Purchase Order Guidance:**\n\n"
                f"• **Current Orders:** Abhi aapke {active_pos_count} active Purchase Orders hain (Total: ₹{po_spend:,.0f}).\n"
                f"• **Urgent Orders:** {critical_count} items reorder point se neeche hain, inka PO turant dispatch karein.\n"
                f"• **Cost Saving Tip:** Reorder items ko alag-alag mangwane ke bajay ek consolidated batch me bhejein taaki supplier freight bache aur bulk discount mile."
            )
        else:
            prose = (
                f"📦 **Supplier & Procurement Strategy:**\n\n"
                f"• **Active Pipeline:** Currently tracking {active_pos_count} purchase orders totaling ₹{po_spend:,.0f}.\n"
                f"• **Urgent Need:** {critical_count} SKUs breached safe inventory buffers and require purchase orders today.\n"
                f"• **Optimization Tip:** Consolidate small purchase orders by vendor to maximize freight efficiency."
            )
        table_rows = [
            {"metric": "Active Purchase Orders", "value": f"{active_pos_count} orders", "status": "In Pipeline"},
            {"metric": "Committed PO Spend", "value": f"₹{po_spend:,.0f}", "status": "Committed"},
            {"metric": "Items Needing Immediate PO", "value": f"{critical_count} items", "status": "Urgent Action"},
        ]
        suggested = ["Kisko reorder karna chahiye?", "Show purchase orders", "Kaunse saman ke daam badh rahe hain?"]

    # Theme D: Greetings / Intro / Chit-chat
    elif any(k in q for k in ["namaste", "hello", "hi", "kaise ho", "kya haal", "sun rahe ho", "tum kaun", "who are you", "kya kar sakte"]):
        template_type = "assistant_greeting"
        if user_lang == 'hi':
            prose = (
                f"👋 **Namaste! Main aapka DemandIQ AI Store Advisor hoon.**\n\n"
                f"Main bina kisi external API ke, seedha aapke database se live figures nikal kar sahi decisions lene me madad karta hoon:\n\n"
                f"• **Active Catalog:** {total_products} items tracked\n"
                f"• **Low Stock Alert:** {critical_count} items reorder point par hain\n"
                f"• **Dead Stock:** ₹{dead_capital:,.0f} fasa hua hai\n"
                f"• **Top Selling SKU:** SKU {top_sku} ({top_qty} units)\n\n"
                f"Aap mujhse stock, munafa, discounts, ya purchase order ke baare me kuch bhi puch sakte hain!"
            )
        else:
            prose = (
                f"👋 **Hello! I am your DemandIQ In-House Decision Copilot.**\n\n"
                f"I operate directly on your local database with zero external API fees.\n\n"
                f"• **Active Catalog:** {total_products} items monitored\n"
                f"• **Low Stock Warnings:** {critical_count} items below ROP\n"
                f"• **Trapped Capital:** ₹{dead_capital:,.0f}\n"
                f"• **Top Volume Leader:** SKU {top_sku} ({top_qty} units)\n\n"
                f"Ask me about profit optimization, discounting, purchase orders, or inventory health!"
            )
        table_rows = [
            {"area": "Catalog Scope", "live_data": f"{total_products} SKUs tracked"},
            {"area": "Stock Risk", "live_data": f"{critical_count} items below Reorder Point"},
            {"area": "Dead Inventory", "live_data": f"₹{dead_capital:,.0f} across {dead_count} items"},
            {"area": "Top Volume Leader", "live_data": f"SKU {top_sku} ({top_qty} units)"},
        ]
        suggested = ["Dukaan ka profit kaise badhaye?", "Kisko reorder karna chahiye?", "Kitna paisa dead stock mein fasa hai?"]

    # Theme E: Store Health / Status / Kaisi chal rahi hai
    elif any(k in q for k in ["haal", "kaisi chal rahi", "status", "overview", "summary", "health", "kaisa chal raha", "score", "report"]):
        template_type = "store_health_summary"
        if user_lang == 'hi':
            prose = (
                f"🏪 **Dukaan ki Overall Health & Business Summary:**\n\n"
                f"• **Total Active Products:** {total_products} items monitored.\n"
                f"• **Stock Urgency:** {critical_count} items ka stock low hai, customer demand miss na ho isliye order zaroori hai.\n"
                f"• **Dead Capital:** ₹{dead_capital:,.0f} fasa hua hai ({dead_count} items me).\n"
                f"• **Top Star Product:** SKU {top_sku} (₹{top_rev:,.0f} sales).\n\n"
                f"Aapka store steady chal raha hai, bas low stock items ko replenish karein aur dead stock pe clearance lagayein."
            )
        else:
            prose = (
                f"🏪 **Store Health & Operational Diagnostic:**\n\n"
                f"• **Monitored Catalog:** {total_products} SKUs.\n"
                f"• **Stockout Vulnerability:** {critical_count} items operating under buffer thresholds.\n"
                f"• **Trapped Capital:** ₹{dead_capital:,.0f} in inactive inventory.\n"
                f"• **Top Driver:** SKU {top_sku} with ₹{top_rev:,.0f} gross sales.\n\n"
                f"Store velocity is steady. Prioritize replenishing low stock lines."
            )
        table_rows = [
            {"kpi": "Catalog SKUs", "current_value": str(total_products), "status": "Active"},
            {"kpi": "Reorder Level Breaches", "current_value": f"{critical_count} SKUs", "status": "Action Required" if critical_count > 0 else "Optimal"},
            {"kpi": "Dead Stock Capital", "current_value": f"₹{dead_capital:,.0f}", "status": "Clearance Priority" if dead_capital > 0 else "Clean"},
            {"kpi": "Top Performer", "current_value": f"SKU {top_sku} ({top_qty} units)", "status": "Core Driver"},
        ]
        suggested = ["Kisko reorder karna chahiye?", "Sabse zyada kya bik raha hai?", "Kitna paisa dead stock mein fasa hai?"]

    # Theme F: General Retail & Business Strategy (Universal Fallback)
    else:
        template_type = "general_business_advisory"
        short_q = query_text[:40]
        if user_lang == 'hi':
            prose = (
                f"🎯 **Aapke sawaal ('{short_q}') ke baare me live dukaan analysis:**\n\n"
                f"1. **Stock Health:** Dukaan me {total_products} products me se {critical_count} items low stock par hain aur {dead_count} items slow-moving hain.\n"
                f"2. **Revenue Driver:** SKU {top_sku} ({top_qty} units sold, ₹{top_rev:,.0f}) aapki dukaan ka sabse strong item hai.\n"
                f"3. **Decision Advice:** Dead stock se ₹{dead_capital:,.0f} release karne ke liye clearance discount plan karein aur low stock items ka PO create karein."
            )
        else:
            prose = (
                f"🎯 **Business Advisory regarding '{short_q}':**\n\n"
                f"1. **Inventory Health:** Across {total_products} catalog SKUs, {critical_count} items require immediate replenishment, while {dead_count} are idle.\n"
                f"2. **Revenue Baseline:** SKU {top_sku} ({top_qty} units, ₹{top_rev:,.0f}) is your top velocity driver.\n"
                f"3. **Capital Action:** Release ₹{dead_capital:,.0f} locked in dead inventory to fund replenishment buffers."
            )
        table_rows = [
            {"area": "Catalog Scope", "live_metric": f"{total_products} Products Monitored"},
            {"area": "Immediate Replenishment", "live_metric": f"{critical_count} SKUs below ROP"},
            {"area": "Dead Stock Recovery", "live_metric": f"₹{dead_capital:,.0f} Trapped"},
            {"area": "Top Performing SKU", "live_metric": f"SKU {top_sku} ({top_qty} units)"},
        ]
        suggested = ["Sabse zyada kya bik raha hai?", "Kisko reorder karna chahiye?", "Kitna paisa dead stock mein fasa hai?"]

    return {
        "template_name": template_type,
        "prose": prose,
        "table": {
            "columns": list(table_rows[0].keys()) if table_rows else [],
            "rows": table_rows,
            "total_count": len(table_rows),
        },
        "suggested_prompts": suggested,
    }


def execute_autonomous_po_action(
    db: Session,
    target_dataset: Any,
    query_text: str,
    user_lang: str
) -> Dict[str, Any]:
    """
    Autonomously creates a Purchase Order in the live database based on natural language/voice command.
    Zero external APIs required: fully local PostgreSQL execution.
    """
    q_lower = query_text.lower()

    # 1. Parse SKU
    sku_match = re.search(r'\b(?:sku\s*|product\s*|item\s*)?([0-9]{5,10})\b', q_lower)
    sku = None
    if sku_match:
        sku = sku_match.group(1)
    else:
        # Check known products
        all_skus = db.query(Product.product_id).limit(100).all()
        for s_tuple in all_skus:
            if s_tuple[0].lower() in q_lower:
                sku = s_tuple[0]
                break

    # If no SKU specified, pick top urgent ROP breach or star seller
    if not sku:
        urgent_rec = db.query(InventoryRecommendation).filter(
            InventoryRecommendation.dataset_id == target_dataset.id,
            InventoryRecommendation.status == "PENDING"
        ).order_by(desc(InventoryRecommendation.created_at)).first()
        if urgent_rec:
            sku = urgent_rec.product_id
        else:
            top_demand = db.query(DailyProductDemand.product_id).filter(
                DailyProductDemand.dataset_id == target_dataset.id
            ).group_by(DailyProductDemand.product_id).order_by(desc(func.sum(DailyProductDemand.units_sold))).first()
            if top_demand:
                sku = top_demand[0]
            else:
                first_p = db.query(Product).first()
                sku = first_p.product_id if first_p else "476825"

    # 2. Parse Quantity
    qty = 30  # sensible default batch
    qty_matches = re.findall(r'\b(\d{1,4})\s*(?:unit|units|piece|pieces|qty|quantity|nag|bori|box|boxes|packet|packets)?\b', q_lower)
    if qty_matches:
        for m in qty_matches:
            if sku and m in sku and len(m) >= 4:
                continue
            val = int(m)
            if 1 <= val <= 10000:
                qty = val
                break

    # 3. Product & Unit Cost
    prod = db.query(Product).filter(Product.product_id == sku).first()
    prod_name = prod.product_name if prod and prod.product_name else f"SKU {sku}"
    
    sp = db.query(SupplierProduct).filter(SupplierProduct.product_id == sku).first()
    unit_cost = sp.unit_cost if sp else 120.0
    total_val = round(qty * unit_cost, 2)

    # 4. Supplier
    supplier = db.query(Supplier).filter(Supplier.is_active == True).first()
    if not supplier:
        supplier = Supplier(
            name="Primary Wholesale Distributor",
            contact_phone="+91 98765 43210",
            payment_terms_days=30,
            min_order_value=1000.0,
            is_active=True
        )
        db.add(supplier)
        db.flush()

    # 5. PO Number
    po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{int(time.time()) % 10000:04d}"

    # 6. Database Mutation
    po = PurchaseOrder(
        dataset_id=target_dataset.id,
        po_number=po_number,
        supplier_id=supplier.id,
        status="draft",
        total_value=total_val,
        currency="INR",
        triggered_by="copilot_autonomous",
        notes=f"Autonomous PO created via Copilot user request: '{query_text[:80]}'",
        expected_delivery_date=datetime.now(timezone.utc) + timedelta(days=5)
    )
    db.add(po)
    db.flush()

    line = PurchaseOrderLine(
        po_id=po.id,
        product_id=sku,
        quantity_ordered=qty,
        quantity_received=0,
        unit_cost=unit_cost,
        line_total=total_val,
        reason_code="COPILOT_AUTONOMOUS_ACTION",
        context_data=f'{{"source":"copilot_command","sku":"{sku}","qty":{qty}}}'
    )
    db.add(line)
    db.commit()
    db.refresh(po)

    wa_text = (
        f"Namaste Ji,\n\n"
        f"*DemandIQ Store Purchase Order*\n"
        f"• *PO Number:* {po_number}\n"
        f"• *Product:* SKU {sku} ({prod_name})\n"
        f"• *Quantity:* {qty} units\n"
        f"• *Total Value:* ₹{total_val:,.2f}\n"
        f"• *Delivery Expected:* 5 Days\n\n"
        f"Kripya confirmation dein aur dispatch schedule karein. Dhanyawad!"
    )

    if user_lang == 'hi':
        prose = (
            f"⚡ **Autonomous Action Executed: Purchase Order Live Create Kar Diya Hai!**\n\n"
            f"• **PO Number:** `{po_number}`\n"
            f"• **Item:** SKU {sku} ({prod_name})\n"
            f"• **Order Quantity:** {qty} units (₹{unit_cost:.2f} per unit)\n"
            f"• **Total Order Value:** ₹{total_val:,.2f}\n"
            f"• **Supplier:** {supplier.name}\n"
            f"• **Status:** Saved as **Draft** in live database.\n\n"
            f"Purchase order dukaan ke system me save ho chuka hai. Aap ise **Purchase Orders** page par dekh sakte hain ya neeche diye **WhatsApp Order Slip** button se supplier ko turant bhej sakte hain."
        )
    else:
        prose = (
            f"⚡ **Autonomous Action Executed: Purchase Order Created in Database!**\n\n"
            f"• **PO Number:** `{po_number}`\n"
            f"• **Item:** SKU {sku} ({prod_name})\n"
            f"• **Order Quantity:** {qty} units (@ ₹{unit_cost:.2f}/unit)\n"
            f"• **Total Order Value:** ₹{total_val:,.2f}\n"
            f"• **Supplier:** {supplier.name}\n"
            f"• **Status:** Saved as **Draft** in live database.\n\n"
            f"The purchase order is committed to your live database. You can review it under **Purchase Orders** or send the WhatsApp dispatch slip directly below."
        )

    table_rows = [
        {"field": "PO Number", "value": po_number},
        {"field": "Target SKU", "value": f"{sku} ({prod_name})"},
        {"field": "Quantity Ordered", "value": f"{qty} units"},
        {"field": "Unit Price", "value": f"₹{unit_cost:.2f}"},
        {"field": "Total Order Value", "value": f"₹{total_val:,.2f}"},
        {"field": "Supplier", "value": supplier.name},
        {"field": "Status", "value": "Draft (Saved in DB)"},
    ]

    return {
        "template_name": "autonomous_po_created",
        "prose": prose,
        "table": {
            "columns": ["field", "value"],
            "rows": table_rows,
            "total_count": len(table_rows),
        },
        "action_result": {
            "action_type": "PO_CREATED",
            "po_number": po_number,
            "sku": sku,
            "product_name": prod_name,
            "quantity": qty,
            "total_value": total_val,
            "supplier_name": supplier.name,
            "whatsapp_text": wa_text,
        },
        "suggested_prompts": [
            "Dead stock par 20% discount laga do",
            "Kitna paisa dead stock mein fasa hai?",
            "Dukaan me munafa kaise badhaye?"
        ]
    }


def execute_autonomous_discount_action(
    db: Session,
    target_dataset: Any,
    query_text: str,
    user_lang: str
) -> Dict[str, Any]:
    """
    Autonomously marks Dead Stock records with a clearance discount in the live database.
    Zero external APIs required: fully local PostgreSQL execution.
    """
    q_lower = query_text.lower()

    # 1. Parse discount percentage
    disc_match = re.search(r'(\d{1,2})\s*%', q_lower)
    discount_pct = 0.20
    if disc_match:
        discount_pct = round(int(disc_match.group(1)) / 100.0, 2)
    else:
        num_match = re.search(r'\b(10|15|20|25|30|35|40|50)\b', q_lower)
        if num_match:
            discount_pct = round(int(num_match.group(1)) / 100.0, 2)

    # 2. Query dead stock records
    dead_records = db.query(DeadStockRecord).filter(
        DeadStockRecord.dataset_id == target_dataset.id
    ).all()

    now_utc = datetime.now(timezone.utc)
    total_capital = 0.0
    updated_count = 0
    sample_rows = []

    for rec in dead_records:
        rec.suggested_discount_pct = discount_pct
        rec.recommended_action = "MARKDOWN"
        rec.status = "APPLIED"
        rec.action_notes = f"Clearance markdown of {int(discount_pct * 100)}% applied via Copilot command: '{query_text[:70]}'"
        rec.action_applied_at = now_utc
        cap = float(rec.capital_tied_up or (rec.on_hand * rec.unit_cost))
        total_capital += cap
        updated_count += 1
        if len(sample_rows) < 5:
            sample_rows.append({
                "product_id": rec.product_id,
                "tied_capital": f"₹{cap:,.0f}",
                "discount_applied": f"{int(discount_pct * 100)}%",
                "status": "APPLIED",
                "action": "MARKDOWN"
            })

    db.commit()

    wa_clearance_text = (
        f"📢 *Dukaan Grand Clearance Sale Announcement!*\n\n"
        f"Hamare {updated_count} selected items par flat *{int(discount_pct * 100)}% DISCOUNT* shuru ho gaya hai!\n"
        f"Limited stock available. Jaldi aaiye aur faida uthaiye!\n\n"
        f"📍 Dukaan: DemandIQ Smart Retail Store"
    )

    if user_lang == 'hi':
        prose = (
            f"⚡ **Autonomous Action Executed: {int(discount_pct * 100)}% Clearance Discount Live Apply Kar Diya!**\n\n"
            f"• **Affected Inventory:** Total {updated_count} dead stock items\n"
            f"• **Discount Applied:** {int(discount_pct * 100)}% clearance markdown\n"
            f"• **Unlocked Capital Potential:** ₹{total_capital:,.0f} dukaan ka fasa hua paisa release hoga\n"
            f"• **Database Status:** Saare records ko **APPLIED** mark kar diya gaya hai.\n\n"
            f"Database me updates live ho chuke hain. Aap **Dead Stock** page par check kar sakte hain ya neeche diye button se customer WhatsApp alert bhej sakte hain."
        )
    else:
        prose = (
            f"⚡ **Autonomous Action Executed: {int(discount_pct * 100)}% Clearance Discount Applied!**\n\n"
            f"• **Affected Inventory:** {updated_count} dead stock records\n"
            f"• **Clearance Markdown:** {int(discount_pct * 100)}% applied across lines\n"
            f"• **Unlocked Capital Potential:** ₹{total_capital:,.0f} in inactive inventory queued for recovery\n"
            f"• **Database Status:** Records marked as **APPLIED**.\n\n"
            f"Changes are live in PostgreSQL. Review details under **Dead Stock** or broadcast the customer clearance notice below."
        )

    table_data = sample_rows if sample_rows else [
        {"product_id": "ALL_DEAD_STOCK", "tied_capital": f"₹{total_capital:,.0f}", "discount_applied": f"{int(discount_pct * 100)}%", "status": "APPLIED", "action": "MARKDOWN"}
    ]

    return {
        "template_name": "autonomous_discount_applied",
        "prose": prose,
        "table": {
            "columns": ["product_id", "tied_capital", "discount_applied", "status", "action"],
            "rows": table_data,
            "total_count": len(table_data),
        },
        "action_result": {
            "action_type": "DISCOUNT_APPLIED",
            "discount_pct": discount_pct,
            "records_affected": updated_count,
            "total_capital": total_capital,
            "whatsapp_text": wa_clearance_text,
        },
        "suggested_prompts": [
            "SKU 476825 ka 30 units ka order create karo",
            "Dukaan ki health kaisi hai?",
            "Sabse zyada kya bik raha hai?"
        ]
    }


def detect_and_execute_autonomous_action(
    db: Session,
    target_dataset: Any,
    query_text: str,
    user_lang: str
) -> Optional[Dict[str, Any]]:
    """
    Detects if the user query is an explicit action command (mutating store operations).
    Returns result dictionary if action was executed, else None.
    """
    q_lower = query_text.lower()

    # 1. Action: Create Purchase Order / Reorder
    po_keywords = [
        "order bana", "create order", "order create", "place order", "order place",
        "po bana", "create po", "po create", "generate po", "make po",
        "order lagao", "order do", "reorder kar", "reorder do", "reorder karo",
        "mangwa lo", "maal mangwa", "bhejo order", "order bhej"
    ]
    is_po_action = any(kw in q_lower for kw in po_keywords)
    if is_po_action:
        return execute_autonomous_po_action(db, target_dataset, query_text, user_lang)

    # 2. Action: Apply Clearance Discount on Dead Stock
    discount_action_keywords = [
        "discount laga", "discount apply", "apply discount", "set discount",
        "discount daal", "discount de do", "chhoot laga", "clearance shuru",
        "markdown laga", "markdown karo", "discount kar do"
    ]
    is_discount_action = any(kw in q_lower for kw in discount_action_keywords)
    if is_discount_action:
        return execute_autonomous_discount_action(db, target_dataset, query_text, user_lang)

    return None


def handle_user_natural_language_query(
    db: Session,
    query_text: str,
    dataset_id: Optional[int] = None,
    user_id: Optional[int] = None,
    session_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Main entry point for guarded natural language query execution with audit logging.
    100% In-House & Zero-API: Uses local PostgreSQL data and deterministic advisory engine.
    """
    t0 = time.perf_counter()
    target_dataset = resolve_dataset(db, None, dataset_id)

    # Create or retrieve chat session
    if session_id:
        chat_sess = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    else:
        chat_sess = ChatSession(user_id=user_id, title=query_text[:50])
        db.add(chat_sess)
        db.commit()
        db.refresh(chat_sess)

    # Detect user's query language
    user_lang = detect_query_language(query_text)

    # Check for Autonomous Store Mutation Action first (e.g. create PO, apply discounts):
    action_res = detect_and_execute_autonomous_action(db, target_dataset, query_text, user_lang)
    if action_res:
        exec_ms = round((time.perf_counter() - t0) * 1000, 2)
        user_msg = ChatMessage(session_id=chat_sess.id, sender_role="user", message=query_text)
        bot_msg = ChatMessage(
            session_id=chat_sess.id,
            sender_role="assistant",
            message=action_res["prose"],
            query_template=action_res["template_name"],
            execution_ms=exec_ms,
        )
        db.add_all([user_msg, bot_msg])
        db.commit()

        return {
            "status": "success",
            "session_id": chat_sess.id,
            "template_name": action_res["template_name"],
            "parameters": {},
            "prose": action_res["prose"],
            "table": action_res.get("table", {}),
            "action_result": action_res.get("action_result"),
            "suggested_prompts": action_res.get("suggested_prompts"),
            "execution_ms": exec_ms,
            "detected_language": user_lang,
        }

    parsed_intent = parse_natural_language_intent(query_text)

    # 1. If intent cannot be mapped to rigid templates, use Zero-API Database Advisory Engine
    if not parsed_intent:
        advisory = generate_smart_database_advisory(db, query_text, user_lang, target_dataset)
        exec_ms = round((time.perf_counter() - t0) * 1000, 2)

        # Log to chat
        user_msg = ChatMessage(session_id=chat_sess.id, sender_role="user", message=query_text)
        bot_msg = ChatMessage(
            session_id=chat_sess.id,
            sender_role="assistant",
            message=advisory["prose"],
            query_template=advisory["template_name"],
            execution_ms=exec_ms,
        )
        db.add_all([user_msg, bot_msg])
        db.commit()

        return {
            "status": "success",
            "session_id": chat_sess.id,
            "template_name": advisory["template_name"],
            "parameters": {},
            "prose": advisory["prose"],
            "table": advisory["table"],
            "suggested_prompts": advisory.get("suggested_prompts"),
            "execution_ms": exec_ms,
            "detected_language": user_lang,
        }

    # 2. Execute whitelisted template
    execution_result = execute_guarded_template(db, parsed_intent, dataset_id=dataset_id)
    exec_ms = execution_result["execution_ms"]

    # Choose prose based on user's language
    if user_lang == 'hi' and execution_result.get("prose_hi"):
        final_prose = execution_result["prose_hi"]
    else:
        final_prose = execution_result["prose"]

    # Log to chat history
    user_msg = ChatMessage(session_id=chat_sess.id, sender_role="user", message=query_text)
    bot_msg = ChatMessage(
        session_id=chat_sess.id,
        sender_role="assistant",
        message=final_prose,
        query_template=parsed_intent.template_name,
        template_params=parsed_intent.parameters,
        execution_ms=exec_ms,
    )
    db.add_all([user_msg, bot_msg])
    db.commit()

    return {
        "status": "success",
        "session_id": chat_sess.id,
        "template_name": parsed_intent.template_name,
        "parameters": parsed_intent.parameters,
        "prose": final_prose,
        "table": execution_result["table"],
        "execution_ms": exec_ms,
        "detected_language": user_lang,
    }
