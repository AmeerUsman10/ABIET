import pytest

from ai.learning.similarity import normalize_question, similarity, singular, tokenize
from ai.llm import LLMError, parse_json_object
from ai.nlp.prompts import Example, Turn, build_messages, quote_ident, rank_tables, render_schema
from ai.nlp.query_processor import QueryProcessor, parse_generation

SCHEMA = {
    "tables": [
        {
            "schema": None,
            "name": "customers",
            "kind": "table",
            "columns": [
                {"name": "customer_id", "type": "INTEGER", "primary_key": True},
                {"name": "segment", "type": "TEXT", "primary_key": False, "values": ["SMB", "Enterprise"]},
            ],
            "foreign_keys": [],
        },
        {
            "schema": None,
            "name": "orders",
            "kind": "table",
            "columns": [
                {"name": "order_id", "type": "INTEGER", "primary_key": True},
                {"name": "customer_id", "type": "INTEGER", "primary_key": False},
                {"name": "total", "type": "NUMERIC", "primary_key": False, "comment": "USD"},
            ],
            "foreign_keys": [
                {"columns": ["customer_id"], "referred_table": "customers", "referred_columns": ["customer_id"]}
            ],
        },
        {
            "schema": None,
            "name": "audit_log",
            "kind": "table",
            "columns": [{"name": "event", "type": "TEXT", "primary_key": False}],
            "foreign_keys": [],
        },
    ]
}


def test_tokenize_and_similarity():
    assert tokenize("Top 10 customers by revenue") == ["top", "10", "customer", "revenue"]
    assert tokenize("orderItems order_date") == ["order", "item", "order", "date"]
    assert singular("categories") == "category" and singular("status") == "status"
    assert similarity("top customers by revenue", "Top 10 customers by revenue") > 0.6
    assert similarity("monthly revenue", "list employees") == 0
    assert normalize_question("  Top  Customers? ") == "top customers"


def test_quote_ident_per_dialect():
    assert quote_ident("orders", "postgresql") == "orders"
    assert quote_ident("OrderDetails", "postgresql") == '"OrderDetails"'
    assert quote_ident("user", "postgresql") == '"user"'
    assert quote_ident("Order Details", "mssql") == "[Order Details]"
    assert quote_ident("OrderDetails", "mssql") == "OrderDetails"
    assert quote_ident("order", "mysql") == "`order`"


def test_schema_rendering_includes_keys_values_and_comments():
    text = render_schema(SCHEMA, "orders by segment", "sqlite", 10000)
    assert "TABLE orders" in text
    assert "customer_id INTEGER -> customers.customer_id" in text
    assert "segment TEXT values: 'SMB', 'Enterprise'" in text
    assert "total NUMERIC -- USD" in text
    assert "order_id INTEGER PK" in text


def test_large_schemas_keep_the_most_relevant_tables():
    ranked = rank_tables(SCHEMA["tables"], "total of orders per customer segment")
    assert ranked[-1]["name"] == "audit_log"
    text = render_schema(SCHEMA, "total of orders", "sqlite", budget=120)
    assert "TABLE orders" in text
    assert "Other tables (columns not shown)" in text
    assert "audit_log" in text


def test_messages_include_dialect_rules_examples_and_history():
    messages = build_messages(
        question="and only for SMB?",
        db_type="mssql",
        schema=SCHEMA,
        examples=[Example(question="orders per customer", sql="SELECT customer_id, COUNT(*) FROM orders GROUP BY 1")],
        history=[Turn(question="orders per customer", sql="SELECT 1", explanation="x")],
        max_rows=500,
        schema_budget=10000,
    )
    system = messages[0]["content"]
    assert "Microsoft SQL Server" in system and "TOP n" in system
    assert "capped at 500 rows" in system
    assert "previously answered correctly" in system
    assert "read-only" in system
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[-1]["content"] == "and only for SMB?"


def test_parse_json_object_tolerates_fences_and_prose():
    assert parse_json_object('```json\n{"sql": "SELECT 1"}\n```') == {"sql": "SELECT 1"}
    assert parse_json_object('Here you go: {"sql": "SELECT 1"} thanks') == {"sql": "SELECT 1"}
    with pytest.raises(LLMError):
        parse_json_object("no json here")
    with pytest.raises(LLMError):
        parse_json_object("[1, 2]")


def test_parse_generation_cleans_sql_and_validates_chart():
    result = parse_generation(
        {"sql": "```sql\nSELECT 1;\n```", "explanation": " One ", "chart": {"type": "bar", "x": "a", "y": "b"}}
    )
    assert result.sql == "SELECT 1"
    assert result.explanation == "One"
    assert result.chart == {"type": "bar", "x": "a", "y": ["b"]}
    assert parse_generation({"sql": "null", "clarification": "Which year?"}).clarification == "Which year?"
    assert parse_generation({"sql": "SELECT 1", "chart": {"type": "radar"}}).chart is None


class OneShot:
    def __init__(self, reply):
        self.reply = reply
        self.messages = None

    def complete_json(self, messages):
        self.messages = messages
        return self.reply


def test_processor_asks_for_clarification_when_nothing_usable_comes_back():
    result = QueryProcessor(OneShot({"sql": None})).generate("hmm", db_type="sqlite", schema=SCHEMA)
    assert result.sql is None and result.clarification


def test_processor_repair_sends_the_error_back():
    llm = OneShot({"sql": "SELECT 2"})
    result = QueryProcessor(llm).repair("q", "SELECT bad", "no such column: bad", db_type="sqlite", schema=SCHEMA)
    assert result.sql == "SELECT 2"
    assert "no such column: bad" in llm.messages[-1]["content"]
    assert llm.messages[-2] == {"role": "assistant", "content": '{"sql": "SELECT bad"}'}


def test_processor_rejects_empty_questions():
    with pytest.raises(ValueError):
        QueryProcessor(OneShot({})).generate("  ", db_type="sqlite", schema=SCHEMA)
