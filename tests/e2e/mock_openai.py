"""Mock OpenAI-compatible chat completions server for the end-to-end UI test (canned SQL for the demo database)."""

import json
import time

from fastapi import FastAPI, Request

app = FastAPI()

ANSWERS = [
    (
        "monthly revenue",
        {
            "sql": "SELECT strftime('%Y-%m', o.order_date) AS month, ROUND(SUM(i.quantity * i.unit_price * (1 - i.discount)), 2) AS revenue\nFROM orders o\nJOIN order_items i ON i.order_id = o.order_id\nWHERE o.status NOT IN ('Cancelled', 'Returned') AND o.order_date >= date('2026-06-30', '-12 months')\nGROUP BY month\nORDER BY month",
            "explanation": "Monthly revenue (excluding cancelled and returned orders) for the last 12 months of data.",
            "chart": {"type": "line", "x": "month", "y": ["revenue"]},
        },
    ),
    (
        "top 10 customers",
        {
            "sql": "SELECT c.company_name, ROUND(SUM(i.quantity * i.unit_price * (1 - i.discount)), 2) AS revenue, COUNT(DISTINCT o.order_id) AS orders\nFROM customers c\nJOIN orders o ON o.customer_id = c.customer_id\nJOIN order_items i ON i.order_id = o.order_id\nWHERE o.status NOT IN ('Cancelled', 'Returned')\nGROUP BY c.customer_id, c.company_name\nORDER BY revenue DESC\nLIMIT 10",
            "explanation": "The ten customers with the highest revenue from non-cancelled, non-returned orders.",
            "chart": {"type": "bar", "x": "company_name", "y": ["revenue"]},
        },
    ),
    (
        "region and customer segment",
        {
            "sql": "SELECT r.name AS region,\n  ROUND(SUM(CASE WHEN c.segment = 'Enterprise' THEN i.quantity * i.unit_price * (1 - i.discount) ELSE 0 END), 2) AS enterprise,\n  ROUND(SUM(CASE WHEN c.segment = 'SMB' THEN i.quantity * i.unit_price * (1 - i.discount) ELSE 0 END), 2) AS smb,\n  ROUND(SUM(CASE WHEN c.segment = 'Consumer' THEN i.quantity * i.unit_price * (1 - i.discount) ELSE 0 END), 2) AS consumer,\n  ROUND(SUM(CASE WHEN c.segment = 'Government' THEN i.quantity * i.unit_price * (1 - i.discount) ELSE 0 END), 2) AS government\nFROM regions r\nJOIN customers c ON c.region_id = r.region_id\nJOIN orders o ON o.customer_id = c.customer_id\nJOIN order_items i ON i.order_id = o.order_id\nWHERE o.status NOT IN ('Cancelled', 'Returned')\nGROUP BY r.name\nORDER BY r.name",
            "explanation": "Revenue per region, split by customer segment.",
            "chart": {"type": "bar", "x": "region", "y": ["enterprise", "smb", "consumer", "government"]},
        },
    ),
    (
        "return rate",
        {
            "sql": "SELECT cat.name AS category, ROUND(100.0 * SUM(CASE WHEN o.status = 'Returned' THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct\nFROM order_items i\nJOIN orders o ON o.order_id = i.order_id\nJOIN products p ON p.product_id = i.product_id\nJOIN categories cat ON cat.category_id = p.category_id\nGROUP BY cat.name\nORDER BY return_rate_pct DESC",
            "explanation": "Share of order lines in each category that belong to returned orders.",
            "chart": {"type": "bar", "x": "category", "y": ["return_rate_pct"]},
        },
    ),
    (
        "broken",
        {
            "sql": "SELECT region_name, COUNT(*) AS customers FROM customers GROUP BY region_name",
            "explanation": "Customers per region.",
        },
    ),
    ("delete", {"sql": "DELETE FROM orders WHERE status = 'Cancelled'", "explanation": "Deletes cancelled orders."}),
    (
        "by channel",
        {
            "sql": "SELECT o.channel, ROUND(AVG(t.order_total), 2) AS avg_order_value, COUNT(*) AS orders\nFROM orders o\nJOIN (SELECT order_id, SUM(quantity * unit_price * (1 - discount)) AS order_total FROM order_items GROUP BY order_id) t ON t.order_id = o.order_id\nGROUP BY o.channel\nORDER BY avg_order_value DESC",
            "explanation": "Average order value and number of orders for each sales channel.",
            "chart": {"type": "pie", "x": "channel", "y": ["orders"]},
        },
    ),
]
REPAIRED = {
    "sql": "SELECT r.name AS region, COUNT(*) AS customers FROM customers c JOIN regions r ON r.region_id = c.region_id GROUP BY r.name ORDER BY customers DESC",
    "explanation": "Number of customers in each region.",
    "chart": {"type": "bar", "x": "region", "y": ["customers"]},
}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    messages = body["messages"]
    last = messages[-1]["content"]
    if "failed with this database error" in last:
        answer = REPAIRED
    elif messages[0]["content"].startswith("You analyze usage"):
        answer = {
            "summary": "Most queries succeed. One query needed an automatic repair because it referenced a column that does not exist.",
            "recommendations": ["Keep rating answers", "Refresh the schema after database changes"],
        }
    else:
        q = last.lower()
        answer = next((a for k, a in ANSWERS if k in q), None)
        if answer is None:
            # follow-up handling: "only 2025" style refinements reuse context
            if "2025" in q and len(messages) > 2:
                answer = {
                    "sql": "SELECT strftime('%Y-%m', o.order_date) AS month, ROUND(SUM(i.quantity * i.unit_price * (1 - i.discount)), 2) AS revenue\nFROM orders o JOIN order_items i ON i.order_id = o.order_id\nWHERE o.status NOT IN ('Cancelled', 'Returned') AND strftime('%Y', o.order_date) = '2025'\nGROUP BY month ORDER BY month",
                    "explanation": "Monthly revenue in 2025 only.",
                    "chart": {"type": "line", "x": "month", "y": ["revenue"]},
                }
            else:
                answer = {
                    "sql": None,
                    "explanation": None,
                    "clarification": "Which metric do you mean - revenue, number of orders, or number of customers?",
                }
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "mock"),
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(answer)}}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
