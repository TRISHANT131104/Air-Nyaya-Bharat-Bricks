"""
AirNyaya - Intelligent Agent System
====================================
Conversational AI agent for DGCA passenger rights using Groq API
"""

import os
import json
import logging
from typing import List, Dict, Optional, Tuple
from pdf_context_loader import load_pdf_context, get_full_content

logger = logging.getLogger(__name__)

# ----------------------------
# GROQ API CONFIGURATION
# ----------------------------

try:
    from groq import Groq
    
    # Groq API Configuration
    os.environ["GROQ_API_KEY"] = "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"
    MODEL_NAME = "llama-3.3-70b-versatile"  # Fast Groq model
    
    # Initialize Groq client
    client = Groq()
    
    logger.info(f"✓ Using Groq API with model: {MODEL_NAME}")
    AI_AVAILABLE = True
    
except Exception as e:
    logger.error(f"Failed to initialize Groq API: {e}")
    AI_AVAILABLE = False
    client = None

# ----------------------------
# SYSTEM PROMPT - GRIEVANCE CLASSIFICATION FOCUSED
# ----------------------------

SYSTEM_PROMPT = """You are AirNyaya AI Assistant - a specialized AI for DGCA passenger rights in India.

YOUR PRIMARY JOB: Identify which of 4 grievance types the user is experiencing.

THE 4 GRIEVANCE TYPES:
1. **cancellation** - Flight was cancelled/stopped before departure
2. **delay** - Flight is delayed but will eventually operate
3. **denied_boarding** - Valid passenger refused boarding (overbooking, etc.)
4. **downgrade** - Involuntarily moved to lower class (business → economy)

RESPONSE RULES:

**When user mentions a flight issue** (any problem with their flight):
- Analyze what happened to identify the grievance type
- Respond with ONLY ONE WORD: the grievance type keyword
- Valid responses: "cancellation" OR "delay" OR "denied_boarding" OR "downgrade"
- Do NOT add explanation, punctuation, emoji, or any other text
- If unclear between two types, pick the most likely one

**When user greets** (hi, hello, hey, namaste):
- Respond warmly and naturally
- Introduce yourself as AirNyaya, DGCA flight rights assistant
- Ask how you can help with flight-related issues
- Do NOT assume any problems

**When user asks general questions** (weather, news, other topics):
- Answer briefly if you know
- If you don't know, say so honestly
- Mention you specialize in flight rights
- Never invent information

**When presenting DGCA rules output**:
- Format with clear sections using emojis:
  📋 Your Rights Summary
  💰 Compensation & Benefits (₹ amounts)
  🎯 Next Steps (numbered actions)
  ⚠️ Important Notes
- Use simple, empathetic language
- Make it actionable

CLASSIFICATION EXAMPLES:
- "Flight cancelled" → cancellation
- "6 hour delay" → delay  
- "Couldn't board, overbooked" → denied_boarding
- "Put in economy instead of business" → downgrade
- "Flight didn't happen" → cancellation
- "Still waiting at airport" → delay
- "They refused to let me on" → denied_boarding

Remember: For flight issues, respond with ONLY the keyword. Nothing else."""

# ----------------------------
# EXAMPLE CONVERSATIONS - MINIMAL & FLEXIBLE
# ----------------------------

EXAMPLE_CONVERSATIONS = [
    {
        "user": "Hi there",
        "assistant": "Hello! 👋 I'm AirNyaya, your DGCA flight rights assistant. How can I help you today?"
    },
    {
        "user": "My flight from Delhi to Mumbai got cancelled yesterday",
        "assistant": "cancellation"
    },
    {
        "user": "The plane has been delayed for 4 hours now",
        "assistant": "delay"
    },
    {
        "user": "They wouldn't let me board even though I had a valid ticket",
        "assistant": "denied_boarding"
    },
    {
        "user": "I paid for business class but was put in economy",
        "assistant": "downgrade"
    },
    {
        "user": "IndiGo cancelled my flight without notice",
        "assistant": "cancellation"
    },
    {
        "user": "My flight has been waiting on the tarmac for 3 hours",
        "assistant": "delay"
    },
    {
        "user": "The flight was overbooked and I couldn't board",
        "assistant": "denied_boarding"
    },
    {
        "user": "They downgraded me from first class to economy",
        "assistant": "downgrade"
    }
]

# ----------------------------
# AIRSEWA COMPLAINT REQUIREMENTS
# ----------------------------

AIRSEWA_REQUIREMENTS = {
    "cancellation": {
        "documents": [
            "Copy of cancelled flight ticket/booking confirmation",
            "Cancellation notification from airline (email/SMS)",
            "Boarding pass (if issued before cancellation)",
            "Proof of expenses incurred (hotel, meals, etc.)",
            "Bank statement showing ticket payment"
        ],
        "steps": [
            "Visit https://airsewa.gov.in and create an account or login",
            "Click on 'Lodge Complaint' from the main menu",
            "Select 'Flight Cancellation' as complaint category",
            "Enter flight details: airline, flight number, date, route",
            "Describe the incident and mention DGCA rules applicable to your case",
            "Upload all required documents (max 5 files, 5MB each)",
            "Submit complaint and note your complaint reference number",
            "Track status regularly - airline must respond within 30 days"
        ]
    },
    "delay": {
        "documents": [
            "Copy of flight ticket/booking confirmation",
            "Boarding pass",
            "Delay notification from airline (email/SMS/display board photo)",
            "Proof of actual departure/arrival time (photo of flight info display)",
            "Receipts for meals/refreshments if not provided",
            "Proof of expenses for extended delay (hotel if overnight)"
        ],
        "steps": [
            "Visit https://airsewa.gov.in and create an account or login",
            "Click on 'Lodge Complaint' from the main menu",
            "Select 'Flight Delay' as complaint category",
            "Enter flight details: airline, flight number, scheduled vs actual time",
            "Specify exact delay duration and mention DGCA compensation rules",
            "Upload supporting documents showing delay and expenses",
            "Submit complaint and save the reference number",
            "Check status updates - expect airline response within 30 days"
        ]
    },
    "denied_boarding": {
        "documents": [
            "Copy of confirmed flight ticket/booking confirmation",
            "Payment receipt showing ticket is fully paid",
            "Denied boarding documentation from airline (if provided)",
            "Boarding pass of alternative flight (if rebooked)",
            "Witness statements (other passengers, if available)",
            "Photos/videos of the incident (if taken)",
            "Communication with airline staff (emails/messages)"
        ],
        "steps": [
            "Visit https://airsewa.gov.in and create an account or login",
            "Click on 'Lodge Complaint' from the main menu",
            "Select 'Denied Boarding' as complaint category",
            "Provide complete flight details and PNR number",
            "Explain why you were denied boarding and state DGCA compensation rights",
            "Upload all supporting documents including booking confirmation",
            "Submit and record your complaint reference number",
            "Monitor complaint status - airline must respond within 30 days"
        ]
    },
    "downgrade": {
        "documents": [
            "Original ticket showing higher class booking",
            "Boarding pass showing lower class assignment",
            "Payment receipt showing fare paid for higher class",
            "Downgrade notification/documentation from airline",
            "Seat assignment records (if available)",
            "Email/SMS communication about the downgrade"
        ],
        "steps": [
            "Visit https://airsewa.gov.in and create an account or login",
            "Click on 'Lodge Complaint' from the main menu",
            "Select 'Class Downgrade' as complaint category",
            "Enter flight details and specify original vs assigned class",
            "Mention DGCA refund rules for involuntary downgrade",
            "Upload ticket, boarding pass, and payment proof",
            "Submit complaint and save your reference number",
            "Track regularly - airline has 30 days to respond and process refund"
        ]
    }
}

# ----------------------------
# AGENT FUNCTIONS
# ----------------------------

def format_messages_for_api(messages: List[Dict]) -> List[Dict]:
    """Format conversation history for Groq API"""
    formatted = []
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        if role in ('user', 'assistant'):
            formatted.append({"role": role, "content": content})
    return formatted

def call_groq_api(messages: List[Dict]) -> str:
    """Call Groq API using official SDK"""
    try:
        if not AI_AVAILABLE or not client:
            raise Exception("Groq API client not available")
        
        # Build messages: system prompt + examples + conversation
        all_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # Add examples for context
        for example in EXAMPLE_CONVERSATIONS:
            all_messages.append({"role": "user", "content": example["user"]})
            all_messages.append({"role": "assistant", "content": example["assistant"]})
        
        # Add actual conversation
        all_messages.extend(format_messages_for_api(messages))
        
        logger.info(f"[GROQ] Calling {MODEL_NAME} with {len(all_messages)} messages")
        
        # Call Groq API
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=all_messages,
            temperature=0.3,  # Lower temperature for more consistent classification
            max_completion_tokens=1024,
            top_p=1,
            stream=False
        )
        
        # Extract response text
        response_text = completion.choices[0].message.content
        logger.info(f"[GROQ] Received response: {len(response_text)} characters")
        return response_text
        
    except Exception as e:
        logger.error(f"Groq API error: {e}", exc_info=True)
        raise

def generate_agent_response(conversation_history: List[Dict]) -> str:
    """Generate AI agent response"""
    logger.info(f"[AGENT] Generating response with {len(conversation_history)} messages")
    
    if not AI_AVAILABLE:
        return "AI agent is not configured. Please check Groq API setup."
    
    try:
        response = call_groq_api(conversation_history)
        logger.info(f"[AGENT] Generated response: {len(response)} characters")
        return response
    except Exception as e:
        logger.error(f"[AGENT] Error: {e}", exc_info=True)
        return f"I apologize, but I encountered an error: {str(e)}\n\nPlease try again."

def classify_grievance(user_message: str) -> Optional[str]:
    """
    Classify user message into one of 4 grievance types.
    Returns: 'cancellation', 'delay', 'denied_boarding', 'downgrade', or None
    """
    logger.info(f"[CLASSIFY] Classifying user message: '{user_message[:100]}'")
    
    try:
        conversation = [{"role": "user", "content": user_message}]
        response = call_groq_api(conversation)
        
        # Clean and normalize response
        response_clean = response.strip().lower()
        
        # Extract grievance type
        valid_types = ['cancellation', 'delay', 'denied_boarding', 'downgrade']
        
        for gtype in valid_types:
            if gtype in response_clean:
                logger.info(f"[CLASSIFY] ✓ Detected grievance: {gtype}")
                return gtype
        
        logger.info(f"[CLASSIFY] ✗ No grievance detected, response: {response}")
        return None
        
    except Exception as e:
        logger.error(f"[CLASSIFY] Error: {e}", exc_info=True)
        return None

def get_airsewa_guidance(grievance_type: str) -> str:
    """Get AirSewa complaint filing guidance for specific grievance type"""
    if grievance_type not in AIRSEWA_REQUIREMENTS:
        return ""
    
    info = AIRSEWA_REQUIREMENTS[grievance_type]
    
    output = "\n\n---\n\n"
    output += "## 📝 How to File a Complaint on AirSewa\n\n"
    output += "If the airline doesn't resolve your issue, you can escalate to AirSewa (DGCA's official portal):\n\n"
    
    output += "### 📄 Required Documents:\n"
    for idx, doc in enumerate(info["documents"], 1):
        output += f"{idx}. {doc}\n"
    
    output += "\n### 🎯 Step-by-Step Process:\n"
    for idx, step in enumerate(info["steps"], 1):
        output += f"{idx}. {step}\n"
    
    output += "\n**⚠️ Important:** Keep all documents organized and file the complaint within the timeframe mentioned in DGCA rules for best results.\n"
    
    return output

def draft_complaint_email(grievance_type: str, field_values: dict, rules: List[Dict]) -> str:
    """Generate a professional complaint email draft using AI"""
    logger.info(f"[DRAFT] Generating email for {grievance_type}")
    
    if not AI_AVAILABLE:
        return "AI service unavailable. Please draft your complaint manually using the DGCA rules provided."
    
    try:
        # Prepare context for AI
        rules_text = ""
        for idx, rule in enumerate(rules[:3], 1):  # Top 3 rules
            rules_text += f"{idx}. {rule.get('title', 'N/A')}: {rule.get('passenger_gets_text', 'N/A')}\n"
        
        prompt = f"""Draft a professional complaint email to an airline for a {grievance_type} case.

Flight Details:
{json.dumps(field_values, indent=2)}

Applicable DGCA Rules:
{rules_text}

Write a formal, professional complaint email with:
- Subject line
- Formal greeting
- Clear description of the issue
- Reference to DGCA regulations
- Specific compensation/facilities requested
- Professional closing
- Mention of escalation to AirSewa if not resolved

Keep it concise, professional, and assertive but polite."""

        email_request = [{"role": "user", "content": prompt}]
        draft_email = call_groq_api(email_request)
        
        logger.info(f"[DRAFT] Generated email draft: {len(draft_email)} characters")
        return draft_email
        
    except Exception as e:
        logger.error(f"[DRAFT] Error: {e}")
        return "Error generating email. Please draft your complaint manually using the DGCA rules provided above."

def format_rules_for_display(rules: List[Dict], grievance_type: str, field_values: dict) -> str:
    """Format DGCA rules into human-friendly display with AI enhancement"""
    if not rules:
        return "No applicable DGCA rules found for your specific situation."
    
    logger.info(f"[AGENT] Formatting {len(rules)} rules for display")
    
    # Prepare rules summary for AI to format nicely
    rules_summary = {
        "grievance_type": grievance_type,
        "field_values": field_values,
        "matched_rules": []
    }
    
    for rule in rules:
        rule_info = {
            "rule_id": rule.get('rule_id', 'N/A'),
            "title": rule.get('title', 'N/A'),
            "match_kind": rule.get('match_kind', 'unknown'),
            "passenger_gets": rule.get('passenger_gets_text', 'Not specified'),
            "source": rule.get('source_para', 'N/A')
        }
        
        # Parse actions if available
        actions_json = rule.get('actions_json', '{}')
        if isinstance(actions_json, str):
            try:
                rule_info["actions"] = json.loads(actions_json)
            except:
                rule_info["actions"] = {}
        else:
            rule_info["actions"] = actions_json or {}
        
        rules_summary["matched_rules"].append(rule_info)
    
    # Use AI to format this beautifully
    if AI_AVAILABLE:
        try:
            format_request = [{
                "role": "user",
                "content": f"""Based on these DGCA rules, create a clear, human-friendly summary for the passenger:

{json.dumps(rules_summary, indent=2)}

Format your response with these sections:
📋 **Your Rights Summary** - Brief overview
💰 **Compensation & Benefits** - What they're entitled to (amounts in ₹)
🎯 **Next Steps** - What to do now (numbered list)
⚠️ **Important Notes** - Key things to remember

Be warm, empathetic, and use simple language. Make it easy to understand and act upon."""
            }]
            
            formatted_response = call_groq_api(format_request)
            
            # Add AirSewa guidance
            if grievance_type:
                formatted_response += get_airsewa_guidance(grievance_type)
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"[AGENT] Error formatting with AI: {e}")
            # Fall through to basic formatting
    
    # Fallback basic formatting
    output = "### 📋 Your Rights\n\n"
    
    exact_matches = [r for r in rules if r.get('match_kind') == 'exact']
    if exact_matches:
        output += "**✅ Applicable Rules:**\n\n"
        for idx, rule in enumerate(exact_matches, 1):
            output += f"**{idx}. {rule.get('title', 'N/A')}**\n"
            output += f"   {rule.get('passenger_gets_text', 'Not specified')}\n\n"
    
    output += "\n### 🎯 Next Steps:\n"
    output += "1. Approach the airline counter with your ticket and documents\n"
    output += "2. Request the compensation/facilities you're entitled to\n"
    output += "3. Keep records of all communications\n"
    output += "4. If denied, file a complaint on AirSewa: https://airsewa.gov.in\n"
    
    # Add AirSewa guidance
    if grievance_type:
        output += get_airsewa_guidance(grievance_type)
    
    return output

def summarize_rules(rules: List[Dict]) -> str:
    """Generate simple summary of DGCA rules (legacy function)"""
    if not rules:
        return "No applicable rules found."
    
    return format_rules_for_display(rules, None, {})

def enhance_response_with_ai_summary(response_text: str, rules: List[Dict], 
                                     conversation_history: List[Dict]) -> str:
    """Enhance response with AI summary (deprecated - use format_rules_for_display)"""
    return format_rules_for_display(rules, None, {})

def process_with_agent(user_message: str, conversation_history: List[Dict], 
                       grievance_type: Optional[str] = None,
                       rules: Optional[List[Dict]] = None) -> Tuple[str, Optional[str]]:
    """Main agent interface"""
    logger.info(f"[AGENT] Processing: type={grievance_type}, rules={len(rules) if rules else 0}")
    
    try:
        if rules:
            logger.info("[AGENT] Formatting rules for display")
            formatted_response = format_rules_for_display(rules, grievance_type, {})
            return formatted_response, None
        else:
            logger.info("[AGENT] Generating conversational response")
            response = generate_agent_response(conversation_history)
            return response, None
    except Exception as e:
        logger.error(f"[AGENT] Error: {e}", exc_info=True)
        return "I apologize for the technical difficulty. Let me help you manually...", None

# ----------------------------
# TESTING
# ----------------------------

if __name__ == "__main__":
    print("=" * 80)
    print("AirNyaya Agent System - Test Mode (Groq API)")
    print("=" * 80)
    
    # Test 1: Greeting
    print("\n🧪 Test 1: Greeting")
    test_greeting = [{"role": "user", "content": "Hi"}]
    if AI_AVAILABLE:
        try:
            response = generate_agent_response(test_greeting)
            print(f"Response: {response}\n")
        except Exception as e:
            print(f"Error: {e}\n")
    
    # Test 2: Grievance Classification
    print("\n🧪 Test 2: Grievance Classification")
    test_cases = [
        "My flight from Delhi to Mumbai got cancelled",
        "The flight is delayed by 6 hours",
        "They wouldn't let me board even with a confirmed ticket",
        "I paid for business class but was seated in economy"
    ]
    
    for test in test_cases:
        print(f"\nInput: {test}")
        grievance = classify_grievance(test)
        print(f"Classification: {grievance}")
    
    # Test 3: Draft Email
    print("\n🧪 Test 3: Draft Complaint Email")
    test_field_values = {
        "flight_number": "6E-2045",
        "airline": "IndiGo",
        "route": "Delhi to Mumbai"
    }
    test_rules = [
        {"title": "Cancellation Compensation", "passenger_gets_text": "Full refund + ₹10,000"}
    ]
    if AI_AVAILABLE:
        try:
            email = draft_complaint_email("cancellation", test_field_values, test_rules)
            print(f"Draft Email:\n{email}\n")
        except Exception as e:
            print(f"Error: {e}\n")
    
    print("=" * 80)
