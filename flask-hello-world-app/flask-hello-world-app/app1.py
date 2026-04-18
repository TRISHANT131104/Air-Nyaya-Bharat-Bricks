"""
AirNyaya - Conversational Rule Matching System with AI Agent
=============================================================
Combines deterministic DGCA rule matching with AI-powered conversational agent
"""

import os
import json
import uuid
import re
import logging
from datetime import datetime
from string import Template
from flask import Flask, request, jsonify, render_template, session
from databricks import sql
from databricks.sdk import WorkspaceClient
from agent import (
    generate_agent_response, 
    summarize_rules, 
    process_with_agent, 
    format_rules_for_display,
    classify_grievance,  # AI-based grievance classification
    draft_complaint_email,  # Email draft generation
    get_airsewa_guidance  # AirSewa filing guidance
)

# ----------------------------
# LOGGING SETUP
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ----------------------------
# CONFIG
# ----------------------------
CATALOG = "airnyaya"
SCHEMA = "mvp"
REQUIRED_FIELDS_TABLE = f"{CATALOG}.{SCHEMA}.required_fields_by_grievance_enriched"
EVAL_RULES_FUNCTION = f"{CATALOG}.{SCHEMA}.eval_rules_det"
WAREHOUSE_HTTP_PATH = "/sql/1.0/warehouses/da906c4474a55de9"

# Initialize Workspace Client for token-based auth
w = WorkspaceClient()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "airnyaya-secret-" + uuid.uuid4().hex)

logger.info("=" * 80)
logger.info("AirNyaya Application Starting with AI Agent")
logger.info(f"Catalog: {CATALOG}, Schema: {SCHEMA}")
logger.info(f"Warehouse: {WAREHOUSE_HTTP_PATH}")
logger.info("=" * 80)

# ----------------------------
# EMAIL TEMPLATES
# ----------------------------

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

FORM_TYPE_2_FIELDS = [
    {
        "field_name": "FULL_NAME",
        "label": "Passenger Name",
        "type": "text",
        "required": True,
        "placeholder": "Enter your full name"
    },
    {
        "field_name": "EMAIL_ADDRESS",
        "label": "Email Address",
        "type": "email",
        "required": True,
        "placeholder": "your.email@example.com"
    },
    {
        "field_name": "PHONE_NUMBER",
        "label": "Phone Number",
        "type": "tel",
        "required": True,
        "placeholder": "+91-XXXXXXXXXX"
    },
    {
        "field_name": "AIRLINE_NAME",
        "label": "Airline Name",
        "type": "text",
        "required": True,
        "placeholder": "e.g., IndiGo, Air India"
    },
    {
        "field_name": "PNR",
        "label": "PNR Number",
        "type": "text",
        "required": True,
        "placeholder": "6-character PNR"
    },
    {
        "field_name": "FLIGHT_NUMBER",
        "label": "Flight Number",
        "type": "text",
        "required": True,
        "placeholder": "e.g., 6E 123"
    },
    {
        "field_name": "FROM",
        "label": "From (Origin Airport)",
        "type": "text",
        "required": True,
        "placeholder": "e.g., Delhi (DEL)"
    },
    {
        "field_name": "TO",
        "label": "To (Destination Airport)",
        "type": "text",
        "required": True,
        "placeholder": "e.g., Mumbai (BOM)"
    },
    {
        "field_name": "SCHEDULED_DEPARTURE",
        "label": "Scheduled Departure Date & Time",
        "type": "datetime-local",
        "required": True,
        "placeholder": ""
    },
    {
        "field_name": "DISRUPTION_TYPE",
        "label": "What happened?",
        "type": "select",
        "required": True,
        "options": [
            "Cancellation",
            "Delay",
            "Denied Boarding",
            "Downgrade",
            "Baggage Issue",
            "Other"
        ]
    },
    {
        "field_name": "INTIMATION_TIME",
        "label": "When were you informed?",
        "type": "text",
        "required": True,
        "placeholder": "e.g., 5 hours before departure"
    },
    {
        "field_name": "ALTERNATE_OR_REFUND_DETAILS",
        "label": "Did airline offer alternate flight/refund?",
        "type": "textarea",
        "required": False,
        "placeholder": "Describe what was offered (if any)"
    },
    {
        "field_name": "EXPENSE_AMOUNT",
        "label": "Extra expenses incurred (optional)",
        "type": "text",
        "required": False,
        "placeholder": "Enter amount in ₹ or NA"
    }
]

# ----------------------------
# DATABASE HELPERS
# ----------------------------

def get_sql_connection():
    """Get Databricks SQL connection using WorkspaceClient token"""
    logger.debug("Creating SQL connection...")
    try:
        # Get credentials from WorkspaceClient
        host = "dbc-8e1c9d06-1344.cloud.databricks.com"
        token = "dapi0a06157808f556277fbe28a77f3e9fe4"
        
        if not host or not token:
            raise ValueError("Could not get host or token from WorkspaceClient")
        
        # Remove https:// prefix if present
        if host.startswith('https://'):
            host = host[8:]
        if host.startswith('http://'):
            host = host[7:]
        
        conn = sql.connect(
            server_hostname=host,
            http_path=WAREHOUSE_HTTP_PATH,
            access_token=token
        )
        logger.debug("SQL connection established successfully")
        return conn
    except Exception as e:
        logger.error(f"Failed to create SQL connection: {e}")
        raise

def sql_rows(query: str):
    """Execute SQL and return rows as list of dicts"""
    logger.info(f"Executing SQL query: {query[:200]}...")
    try:
        with get_sql_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                columns = [desc[0] for desc in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                logger.info(f"Query returned {len(rows)} row(s)")
                return rows
    except Exception as e:
        logger.error(f"SQL query failed: {e}")
        logger.error(f"Query was: {query}")
        raise

# ----------------------------
# EMAIL ACTION HELPERS
# ----------------------------

def check_email_action_applicable(grievance_type: str) -> bool:
    """Check if email action is available for this grievance type"""
    return grievance_type.lower() in ['cancellation', 'denied_boarding']

def parse_form_type_2_response(form_response: dict) -> dict:
    """
    Parse Form Type 2 user responses and prepare data for email template.
    """
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
    
    # Calculate notice window
    notice_window = intimation
    
    # Determine compensation types based on disruption
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

def generate_compensation_email(form_data: dict) -> str:
    """Generate DGCA compensation email using the template"""
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

# ----------------------------
# FIELD MANAGEMENT
# ----------------------------

def get_required_fields(grievance_type: str):
    """Get required fields for a grievance type"""
    logger.info(f"[FIELDS] Fetching required fields for grievance_type: {grievance_type}")
    query = f"""
        SELECT field_name, field_description, field_order
        FROM {REQUIRED_FIELDS_TABLE}
        WHERE grievance_type = '{grievance_type}'
        ORDER BY field_order
    """
    fields = sql_rows(query)
    logger.info(f"[FIELDS] Found {len(fields)} required fields: {[f['field_name'] for f in fields]}")
    return fields

def detect_field_type(field_name: str, field_description: str) -> str:
    """
    Auto-detect field type based on name and description.
    Returns: 'boolean', 'number', 'datetime', or 'text'
    """
    field_name_lower = field_name.lower()
    description_lower = field_description.lower()
    
    # Boolean detection
    boolean_indicators = ['_confirmed', 'is_', 'has_', 'was_']
    if any(ind in field_name_lower for ind in boolean_indicators):
        return 'boolean'
    if 'yes/no' in description_lower or 'true/false' in description_lower:
        return 'boolean'
    
    # Number detection
    number_indicators = ['_hours', '_km', '_minutes', 'distance', 'delay', 'amount', 'fare', 'price']
    if any(ind in field_name_lower for ind in number_indicators):
        return 'number'
    if 'number' in description_lower or 'amount' in description_lower:
        return 'number'
    
    # DateTime detection
    datetime_indicators = ['_date', '_time', 'datetime', 'timestamp']
    if any(ind in field_name_lower for ind in datetime_indicators):
        return 'datetime'
    if 'date' in description_lower or 'time' in description_lower:
        return 'datetime'
    
    # Default to text
    return 'text'

# ----------------------------
# RULE EVALUATION
# ----------------------------

def eval_rules(grievance_type: str, field_values: dict):
    """Call eval_rules_det function with field values"""
    logger.info(f"[EVAL] Evaluating rules for {grievance_type}")
    logger.info(f"[EVAL] Field values: {json.dumps(field_values, indent=2)}")
    
    values_json = json.dumps(field_values, ensure_ascii=False)
    values_json_escaped = values_json.replace("'", "''")
    
    query = f"""
        SELECT *
        FROM {EVAL_RULES_FUNCTION}(
            '{grievance_type}',
            '{values_json_escaped}'
        )
        ORDER BY match_kind, source_para, rule_id
    """
    
    logger.info(f"[EVAL] Calling {EVAL_RULES_FUNCTION}...")
    rules = sql_rows(query)
    logger.info(f"[EVAL] ✓ Found {len(rules)} matching rule(s)")
    
    if rules:
        for idx, rule in enumerate(rules):
            logger.info(f"[EVAL] Rule {idx+1}: ID={rule.get('rule_id')}, Match={rule.get('match_kind')}")
    
    return rules

# ----------------------------
# SESSION MANAGEMENT
# ----------------------------

def init_session():
    """Initialize session state"""
    if 'conversation_id' not in session:
        session['conversation_id'] = str(uuid.uuid4())
        logger.info(f"[SESSION] New conversation started: {session['conversation_id']}")
    
    if 'messages' not in session:
        session['messages'] = []
    if 'state' not in session:
        session['state'] = 'initial'
    if 'grievance_type' not in session:
        session['grievance_type'] = None
    if 'required_fields' not in session:
        session['required_fields'] = []
    if 'field_values' not in session:
        session['field_values'] = {}
    if 'matched_rules' not in session:
        session['matched_rules'] = []

def add_message(role: str, content: str, metadata: dict = None):
    """Add message to conversation"""
    message = {
        'role': role,
        'content': content,
        'timestamp': datetime.now().isoformat(),
        'metadata': metadata or {}
    }
    session['messages'].append(message)
    session.modified = True
    logger.info(f"[MESSAGE] {role.upper()}: {content[:100]}{'...' if len(content) > 100 else ''}")

def get_conversation_for_agent():
    """Get conversation history formatted for AI agent"""
    return [
        {"role": msg['role'], "content": msg['content']}
        for msg in session.get('messages', [])
    ]

# ----------------------------
# CONVERSATION LOGIC WITH AI AGENT
# ----------------------------

def process_user_message(user_text: str) -> dict:
    """Process user message with AI agent integration"""
    logger.info("=" * 80)
    logger.info(f"[PROCESS] Processing user message: '{user_text}'")
    logger.info("=" * 80)
    
    init_session()
    add_message('user', user_text)
    
    state = session['state']
    logger.info(f"[STATE] Current state: {state}")
    
    if state == 'initial':
        logger.info("[STATE] → Handling INITIAL state with AI agent")
        
        # Use AI to classify grievance
        grievance_type = classify_grievance(user_text)
        
        if grievance_type:
            logger.info(f"[STATE] AI classified grievance as: {grievance_type}")
            
            session['grievance_type'] = grievance_type
            session['required_fields'] = get_required_fields(grievance_type)
            
            # Enrich fields with type detection
            for field in session['required_fields']:
                field['field_type'] = detect_field_type(
                    field['field_name'], 
                    field['field_description']
                )
            
            session['state'] = 'awaiting_fields'
            session.modified = True
            
            logger.info(f"[STATE] Transitioned to: awaiting_fields")
            logger.info(f"[STATE] Required fields count: {len(session['required_fields'])}")
            
            # Generate empathetic response
            grievance_labels = {
                'cancellation': 'Flight Cancellation',
                'delay': 'Flight Delay',
                'denied_boarding': 'Denied Boarding',
                'downgrade': 'Class Downgrade'
            }
            
            response_text = f"I understand you're facing a **{grievance_labels[grievance_type]}** situation.\n\nPlease provide the following information to determine your DGCA rights:"
            
            add_message('assistant', response_text, {
                'show_fields': True, 
                'fields': session['required_fields']
            })
            
            return {
                'response': response_text, 
                'rules': None, 
                'show_fields': True, 
                'fields': session['required_fields']
            }
        
        else:
            logger.info("[STATE] No grievance detected, using AI agent for conversational response")
            
            try:
                # Use AI agent for conversational response
                conversation_history = get_conversation_for_agent()
                response_text = generate_agent_response(conversation_history)
                
            except Exception as e:
                logger.error(f"[AGENT] Error using AI agent: {e}")
                # Fallback response
                response_text = """I'm here to help you understand your passenger rights under DGCA regulations.

I can assist with:
✈️ **Flight Cancellations** - If your flight was cancelled
⏰ **Flight Delays** - If your flight was significantly delayed
🚫 **Denied Boarding** - If you were not allowed to board despite having a ticket
⬇️ **Class Downgrade** - If you were moved to a lower class

Please tell me what happened with your flight."""
            
            add_message('assistant', response_text)
            return {'response': response_text, 'rules': None}
    
    elif state == 'awaiting_fields':
        logger.info("[STATE] → Handling AWAITING_FIELDS state")
        
        # Parse the user's field values from form submission
        field_values = {}
        
        # Try JSON parsing first (if frontend sends structured data)
        try:
            field_values = json.loads(user_text)
            logger.info(f"[PARSE] Parsed JSON field values: {len(field_values)} fields")
        except:
            # Fallback: parse "field_name: value" format
            lines = user_text.split('\n')
            
            for line in lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    field_name = parts[0].strip()
                    value = parts[1].strip()
                    
                    # Check if this field exists in required_fields
                    for field in session['required_fields']:
                        if field['field_name'] == field_name or field['field_name'].replace('_', ' ').lower() == field_name.lower():
                            field_values[field['field_name']] = value
                            logger.info(f"[PARSE] Extracted: {field['field_name']} = {value}")
                            break
            
            logger.info(f"[PARSE] Parsed {len(field_values)} field values from text")
        
        # Check if we got all required fields
        missing_fields = [f['field_name'] for f in session['required_fields'] if f['field_name'] not in field_values]
        
        if missing_fields:
            logger.warning(f"[PARSE] Missing fields: {missing_fields}")
            response_text = f"I couldn't find values for the following fields: {', '.join(missing_fields)}\n\nPlease provide all required values."
            
            add_message('assistant', response_text)
            return {'response': response_text, 'rules': None}
        
        # Store field values in session
        session['field_values'] = field_values
        session.modified = True
        
        # All fields collected, evaluate rules
        logger.info("[EVAL] All fields collected, evaluating rules...")
        
        try:
            rules = eval_rules(session['grievance_type'], field_values)
            logger.info(f"[EVAL] ✓ Rule evaluation successful: {len(rules)} rules found")
            
            # Store rules in session
            session['matched_rules'] = rules
            session.modified = True
            
            # Check if email action is applicable
            email_action_available = check_email_action_applicable(session['grievance_type'])
            
            # Use AI agent to generate enhanced summary
            try:
                logger.info("[AGENT] Formatting rules with AI for human-friendly display")
                response_text = format_rules_for_display(
                    rules,
                    session['grievance_type'],
                    field_values
                )
                
            except Exception as e:
                logger.error(f"[AGENT] Error using AI agent for summary: {e}")
                # Fallback to basic response
                if rules:
                    response_text = f"✅ **Analysis Complete!** I found **{len(rules)} applicable DGCA rule(s)** for your situation.\n\n"
                    response_text += summarize_rules(rules)
                    response_text += get_airsewa_guidance(session['grievance_type'])
                else:
                    response_text = "I've analyzed your situation, but couldn't find any matching DGCA rules."
            
            # Add action options if email is applicable
            if email_action_available:
                response_text += "\n\n**📧 Next Steps - Choose an Action:**\n"
                response_text += "1. **Send Email to Airline** - Draft a formal complaint email\n"
                response_text += "2. **File on AirSewa** - Submit through official portal\n"
                response_text += "3. **Download Report** - Get a detailed PDF of your rights\n"
            
            session['state'] = 'completed'
            session.modified = True
            
            metadata = {
                'rules': rules,
                'show_email_action': email_action_available
            }
            
            add_message('assistant', response_text, metadata)
            
            return {
                'response': response_text,
                'rules': rules,
                'show_email_action': email_action_available,
                'email_form_fields': FORM_TYPE_2_FIELDS if email_action_available else None
            }
            
        except Exception as e:
            logger.error(f"[EVAL] ✗ Rule evaluation failed: {e}", exc_info=True)
            response_text = f"Sorry, I encountered an error while evaluating the rules: {str(e)}"
            add_message('assistant', response_text)
            return {'response': response_text, 'rules': None}
    
    elif state == 'completed':
        logger.info("[STATE] → Handling COMPLETED state (resetting)")
        session.clear()
        init_session()
        
        # Use AI agent for friendly reset message
        try:
            conversation_history = [{"role": "user", "content": user_text}]
            response_text = generate_agent_response(conversation_history)
        except:
            response_text = "Let's start fresh! What's your flight issue?"
        
        add_message('assistant', response_text)
        return {'response': response_text, 'rules': None}

# ----------------------------
# ROUTES
# ----------------------------

@app.route("/")
def index():
    """Main chat interface"""
    logger.info("[ROUTE] GET / - Loading chat interface")
    init_session()
    return render_template('index.html')

@app.route("/api/chat", methods=["POST"])
def chat():
    """Handle chat messages"""
    logger.info("[ROUTE] POST /api/chat")
    data = request.json
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({'error': 'Empty message'}), 400
    
    try:
        result = process_user_message(user_message)
        return jsonify(result)
    except Exception as e:
        logger.error(f"[ROUTE] ✗ Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route("/api/submit_fields", methods=["POST"])
def submit_fields():
    """Handle form field submission"""
    logger.info("[ROUTE] POST /api/submit_fields")
    data = request.json
    field_values = data.get('fields', {})
    
    if not field_values:
        return jsonify({'error': 'No field values provided'}), 400
    
    try:
        # Convert field values to JSON string format
        field_values_json = json.dumps(field_values)
        result = process_user_message(field_values_json)
        return jsonify(result)
    except Exception as e:
        logger.error(f"[ROUTE] ✗ Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route("/api/get_email_form", methods=["GET"])
def get_email_form():
    """Get email form fields"""
    logger.info("[ROUTE] GET /api/get_email_form")
    
    init_session()
    
    grievance_type = session.get('grievance_type')
    
    if not grievance_type:
        return jsonify({
            'error': 'No active grievance case. Please complete the initial assessment first.'
        }), 400
    
    if not check_email_action_applicable(grievance_type):
        return jsonify({
            'error': f'Email action is not available for {grievance_type} cases.'
        }), 400
    
    return jsonify({
        'success': True,
        'form_fields': FORM_TYPE_2_FIELDS,
        'grievance_type': grievance_type
    })

@app.route("/api/generate_email", methods=["POST"])
def generate_email():
    """Generate compensation email from form data"""
    logger.info("[ROUTE] POST /api/generate_email")
    
    init_session()
    data = request.json
    form_response = data.get('form_data', {})
    
    if not form_response:
        return jsonify({'error': 'No form data provided'}), 400
    
    grievance_type = session.get('grievance_type')
    rules = session.get('matched_rules', [])
    
    if not grievance_type:
        return jsonify({
            'error': 'No active grievance case. Please complete the assessment first.'
        }), 400
    
    if not check_email_action_applicable(grievance_type):
        return jsonify({
            'error': f'Email action is not available for {grievance_type} cases.'
        }), 400
    
    try:
        # Parse form response and generate email
        email_data = parse_form_type_2_response(form_response)
        email_text = generate_compensation_email(email_data)
        
        logger.info(f"[EMAIL] Generated compensation email successfully")
        
        return jsonify({
            'success': True,
            'email_text': email_text,
            'subject': f"Request for Statutory Compensation under DGCA Passenger Charter – PNR {form_response.get('PNR', '')}"
        })
        
    except Exception as e:
        logger.error(f"[ROUTE] ✗ Error generating email: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route("/api/draft_email", methods=["POST"])
def draft_email():
    """Generate draft complaint email (legacy endpoint)"""
    logger.info("[ROUTE] POST /api/draft_email")
    
    init_session()
    
    grievance_type = session.get('grievance_type')
    field_values = session.get('field_values', {})
    rules = session.get('matched_rules', [])
    
    if not grievance_type or not rules:
        return jsonify({
            'error': 'No complaint data available. Please complete the complaint form first.'
        }), 400
    
    try:
        # Generate draft email using AI
        email_draft = draft_complaint_email(grievance_type, field_values, rules)
        
        logger.info(f"[DRAFT] Generated email draft successfully")
        
        return jsonify({
            'success': True,
            'email_draft': email_draft
        })
        
    except Exception as e:
        logger.error(f"[ROUTE] ✗ Error generating draft email: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route("/api/history")
def history():
    """Get conversation history"""
    logger.info("[ROUTE] GET /api/history")
    init_session()
    return jsonify({
        'messages': session.get('messages', []),
        'state': session.get('state'),
        'grievance_type': session.get('grievance_type')
    })

@app.route("/api/reset", methods=["POST"])
def reset():
    """Reset conversation"""
    logger.info("[ROUTE] POST /api/reset")
    session.clear()
    return jsonify({'success': True})

# ----------------------------
# MAIN
# ----------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
