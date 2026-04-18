import os
import json
import uuid
from flask import Flask, request, jsonify, render_template_string, session
from databricks import sql
from databricks.sdk.core import Config

# Import agent for conversational responses
try:
    from agent import generate_agent_response
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False
    generate_agent_response = None

# ----------------------------
# CONFIG
# ----------------------------
CATALOG = "airnyaya"
SCHEMA = "mvp"
REQUIRED_FIELDS_TABLE = f"{CATALOG}.{SCHEMA}.required_fields_by_grievance"
RULES_TABLE = f"{CATALOG}.{SCHEMA}.rules_all"
CASE_RUNS_TABLE = f"{CATALOG}.{SCHEMA}.case_runs"

# Set this in your Databricks App env or secret
WAREHOUSE_HTTP_PATH = "/sql/1.0/warehouses/da906c4474a55de9"


cfg = Config()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "airnyaya-secret-" + uuid.uuid4().hex)

# ----------------------------
# FLIGHT QUERY DETECTION
# ----------------------------
FLIGHT_KEYWORDS = [
    'flight', 'flights', 'airline', 'airlines', 'airport',
    'cancellation', 'cancelled', 'cancel', 'canceling',
    'delay', 'delayed', 'delaying',
    'boarding', 'boarded', 'denied boarding',
    'downgrade', 'downgraded', 'class change',
    'refund', 'compensation', 'ticket',
    'indigo', 'air india', 'spicejet', 'vistara', 'go first', 'akasa'
]

def is_flight_related(message: str) -> bool:
    """
    Detect if a message is about flight issues.
    Returns True if message contains flight-related keywords.
    """
    message_lower = message.lower()
    
    # Check for flight keywords
    for keyword in FLIGHT_KEYWORDS:
        if keyword in message_lower:
            return True
    
    # Common greetings and general queries (not flight-related)
    greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening']
    simple_greetings = [g for g in greetings if message_lower.strip() in [g, g + '!', g + '.']]
    
    if simple_greetings:
        return False
    
    # If message is very short and doesn't contain flight keywords, likely not flight-related
    if len(message.split()) <= 3 and not any(kw in message_lower for kw in FLIGHT_KEYWORDS[:10]):
        return False
    
    return False  # Default to not flight-related to avoid false positives

# ----------------------------
# HTML - ENHANCED PROFESSIONAL INTERFACE
# ----------------------------