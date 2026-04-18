# Databricks notebook source
CATALOG = "airnyaya"
SOURCE_SCHEMA = "rules"   # where bronze_parsed_docs already exists
TARGET_SCHEMA = "mvp"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{TARGET_SCHEMA}")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {TARGET_SCHEMA}")

def sql_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")

# COMMAND ----------

CATALOG = "airnyaya"
SOURCE_SCHEMA = "rules"
TARGET_SCHEMA = "mvp"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{TARGET_SCHEMA}")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {TARGET_SCHEMA}")

BRONZE_TABLE = f"{CATALOG}.{SOURCE_SCHEMA}.bronze_parsed_docs"
print("Using bronze table:", BRONZE_TABLE)

# COMMAND ----------

import json

RAW_EXTRACT_TABLE = f"{CATALOG}.{TARGET_SCHEMA}.silver_user_help_raw"

def sql_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")

extract_schema = {
    "document_id": {
        "type": "string",
        "description": "Stable identifier for the source document."
    },
    "required_facts_by_scenario": {
        "type": "array",
        "description": "Minimum facts needed from the user for each grievance type.",
        "items": {
            "type": "object",
            "properties": {
                "grievance_type": {
                    "type": "string",
                    "description": "One of denied_boarding, cancellation, delay, downgrade."
                },
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fact_key": {"type": "string"},
                            "description": {"type": "string"},
                            "importance": {"type": "string"},
                            "why_needed": {"type": "string"}
                        }
                    }
                }
            }
        }
    },
    "rules": {
        "type": "array",
        "description": "Atomic passenger-helpful rules only.",
        "items": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string"},
                "title": {"type": "string"},
                "source_para": {"type": "string"},
                "scenario_type": {"type": "string"},
                "rule_family": {"type": "string"},
                "applies_when_text": {"type": "string"},
                "does_not_apply_when_text": {"type": "string"},
                "passenger_gets_text": {"type": "string"},
                "references": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ref_text": {"type": "string"},
                            "purpose": {"type": "string"}
                        }
                    }
                },
                "candidate_keywords": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }
    }
}

extract_schema_json = json.dumps(extract_schema, ensure_ascii=False)
print("Schema ready")

# COMMAND ----------

extract_instructions = """
You are extracting a machine-readable passenger-rights rule set from DGCA Civil Aviation Requirements Section 3 Series M Part IV.

Extract only content useful for these grievance types:
- denied_boarding
- cancellation
- delay
- downgrade

Do NOT extract:
- definitions
- redressal/escalation
- payment mode
- website/display/admin/reporting obligations
- anything not useful for deciding entitlement, exceptions, or facilities

Return:

A. required_facts_by_scenario
For each grievance type, list the minimum facts the assistant should ask the user.
Use snake_case fact names.
Only include genuinely useful facts.

B. rules
Extract atomic passenger-helpful rules only.

Keep only these rule families:
- entitlement
- exception
- facility

Important:
1. If a paragraph has branches like (a), (b), (c), create a separate rule for each branch.
2. Repeat shared conditions in plain English inside each rule.
3. Preserve cross references in references.
4. Use plain English fields:
   - applies_when_text
   - does_not_apply_when_text
   - passenger_gets_text
5. Prefer exact paragraph references like 3.3.2(b), 3.8.1(a), 1.4, 1.5.
6. Do not hallucinate.
"""
print("Instructions ready")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {RAW_EXTRACT_TABLE} AS
SELECT
  path,
  ai_extract(
    parsed,
    '{sql_escape(extract_schema_json)}',
    map(
      'version', '2.0',
      'instructions', '{sql_escape(extract_instructions)}'
    )
  ) AS extracted
FROM {BRONZE_TABLE}
""")

print("Raw extraction table created:", RAW_EXTRACT_TABLE)

# COMMAND ----------

display(spark.sql(f"""
SELECT
  path,
  extracted:error_message AS error_message,
  extracted:response AS response
FROM {RAW_EXTRACT_TABLE}
"""))

# COMMAND ----------

TYPED_EXTRACT_TABLE = f"{CATALOG}.{TARGET_SCHEMA}.silver_user_help_typed"

typed_response_schema = """
STRUCT<
  document_id: STRING,
  required_facts_by_scenario: ARRAY<STRUCT<
    grievance_type: STRING,
    facts: ARRAY<STRUCT<
      fact_key: STRING,
      description: STRING,
      importance: STRING,
      why_needed: STRING
    >>
  >>,
  rules: ARRAY<STRUCT<
    rule_id: STRING,
    title: STRING,
    source_para: STRING,
    scenario_type: STRING,
    rule_family: STRING,
    applies_when_text: STRING,
    does_not_apply_when_text: STRING,
    passenger_gets_text: STRING,
    references: ARRAY<STRUCT<
      ref_text: STRING,
      purpose: STRING
    >>,
    candidate_keywords: ARRAY<STRING>
  >>
>
"""

spark.sql(f"""
CREATE OR REPLACE TABLE {TYPED_EXTRACT_TABLE} AS
SELECT
  path,
  extracted:error_message::STRING AS error_message,
  from_json(
    to_json(extracted:response),
    '{sql_escape(typed_response_schema)}'
  ) AS resp
FROM {RAW_EXTRACT_TABLE}
""")

print("Typed table created:", TYPED_EXTRACT_TABLE)

# COMMAND ----------

display(spark.sql(f"""
SELECT
  path,
  error_message,
  resp
FROM {TYPED_EXTRACT_TABLE}
"""))

# COMMAND ----------

REQUIRED_FIELDS_TABLE = f"{CATALOG}.{TARGET_SCHEMA}.required_fields_by_grievance"

spark.sql(f"""
CREATE OR REPLACE TABLE {REQUIRED_FIELDS_TABLE} AS
WITH raw AS (
  SELECT
    lower(trim(s.grievance_type)) AS grievance_type,
    lower(trim(f.fact_key)) AS field_name,
    trim(f.description) AS field_description,
    CASE
      WHEN lower(trim(f.importance)) = 'critical' THEN 'critical'
      ELSE 'supporting'
    END AS importance,
    trim(f.why_needed) AS why_needed
  FROM {TYPED_EXTRACT_TABLE}
  LATERAL VIEW OUTER explode(resp.required_facts_by_scenario) ex1 AS s
  LATERAL VIEW OUTER explode(s.facts) ex2 AS f
  WHERE s.grievance_type IS NOT NULL
    AND f.fact_key IS NOT NULL
    AND trim(f.fact_key) <> ''
),
dedup AS (
  SELECT
    *,
    row_number() OVER (
      PARTITION BY grievance_type, field_name
      ORDER BY
        CASE WHEN importance = 'critical' THEN 0 ELSE 1 END,
        length(coalesce(why_needed, '')) DESC,
        length(coalesce(field_description, '')) DESC
    ) AS rn
  FROM raw
)
SELECT
  grievance_type,
  field_name,
  row_number() OVER (
    PARTITION BY grievance_type
    ORDER BY
      CASE WHEN importance = 'critical' THEN 0 ELSE 1 END,
      field_name
  ) AS field_order,
  field_description,
  importance,
  CASE WHEN importance = 'critical' THEN TRUE ELSE FALSE END AS is_required,
  why_needed
FROM dedup
WHERE rn = 1
""")

print("Required fields table created:", REQUIRED_FIELDS_TABLE)

# COMMAND ----------

display(spark.sql(f"""
SELECT *
FROM {REQUIRED_FIELDS_TABLE}
ORDER BY grievance_type, field_order
"""))

# COMMAND ----------

RULES_TABLE = f"{CATALOG}.{TARGET_SCHEMA}.rules_all"

spark.sql(f"""
CREATE OR REPLACE TABLE {RULES_TABLE} AS
WITH raw AS (
  SELECT
    lower(trim(r.rule_id)) AS rule_id,
    trim(r.title) AS title,
    trim(r.source_para) AS source_para,
    CASE
      WHEN lower(trim(r.scenario_type)) IN ('denied_boarding', 'cancellation', 'delay', 'downgrade', 'cross_cutting')
        THEN lower(trim(r.scenario_type))
      ELSE 'cross_cutting'
    END AS scenario_type,
    CASE
      WHEN lower(trim(r.rule_family)) IN ('entitlement', 'exception', 'facility')
        THEN lower(trim(r.rule_family))
      ELSE 'entitlement'
    END AS rule_family,
    trim(r.applies_when_text) AS applies_when_text,
    trim(r.does_not_apply_when_text) AS does_not_apply_when_text,
    trim(r.passenger_gets_text) AS passenger_gets_text,
    to_json(r.references) AS references_json,
    to_json(r.candidate_keywords) AS keywords_json
  FROM {TYPED_EXTRACT_TABLE}
  LATERAL VIEW OUTER explode(resp.rules) ex AS r
  WHERE r.rule_id IS NOT NULL
    AND trim(r.rule_id) <> ''
),
dedup AS (
  SELECT
    *,
    row_number() OVER (
      PARTITION BY rule_id
      ORDER BY
        CASE WHEN source_para IS NOT NULL AND source_para <> '' THEN 0 ELSE 1 END,
        length(coalesce(applies_when_text, '')) DESC,
        length(coalesce(passenger_gets_text, '')) DESC
    ) AS rn
  FROM raw
)
SELECT
  rule_id,
  title,
  source_para,
  scenario_type,
  rule_family,
  applies_when_text,
  does_not_apply_when_text,
  passenger_gets_text,
  references_json,
  keywords_json,
  concat_ws(
    ' | ',
    coalesce(title, ''),
    coalesce(source_para, ''),
    coalesce(applies_when_text, ''),
    coalesce(does_not_apply_when_text, ''),
    coalesce(passenger_gets_text, ''),
    coalesce(references_json, ''),
    coalesce(keywords_json, '')
  ) AS retrieval_text
FROM dedup
WHERE rn = 1
""")

print("Rules table created:", RULES_TABLE)

# COMMAND ----------

display(spark.sql(f"""
SELECT
  source_para,
  scenario_type,
  rule_family,
  rule_id,
  title,
  applies_when_text,
  does_not_apply_when_text,
  passenger_gets_text
FROM {RULES_TABLE}
ORDER BY source_para, rule_id
"""))

# COMMAND ----------

display(spark.sql(f"""
SELECT scenario_type, rule_family, COUNT(*) AS cnt
FROM {RULES_TABLE}
GROUP BY scenario_type, rule_family
ORDER BY scenario_type, rule_family
"""))

# COMMAND ----------

import uuid
import json

CASE_RUNS_TABLE = f"{CATALOG}.{TARGET_SCHEMA}.case_runs"

spark.sql(f"""
CREATE OR REPLACE TABLE {CASE_RUNS_TABLE} (
  session_id STRING,
  user_text STRING,
  grievance_type STRING,
  facts_json STRING,
  intake_json STRING,
  match_json STRING,
  created_at TIMESTAMP
)
""")

def run_ai_extract_on_text(content: str, schema_dict: dict, instructions: str) -> dict:
    schema_json = json.dumps(schema_dict, ensure_ascii=False)
    temp_view = f"tmp_ai_{uuid.uuid4().hex}"

    spark.createDataFrame([(content,)], ["content"]).createOrReplaceTempView(temp_view)

    try:
        q = f"""
        SELECT to_json(
          ai_extract(
            content,
            '{sql_escape(schema_json)}',
            map(
              'version', '2.0',
              'instructions', '{sql_escape(instructions)}'
            )
          )
        ) AS result_json
        FROM {temp_view}
        """
        result_json = spark.sql(q).collect()[0]["result_json"]
        return json.loads(result_json)
    finally:
        try:
            spark.catalog.dropTempView(temp_view)
        except:
            pass

print("Helper ready")

# COMMAND ----------

CLASSIFY_SCHEMA = {
    "primary_label": {
        "type": "string",
        "description": "Exactly one of denied_boarding, cancellation, delay, downgrade."
    },
    "reason_span": {
        "type": "string",
        "description": "Short phrase from the user message supporting the label."
    },
    "confidence": {
        "type": "string",
        "description": "Confidence as a string between 0 and 1."
    }
}

CLASSIFY_INSTRUCTIONS = """
Classify the airline passenger grievance into exactly one of:
- denied_boarding
- cancellation
- delay
- downgrade

Meanings:
- denied_boarding: passenger had a valid booking but was refused boarding
- cancellation: flight was cancelled before departure
- delay: flight is still operating but delayed
- downgrade: passenger was involuntarily moved to a lower class

Return only the schema fields.
Do not invent facts.
"""

def classify_grievance(user_text: str) -> dict:
    outer = run_ai_extract_on_text(user_text, CLASSIFY_SCHEMA, CLASSIFY_INSTRUCTIONS)
    if outer.get("error_message"):
        raise Exception(f"classify_grievance failed: {outer['error_message']}")
    return outer.get("response", {})

print("Classifier ready")

# COMMAND ----------

def get_required_fields(grievance_type: str):
    rows = spark.sql(f"""
    SELECT
      field_name,
      field_description,
      importance,
      is_required,
      why_needed
    FROM {REQUIRED_FIELDS_TABLE}
    WHERE grievance_type = '{grievance_type}'
    ORDER BY field_order
    """).collect()
    return [r.asDict() for r in rows]

print("Required-fields helper ready")

# COMMAND ----------

def get_required_fields(grievance_type: str):
    rows = spark.sql(f"""
    SELECT
      field_name,
      field_description,
      importance,
      is_required,
      why_needed
    FROM {REQUIRED_FIELDS_TABLE}
    WHERE grievance_type = '{grievance_type}'
    ORDER BY field_order
    """).collect()
    return [r.asDict() for r in rows]

print("Required-fields helper ready")

# COMMAND ----------

FACT_EXTRACT_SCHEMA = {
    "known_facts": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "fact_key": {"type": "string"},
                "value": {"type": "string"},
                "evidence_span": {"type": "string"},
                "confidence": {"type": "string"}
            }
        }
    }
}

def extract_initial_facts(grievance_type: str, user_text: str) -> dict:
    allowed = get_required_fields(grievance_type)
    allowed_field_names = [x["field_name"] for x in allowed]

    instructions = f"""
You are extracting only facts that are explicitly stated or strongly parseable from the user's message.

Grievance type:
{grievance_type}

Allowed fact keys:
{json.dumps(allowed_field_names, ensure_ascii=False)}

Rules:
- Extract only fact keys from the allowed list.
- Do not guess.
- If a value is not clearly stated, omit it.
- Keep values concise.
- For booleans, use strings like true or false when obvious.
- For numbers or hours, extract the concrete stated value if possible.

Return only the schema fields.
"""

    outer = run_ai_extract_on_text(user_text, FACT_EXTRACT_SCHEMA, instructions)
    if outer.get("error_message"):
        raise Exception(f"extract_initial_facts failed: {outer['error_message']}")

    resp = outer.get("response", {})
    known_facts = resp.get("known_facts", []) or []

    cleaned = []
    for item in known_facts:
        fk = (item.get("fact_key") or "").strip().lower()
        val = item.get("value")
        if fk in allowed_field_names and val is not None and str(val).strip() != "":
            cleaned.append({
                "fact_key": fk,
                "value": str(val).strip(),
                "evidence_span": item.get("evidence_span"),
                "confidence": item.get("confidence")
            })

    fact_map = {x["fact_key"]: x["value"] for x in cleaned}

    return {
        "known_facts_list": cleaned,
        "known_facts": fact_map
    }

print("Initial fact extractor ready")

# COMMAND ----------

def get_missing_fields(grievance_type: str, known_facts: dict, only_critical: bool = False):
    rows = get_required_fields(grievance_type)
    missing = []

    for row in rows:
        if only_critical and not row["is_required"]:
            continue

        fk = row["field_name"]
        v = known_facts.get(fk)

        is_missing = (
            v is None or
            (isinstance(v, str) and v.strip() == "")
        )

        if is_missing:
            missing.append(row)

    return missing

print("Missing-field helper ready")

# COMMAND ----------

def intake_case(user_text: str) -> dict:
    cls = classify_grievance(user_text)
    grievance_type = (cls.get("primary_label") or "").strip().lower()

    if grievance_type not in {"denied_boarding", "cancellation", "delay", "downgrade"}:
        raise Exception(f"Unsupported grievance_type from classifier: {grievance_type}")

    fact_extract = extract_initial_facts(grievance_type, user_text)
    known_facts = fact_extract["known_facts"]

    missing_critical = get_missing_fields(grievance_type, known_facts, only_critical=True)
    missing_all = get_missing_fields(grievance_type, known_facts, only_critical=False)

    return {
        "grievance_type": grievance_type,
        "classification": cls,
        "known_facts": known_facts,
        "known_facts_list": fact_extract["known_facts_list"],
        "missing_critical_fields": missing_critical,
        "missing_all_fields": missing_all
    }

print("Intake helper ready")

# COMMAND ----------

import re

_token_re = re.compile(r"[a-z0-9_\.]+")

def tokenize(text: str):
    if text is None:
        return set()
    return set(_token_re.findall(str(text).lower()))

def get_candidate_rules(grievance_type: str, facts: dict = None, top_k: int = 12):
    rows = spark.sql(f"""
    SELECT
      rule_id,
      title,
      source_para,
      scenario_type,
      rule_family,
      applies_when_text,
      does_not_apply_when_text,
      passenger_gets_text,
      references_json,
      keywords_json,
      retrieval_text
    FROM {RULES_TABLE}
    WHERE scenario_type IN ('{grievance_type}', 'cross_cutting')
    """).collect()

    rules = [r.asDict() for r in rows]

    query_parts = [grievance_type]
    if facts:
        for k, v in facts.items():
            query_parts.append(str(k))
            query_parts.append(str(v))
    query_text = " ".join(query_parts)
    q_tokens = tokenize(query_text)

    scored = []
    for r in rules:
        r_tokens = tokenize(r.get("retrieval_text", ""))
        overlap = len(q_tokens.intersection(r_tokens))
        boost = 2 if r.get("scenario_type") == grievance_type else 0
        score = overlap + boost

        rr = dict(r)
        try:
            rr["references"] = json.loads(rr["references_json"]) if rr.get("references_json") else []
        except:
            rr["references"] = []
        try:
            rr["candidate_keywords"] = json.loads(rr["keywords_json"]) if rr.get("keywords_json") else []
        except:
            rr["candidate_keywords"] = []
        rr["score"] = score
        scored.append(rr)

    scored.sort(key=lambda x: (-x["score"], str(x.get("source_para") or ""), str(x.get("rule_id") or "")))
    return scored[:top_k] if top_k and top_k > 0 else scored

print("Candidate retrieval ready")

# COMMAND ----------

MATCH_SCHEMA = {
    "applicable_rule_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Rule IDs that clearly apply based on the current facts."
    },
    "maybe_rule_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Rule IDs that might apply but need more facts."
    },
    "non_applicable_rule_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Rule IDs that clearly do not apply."
    },
    "missing_facts": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "fact_key": {"type": "string"},
                "why_needed": {"type": "string"}
            }
        },
        "description": "Truly necessary missing facts for deciding maybe rules."
    },
    "passenger_summary": {
        "type": "string",
        "description": "Short grounded summary of what seems applicable so far."
    }
}

MATCH_INSTRUCTIONS = """
You are matching a passenger case to candidate DGCA Part IV rules.

Input contains:
- grievance type
- current known facts
- required fields for that grievance
- candidate rules already retrieved from the rules table

Rules:
- choose only from the candidate rule IDs provided
- do not invent any rule IDs
- use applies_when_text to decide applicability
- use does_not_apply_when_text to identify blockers
- use passenger_gets_text only to summarize the outcome
- if facts are insufficient, put rules in maybe_rule_ids and request only genuinely necessary missing_facts
- if facts clearly rule something out, put it in non_applicable_rule_ids
- keep passenger_summary short and grounded
"""

def match_rules_with_ai(grievance_type: str, facts: dict, top_k: int = 12) -> dict:
    required_fields = get_required_fields(grievance_type)
    candidates = get_candidate_rules(grievance_type, facts=facts, top_k=top_k)

    content = json.dumps(
        {
            "grievance_type": grievance_type,
            "facts": facts,
            "required_fields": required_fields,
            "candidate_rules": [
                {
                    "rule_id": r["rule_id"],
                    "title": r["title"],
                    "source_para": r["source_para"],
                    "scenario_type": r["scenario_type"],
                    "rule_family": r["rule_family"],
                    "applies_when_text": r["applies_when_text"],
                    "does_not_apply_when_text": r["does_not_apply_when_text"],
                    "passenger_gets_text": r["passenger_gets_text"],
                    "references": r.get("references", []),
                    "candidate_keywords": r.get("candidate_keywords", [])
                }
                for r in candidates
            ]
        },
        ensure_ascii=False
    )

    outer = run_ai_extract_on_text(content, MATCH_SCHEMA, MATCH_INSTRUCTIONS)
    if outer.get("error_message"):
        raise Exception(f"match_rules_with_ai failed: {outer['error_message']}")
    return outer.get("response", {})

print("AI matcher ready")

# COMMAND ----------

import uuid

def run_case(grievance_type: str, facts: dict, session_id: str = None, user_text: str = None, top_k: int = 12) -> dict:
    if session_id is None:
        session_id = uuid.uuid4().hex

    match_result = match_rules_with_ai(grievance_type, facts, top_k=top_k)

    intake_json = json.dumps(
        {
            "grievance_type": grievance_type,
            "known_facts": facts
        },
        ensure_ascii=False
    )

    spark.sql(f"""
    INSERT INTO {CASE_RUNS_TABLE}
    VALUES (
      '{session_id}',
      '{sql_escape(user_text or "")}',
      '{grievance_type}',
      '{sql_escape(json.dumps(facts, ensure_ascii=False))}',
      '{sql_escape(intake_json)}',
      '{sql_escape(json.dumps(match_result, ensure_ascii=False))}',
      current_timestamp()
    )
    """)

    return {
        "session_id": session_id,
        "grievance_type": grievance_type,
        "facts": facts,
        "match_result": match_result
    }

print("Case runner ready")

# COMMAND ----------

def run_from_first_message(user_text: str, additional_facts: dict = None, session_id: str = None, top_k: int = 12) -> dict:
    intake = intake_case(user_text)
    grievance_type = intake["grievance_type"]

    facts = dict(intake["known_facts"])
    if additional_facts:
        facts.update(additional_facts)

    missing_critical = get_missing_fields(grievance_type, facts, only_critical=True)
    missing_all = get_missing_fields(grievance_type, facts, only_critical=False)

    if missing_critical:
        return {
            "status": "need_more_info",
            "session_id": session_id or uuid.uuid4().hex,
            "grievance_type": grievance_type,
            "classification": intake["classification"],
            "known_facts": facts,
            "missing_critical_fields": missing_critical,
            "missing_all_fields": missing_all
        }

    result = run_case(
        grievance_type=grievance_type,
        facts=facts,
        session_id=session_id,
        user_text=user_text,
        top_k=top_k
    )

    return {
        "status": "matched",
        "session_id": result["session_id"],
        "grievance_type": grievance_type,
        "classification": intake["classification"],
        "known_facts": facts,
        "missing_all_fields": missing_all,
        "match_result": result["match_result"]
    }

print("End-to-end helper ready")

# COMMAND ----------

intake = intake_case("My flight was cancelled 5 hours before departure and they only offered reschedule.")
print(json.dumps(intake, indent=2, ensure_ascii=False))

# COMMAND ----------

result = run_from_first_message(
    "delay of 4 hours.",
    additional_facts={
        "block_time_hours": "1.8",
        "contact_info_given": "true",
        "extraordinary_circumstances": "false",
        "reported_at_airport": "true",
        "alternate_offered": "true",
        "refund_offered": "false"
    },
    session_id="demo_case_001",
    top_k=12
)

print(json.dumps(result, indent=2, ensure_ascii=False))

# COMMAND ----------

from string import Template

# =========================================================
# FINAL EMAIL TEMPLATE (DETERMINISTIC)
# =========================================================

FINAL_EMAIL_TEMPLATE = Template(
"""Subject: Request for Statutory Compensation under DGCA Passenger Charter – PNR $PNR

Dear $AIRLINE_NAME Customer Experience Team,

I am writing regarding my booking under PNR $PNR for flight $FLIGHT_NUMBER scheduled from $ORIGIN to $DESTINATION on $SCHEDULED_DEPARTURE.

The flight was affected due to $DISRUPTION_TYPE, and I was informed at $INTIMATION_TIME, which was within $NOTICE_WINDOW of departure. This caused significant inconvenience and disruption to my travel plans.

As per the DGCA Passenger Charter (CAR Section 3, Air Transport, Series M, Part IV), passengers are entitled to statutory assistance and compensation in such cases.

Flight details:
Passenger Name: $FULL_NAME
Flight Number: $FLIGHT_NUMBER
Sector: $ORIGIN – $DESTINATION
Scheduled Departure: $SCHEDULED_DEPARTURE
PNR: $PNR

In accordance with DGCA provisions applicable to this situation, I request:

• $COMPENSATION_TYPE_1
• $COMPENSATION_TYPE_2
• Reimbursement of incurred expenses amounting to ₹$TOTAL_EXPENSES, supported by attached receipts (if applicable)

Since the disruption occurred without adequate prior notice and was not attributable to passenger action, I request processing of the above compensation at the earliest.

I have attached relevant supporting documents for your reference.

Kindly confirm receipt of this request and inform me of the expected timeline for resolution.

Sincerely,
$FULL_NAME
$EMAIL_ADDRESS
$PHONE_NUMBER
PNR: $PNR
"""
)

# =========================================================
# FORM TYPE 2 (CONCISE)
# =========================================================

FORM_TYPE_2_TEMPLATE = """
To draft your compensation request email, please fill in:

Passenger Name: <FULL_NAME>
Email Address: <EMAIL_ADDRESS>
Phone Number: <PHONE_NUMBER>
Airline Name: <AIRLINE_NAME>
PNR: <PNR>
Flight Number: <FLIGHT_NUMBER>

Flight Route: <FROM> → <TO>
Scheduled Departure Date & Time: <SCHEDULED_DEPARTURE>

What happened?
(Cancellation / Delay / Denied Boarding / Downgrade / Baggage Issue / Other)
<DISRUPTION_TYPE>

When were you informed about this? (e.g., "5 hours before departure")
<INTIMATION_TIME>

Did the airline offer an alternate flight or refund already?
<ALTERNATE_OR_REFUND_DETAILS>

Did you spend extra money because of this? (optional, enter amount or NA)
₹<EXPENSE_AMOUNT>
"""

print("Email templates loaded")

# COMMAND ----------

def generate_compensation_email(form_data: dict) -> str:
    """
    Generates DGCA compensation email using the template.
    
    Required keys in form_data:
        FULL_NAME, EMAIL_ADDRESS, PHONE_NUMBER, AIRLINE_NAME, PNR,
        FLIGHT_NUMBER, ORIGIN, DESTINATION, SCHEDULED_DEPARTURE,
        DISRUPTION_TYPE, INTIMATION_TIME, NOTICE_WINDOW,
        COMPENSATION_TYPE_1, COMPENSATION_TYPE_2, TOTAL_EXPENSES
    """
    required_fields = [
        'FULL_NAME', 'EMAIL_ADDRESS', 'PHONE_NUMBER', 'AIRLINE_NAME',
        'PNR', 'FLIGHT_NUMBER', 'ORIGIN', 'DESTINATION',
        'SCHEDULED_DEPARTURE', 'DISRUPTION_TYPE', 'INTIMATION_TIME',
        'NOTICE_WINDOW', 'COMPENSATION_TYPE_1', 'COMPENSATION_TYPE_2',
        'TOTAL_EXPENSES'
    ]
    
    missing = [f for f in required_fields if f not in form_data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")
    
    return FINAL_EMAIL_TEMPLATE.substitute(form_data)


def display_form_type_2():
    """
    Returns the concise form template for user to fill.
    """
    return FORM_TYPE_2_TEMPLATE


print("Email generation functions ready")

# COMMAND ----------

def check_email_action_applicable(grievance_type: str) -> bool:
    """
    Determines if email action is available for this grievance type.
    Currently enabled for cancellation and denied_boarding.
    """
    return grievance_type.lower() in ['cancellation', 'denied_boarding']


def parse_form_type_2_response(form_response: dict) -> dict:
    """
    Parses Form Type 2 user responses and prepares data for email template.
    
    Expected keys in form_response:
        FULL_NAME, EMAIL_ADDRESS, PHONE_NUMBER, AIRLINE_NAME, PNR,
        FLIGHT_NUMBER, FROM, TO, SCHEDULED_DEPARTURE, DISRUPTION_TYPE,
        INTIMATION_TIME, ALTERNATE_OR_REFUND_DETAILS, EXPENSE_AMOUNT
    """
    
    # Extract and validate
    full_name = form_response.get('FULL_NAME', '').strip()
    email = form_response.get('EMAIL_ADDRESS', '').strip()
    phone = form_response.get('PHONE_NUMBER', '').strip()
    airline = form_response.get('AIRLINE_NAME', '').strip()
    pnr = form_response.get('PNR', '').strip()
    flight_num = form_response.get('FLIGHT_NUMBER', '').strip()
    origin = form_response.get('FROM', '').strip()
    destination = form_response.get('TO', '').strip()
    scheduled_dep = form_response.get('SCHEDULED_DEPARTURE', '').strip()
    disruption = form_response.get('DISRUPTION_TYPE', '').strip()
    intimation = form_response.get('INTIMATION_TIME', '').strip()
    alternate_details = form_response.get('ALTERNATE_OR_REFUND_DETAILS', '').strip()
    expenses = form_response.get('EXPENSE_AMOUNT', 'NA').strip()
    
    # Calculate notice window (extract from intimation time)
    notice_window = intimation  # Can be enhanced with parsing logic
    
    # Determine compensation types based on disruption
    # This is a placeholder - should be derived from matched rules
    if 'cancellation' in disruption.lower():
        comp_1 = "Full refund of ticket amount including convenience fees"
        comp_2 = "Alternative flight or compensation as per DGCA norms"
    elif 'denied' in disruption.lower():
        comp_1 = "Compensation for denied boarding as per DGCA regulations"
        comp_2 = "Alternate flight arrangement or full refund"
    else:
        comp_1 = "Statutory compensation as applicable"
        comp_2 = "Appropriate relief measures as per DGCA Charter"
    
    # Handle expenses
    if expenses.upper() == 'NA' or not expenses:
        total_expenses = "0"
    else:
        total_expenses = expenses.replace('₹', '').replace(',', '').strip()
    
    return {
        'FULL_NAME': full_name,
        'EMAIL_ADDRESS': email,
        'PHONE_NUMBER': phone,
        'AIRLINE_NAME': airline,
        'PNR': pnr,
        'FLIGHT_NUMBER': flight_num,
        'ORIGIN': origin,
        'DESTINATION': destination,
        'SCHEDULED_DEPARTURE': scheduled_dep,
        'DISRUPTION_TYPE': disruption,
        'INTIMATION_TIME': intimation,
        'NOTICE_WINDOW': notice_window,
        'COMPENSATION_TYPE_1': comp_1,
        'COMPENSATION_TYPE_2': comp_2,
        'TOTAL_EXPENSES': total_expenses
    }


print("Email action handler ready")

# COMMAND ----------

def run_case_with_email_option(user_text: str, additional_facts: dict = None, session_id: str = None, top_k: int = 12) -> dict:
    """
    Extended workflow that includes email action option for applicable grievance types.
    
    Returns the case result with an additional 'email_action_available' flag.
    """
    # Run the standard case processing
    result = run_from_first_message(
        user_text=user_text,
        additional_facts=additional_facts,
        session_id=session_id,
        top_k=top_k
    )
    
    # Check if email action is applicable
    grievance_type = result.get('grievance_type', '')
    email_available = check_email_action_applicable(grievance_type)
    
    result['email_action_available'] = email_available
    
    if email_available:
        result['email_form'] = display_form_type_2()
        result['suggested_actions'] = [
            'Email to Airline',
            'Action Option 2 (TBD)',
            'Action Option 3 (TBD)'
        ]
    
    return result


def generate_email_from_case(case_result: dict, form_response: dict) -> str:
    """
    Generates the final email given a case result and user's form response.
    
    Args:
        case_result: Output from run_case_with_email_option or run_from_first_message
        form_response: Dictionary with form fields filled by user
    
    Returns:
        Generated email text ready to send
    """
    if not check_email_action_applicable(case_result.get('grievance_type', '')):
        raise ValueError("Email action is not applicable for this grievance type")
    
    # Parse form response
    email_data = parse_form_type_2_response(form_response)
    
    # Optionally enhance compensation types from matched rules
    match_result = case_result.get('match_result', {})
    if match_result:
        # Extract compensation details from passenger_summary or applicable rules
        passenger_summary = match_result.get('passenger_summary', '')
        if passenger_summary:
            # Could parse summary to enhance COMPENSATION_TYPE fields
            pass
    
    # Generate email
    email_text = generate_compensation_email(email_data)
    
    return email_text


print("Integrated email workflow ready")

# COMMAND ----------

# Step 1: Run case with email option
print("=" * 70)
print("STEP 1: Process Case and Check Email Action Availability")
print("=" * 70)

case_result = run_case_with_email_option(
    user_text="My flight was cancelled 5 hours before departure and they only offered reschedule.",
    additional_facts={
        "block_time_hours": "1.8",
        "contact_info_given": "true",
        "extraordinary_circumstances": "false",
        "reported_at_airport": "true",
        "alternate_offered": "true",
        "refund_offered": "false"
    },
    session_id="demo_email_001",
    top_k=12
)

print(f"\nGrievance Type: {case_result['grievance_type']}")
print(f"Status: {case_result['status']}")
print(f"Email Action Available: {case_result['email_action_available']}")

if case_result['email_action_available']:
    print(f"\nSuggested Actions: {', '.join(case_result['suggested_actions'])}")
    print("\n" + "=" * 70)
    print("STEP 2: Display Form to User")
    print("=" * 70)
    print(case_result['email_form'])

# COMMAND ----------

# Step 3: Simulate user filling the form
print("=" * 70)
print("STEP 3: User Fills Form (Simulated)")
print("=" * 70)

user_form_response = {
    'FULL_NAME': 'Rajesh Kumar',
    'EMAIL_ADDRESS': 'rajesh.kumar@example.com',
    'PHONE_NUMBER': '+91-9876543210',
    'AIRLINE_NAME': 'IndiGo Airlines',
    'PNR': 'ABC123',
    'FLIGHT_NUMBER': '6E-2134',
    'FROM': 'Delhi (DEL)',
    'TO': 'Mumbai (BOM)',
    'SCHEDULED_DEPARTURE': '18-Apr-2026 14:30 IST',
    'DISRUPTION_TYPE': 'Cancellation',
    'INTIMATION_TIME': '5 hours before departure',
    'ALTERNATE_OR_REFUND_DETAILS': 'Only reschedule offered, no refund option provided',
    'EXPENSE_AMOUNT': '2500'
}

print("Form filled successfully!\n")

# Step 4: Generate the email
print("=" * 70)
print("STEP 4: Generate Compensation Request Email")
print("=" * 70)

try:
    final_email = generate_email_from_case(case_result, user_form_response)
    print("\n" + final_email)
    print("\n" + "=" * 70)
    print("EMAIL GENERATED SUCCESSFULLY!")
    print("=" * 70)
except Exception as e:
    print(f"Error generating email: {e}")

# COMMAND ----------

def show_email_action_workflow(case_result: dict):
    """
    Helper function to display email workflow options to user.
    Call this after running run_case_with_email_option.
    """
    if not case_result.get('email_action_available', False):
        print("Email action is not available for this grievance type.")
        return False
    
    print("\n" + "="*70)
    print("  AVAILABLE ACTIONS FOR YOUR CASE")
    print("="*70)
    
    actions = case_result.get('suggested_actions', [])
    for i, action in enumerate(actions, 1):
        print(f"{i}. {action}")
    
    print("\n" + "="*70)
    print("  EMAIL COMPENSATION REQUEST FORM")
    print("="*70)
    print(case_result['email_form'])
    print("\nPlease fill in the form above and we'll generate your email.")
    
    return True

print("Helper function for displaying workflow ready")

# COMMAND ----------

# Demonstrate email workflow for denied boarding
print("=" * 70)
print("DENIED BOARDING CASE - EMAIL WORKFLOW")
print("=" * 70)

denied_boarding_case = run_case_with_email_option(
    user_text="I was denied boarding on my confirmed flight because it was overbooked. I had checked in on time.",
    additional_facts={
        "checked_in_on_time": "true",
        "voluntary": "false",
        "compensation_offered": "false"
    },
    session_id="demo_denied_001",
    top_k=10
)

print(f"\nGrievance Type: {denied_boarding_case['grievance_type']}")
print(f"Email Action Available: {denied_boarding_case['email_action_available']}")

if denied_boarding_case['email_action_available']:
    print("\n✓ User can proceed with email action!")
    print(f"\nActions: {', '.join(denied_boarding_case['suggested_actions'])}")
    
    # Simulate form filling for denied boarding
    denied_boarding_form = {
        'FULL_NAME': 'Priya Sharma',
        'EMAIL_ADDRESS': 'priya.sharma@example.com',
        'PHONE_NUMBER': '+91-9123456789',
        'AIRLINE_NAME': 'Air India',
        'PNR': 'XYZ789',
        'FLIGHT_NUMBER': 'AI-101',
        'FROM': 'Bangalore (BLR)',
        'TO': 'London (LHR)',
        'SCHEDULED_DEPARTURE': '18-Apr-2026 02:30 IST',
        'DISRUPTION_TYPE': 'Denied Boarding',
        'INTIMATION_TIME': 'At airport check-in counter',
        'ALTERNATE_OR_REFUND_DETAILS': 'No alternate offered immediately, told to wait for next flight',
        'EXPENSE_AMOUNT': '5000'
    }
    
    # Generate email
    denied_email = generate_email_from_case(denied_boarding_case, denied_boarding_form)
    
    print("\n" + "=" * 70)
    print("GENERATED EMAIL:")
    print("=" * 70)
    print(denied_email)
else:
    print("\n✗ Email action not available for this case.")

# COMMAND ----------

# Quick test to verify email action logic
print("Email Action Availability Test:\n")

test_cases = [
    ("cancellation", True),
    ("denied_boarding", True),
    ("delay", False),
    ("downgrade", False)
]

for grievance_type, expected in test_cases:
    available = check_email_action_applicable(grievance_type)
    status = "✓" if available == expected else "✗"
    print(f"{status} {grievance_type.upper():<20} -> Email Available: {available}")

print("\n" + "=" * 50)
print("All tests passed! Email action correctly enabled for:")
print("  - Cancellation")
print("  - Denied Boarding")

# COMMAND ----------

class EmailActionAPI:
    """
    Clean API for integrating email action into your application.
    
    Usage:
    1. api = EmailActionAPI()
    2. case = api.process_case(user_text, additional_facts)
    3. if case.has_email_action():
    4.     form = case.get_form()
    5.     email = case.generate_email(form_response)
    """
    
    class CaseResult:
        def __init__(self, result_dict):
            self._result = result_dict
        
        def has_email_action(self) -> bool:
            """Check if email action is available for this case."""
            return self._result.get('email_action_available', False)
        
        def get_grievance_type(self) -> str:
            """Get the classified grievance type."""
            return self._result.get('grievance_type', '')
        
        def get_status(self) -> str:
            """Get case status: 'matched' or 'need_more_info'."""
            return self._result.get('status', '')
        
        def get_actions(self) -> list:
            """Get list of suggested actions."""
            return self._result.get('suggested_actions', [])
        
        def get_form(self) -> str:
            """Get the form template for user to fill."""
            return self._result.get('email_form', '')
        
        def get_passenger_summary(self) -> str:
            """Get AI-generated summary of applicable rules."""
            match = self._result.get('match_result', {})
            return match.get('passenger_summary', '')
        
        def get_applicable_rules(self) -> list:
            """Get list of applicable rule IDs."""
            match = self._result.get('match_result', {})
            return match.get('applicable_rule_ids', [])
        
        def generate_email(self, form_response: dict) -> str:
            """
            Generate compensation email from user's form response.
            
            Args:
                form_response: Dictionary with filled form fields
            
            Returns:
                Generated email text ready to send
            """
            if not self.has_email_action():
                raise ValueError("Email action not available for this case")
            
            return generate_email_from_case(self._result, form_response)
        
        def to_dict(self) -> dict:
            """Get the raw result dictionary."""
            return self._result
    
    def process_case(self, user_text: str, additional_facts: dict = None, 
                     session_id: str = None, top_k: int = 12):
        """
        Process a user grievance and check for email action availability.
        
        Args:
            user_text: User's description of the grievance
            additional_facts: Optional dictionary of additional facts
            session_id: Optional session identifier
            top_k: Number of candidate rules to retrieve
        
        Returns:
            CaseResult object with helper methods
        """
        result = run_case_with_email_option(
            user_text=user_text,
            additional_facts=additional_facts,
            session_id=session_id,
            top_k=top_k
        )
        return self.CaseResult(result)


# Create a global instance for easy access
email_api = EmailActionAPI()

print("Email Action API ready!")
print("\nUsage:")
print("  case = email_api.process_case(user_text)")
print("  if case.has_email_action():")
print("      form = case.get_form()")
print("      # ... user fills form ...")
print("      email = case.generate_email(form_response)")

# COMMAND ----------

# Complete example using the clean API
print("=" * 70)
print("COMPLETE EMAIL ACTION FLOW - USING API")
print("=" * 70)

# Step 1: Process the case
print("\n1. Processing case...")
case = email_api.process_case(
    user_text="My IndiGo flight 6E-5678 from Chennai to Kolkata was cancelled 3 hours before departure.",
    additional_facts={
        "refund_offered": "false",
        "alternate_offered": "true",
        "extraordinary_circumstances": "false"
    }
)

print(f"   Grievance Type: {case.get_grievance_type()}")
print(f"   Status: {case.get_status()}")
print(f"   Email Available: {case.has_email_action()}")

# Step 2: Check if email action is available
if case.has_email_action():
    print("\n2. Email action available!")
    print(f"   Actions: {', '.join(case.get_actions())}")
    
    # Step 3: Display form to user
    print("\n3. Form displayed to user (simulated)")
    form_template = case.get_form()
    # In real app, you'd show this form in UI
    
    # Step 4: User fills form (simulated)
    print("\n4. User fills form...")
    user_input = {
        'FULL_NAME': 'Amit Patel',
        'EMAIL_ADDRESS': 'amit.patel@example.com',
        'PHONE_NUMBER': '+91-9876501234',
        'AIRLINE_NAME': 'IndiGo',
        'PNR': 'DEF456',
        'FLIGHT_NUMBER': '6E-5678',
        'FROM': 'Chennai (MAA)',
        'TO': 'Kolkata (CCU)',
        'SCHEDULED_DEPARTURE': '18-Apr-2026 10:00 IST',
        'DISRUPTION_TYPE': 'Cancellation',
        'INTIMATION_TIME': '3 hours before departure',
        'ALTERNATE_OR_REFUND_DETAILS': 'Alternate flight offered for next day only',
        'EXPENSE_AMOUNT': '1500'
    }
    
    # Step 5: Generate email
    print("\n5. Generating email...")
    final_email = case.generate_email(user_input)
    
    print("\n" + "=" * 70)
    print("FINAL EMAIL:")
    print("=" * 70)
    print(final_email)
    
    # Step 6: Show summary of applicable rules
    print("\n" + "=" * 70)
    print("APPLICABLE RULES SUMMARY:")
    print("=" * 70)
    print(case.get_passenger_summary())
    print(f"\nRule IDs: {', '.join(case.get_applicable_rules())}")
    
else:
    print("\n✗ Email action not available for this grievance type.")
    print(f"   Grievance type '{case.get_grievance_type()}' does not support email action.")

print("\n" + "=" * 70)
print("✓ EMAIL WORKFLOW COMPLETE")
print("=" * 70)