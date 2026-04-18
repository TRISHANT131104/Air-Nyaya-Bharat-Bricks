"""
PDF Context Loader for AirNyaya
================================
Extracts DGCA rules from part2.pdf and provides them as context to the AI agent
"""

import os
import json
import re
from typing import Dict, List, Optional

# Try importing PDF libraries
try:
    import PyPDF2
    PDF_LIBRARY = "PyPDF2"
except ImportError:
    try:
        import pdfplumber
        PDF_LIBRARY = "pdfplumber"
    except ImportError:
        PDF_LIBRARY = None
        print("⚠️  Warning: No PDF library available. Install PyPDF2 or pdfplumber")

# Global cache for PDF content
_pdf_content_cache = None
_pdf_sections_cache = None

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract all text from PDF file
    Tries multiple methods for best results
    """
    if not os.path.exists(pdf_path):
        print(f"❌ PDF file not found: {pdf_path}")
        return ""
    
    text = ""
    
    try:
        if PDF_LIBRARY == "pdfplumber":
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
            print(f"✓ Extracted {len(text)} characters using pdfplumber")
            
        elif PDF_LIBRARY == "PyPDF2":
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
            print(f"✓ Extracted {len(text)} characters using PyPDF2")
        else:
            print("❌ No PDF library available")
            return ""
            
    except Exception as e:
        print(f"❌ Error extracting PDF: {e}")
        return ""
    
    return text

def parse_dgca_rules(text: str) -> Dict[str, Dict]:
    """
    Parse DGCA rules text into structured sections
    Looks for common patterns in DGCA regulations
    """
    sections = {}
    
    # Try to identify major sections
    # Common DGCA section patterns
    section_patterns = [
        r'(?:Section|SECTION|Chapter|CHAPTER)\s+(\d+(?:\.\d+)?)[:\s]*([^\n]+)',
        r'(\d+\.\d+(?:\.\d+)?)[:\.\s]+([A-Z][^\n]+)',
        r'([A-Z][A-Z\s]{10,})',  # All caps headings
    ]
    
    current_section = "General"
    sections[current_section] = {"title": "General Provisions", "content": ""}
    
    lines = text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        # Try to match section headers
        is_header = False
        for pattern in section_patterns:
            match = re.match(pattern, line)
            if match:
                section_id = match.group(1) if len(match.groups()) > 1 else f"section_{len(sections)}"
                section_title = match.group(2) if len(match.groups()) > 1 else match.group(1)
                current_section = section_id
                sections[current_section] = {
                    "title": section_title.strip(),
                    "content": ""
                }
                is_header = True
                break
        
        if not is_header:
            sections[current_section]["content"] += line + "\n"
    
    # Clean up sections
    for section_id in sections:
        sections[section_id]["content"] = sections[section_id]["content"].strip()
    
    print(f"✓ Parsed {len(sections)} sections from DGCA rules")
    return sections

def identify_relevant_context(query: str, sections: Dict[str, Dict], max_length: int = 3000) -> str:
    """
    Identify the most relevant sections of DGCA rules for a query
    Returns concatenated relevant text up to max_length
    """
    query_lower = query.lower()
    
    # Keywords to section mapping
    keyword_priorities = {
        "cancel": ["cancellation", "cancel", "refund"],
        "delay": ["delay", "postpone", "late"],
        "denied": ["denied boarding", "denied", "overbooking", "bumping"],
        "downgrade": ["downgrade", "class", "upgrade"],
        "compensation": ["compensation", "refund", "payment", "reimburse"],
        "refund": ["refund", "money back", "reimbursement"],
        "baggage": ["baggage", "luggage", "bag"],
        "facility": ["facilities", "refreshment", "meal", "hotel", "accommodation"]
    }
    
    # Score each section by relevance
    section_scores = {}
    for section_id, section_data in sections.items():
        score = 0
        content_lower = (section_data["title"] + " " + section_data["content"]).lower()
        
        # Score based on keyword matches
        for keyword_group, keywords in keyword_priorities.items():
            if keyword_group in query_lower:
                for keyword in keywords:
                    score += content_lower.count(keyword) * 10
        
        # Score based on query word matches
        query_words = [w for w in query_lower.split() if len(w) > 3]
        for word in query_words:
            score += content_lower.count(word)
        
        section_scores[section_id] = score
    
    # Select top sections
    sorted_sections = sorted(section_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Build context from top sections
    context = "=== DGCA REGULATIONS CONTEXT ===\n\n"
    current_length = len(context)
    
    for section_id, score in sorted_sections:
        if score == 0:
            break
        if current_length >= max_length:
            break
            
        section_data = sections[section_id]
        section_text = f"## {section_data['title']}\n{section_data['content']}\n\n"
        
        if current_length + len(section_text) <= max_length:
            context += section_text
            current_length += len(section_text)
    
    # If no relevant sections found, include general overview
    if current_length < len(context) + 500:
        context += "\n[Note: For specific queries, please refer to the complete DGCA Civil Aviation Requirements]\n"
    
    return context

def load_pdf_context(pdf_path: str = None) -> Dict[str, Dict]:
    """
    Load and cache PDF content
    Returns structured sections
    """
    global _pdf_content_cache, _pdf_sections_cache
    
    if _pdf_sections_cache is not None:
        return _pdf_sections_cache
    
    if pdf_path is None:
        # Default path relative to this file
        pdf_path = os.path.join(os.path.dirname(__file__), "part2.pdf")
    
    print(f"📄 Loading DGCA rules from: {pdf_path}")
    
    # Extract text
    text = extract_text_from_pdf(pdf_path)
    if not text:
        print("❌ Could not extract text from PDF")
        return {}
    
    _pdf_content_cache = text
    
    # Parse into sections
    sections = parse_dgca_rules(text)
    _pdf_sections_cache = sections
    
    print(f"✓ Loaded {len(sections)} sections, {len(text)} total characters")
    return sections

def get_context_for_query(query: str, max_length: int = 3000) -> str:
    """
    Get relevant DGCA context for a user query
    This is the main function to call from the agent
    """
    # Load PDF if not already loaded
    sections = load_pdf_context()
    
    if not sections:
        return "[DGCA rules context not available]"
    
    # Get relevant context
    context = identify_relevant_context(query, sections, max_length)
    return context

def get_full_content() -> str:
    """
    Get the complete PDF content
    """
    global _pdf_content_cache
    
    if _pdf_content_cache is None:
        load_pdf_context()
    
    return _pdf_content_cache or "[PDF content not available]"

def clear_cache():
    """
    Clear cached PDF content (useful for testing/reloading)
    """
    global _pdf_content_cache, _pdf_sections_cache
    _pdf_content_cache = None
    _pdf_sections_cache = None
    print("✓ PDF cache cleared")

# ============================================================================
# INTEGRATION FUNCTIONS FOR AGENT
# ============================================================================

def get_enhanced_system_prompt_with_rules() -> str:
    """
    Generate system prompt that includes overview of available DGCA rules
    """
    sections = load_pdf_context()
    
    if not sections:
        return ""
    
    # Create a summary of available sections
    section_summary = "Available DGCA Regulation Sections:\n"
    for section_id, section_data in list(sections.items())[:10]:  # First 10 sections
        section_summary += f"- {section_data['title']}\n"
    
    enhanced_prompt = f"""
You have access to the complete DGCA Civil Aviation Requirements (Part II) document.

{section_summary}

When answering questions:
1. Reference specific DGCA regulations from the context provided
2. Cite section numbers when available
3. Provide accurate information based on the regulations
4. If the context doesn't cover the query, acknowledge it and provide general guidance

The regulations cover:
- Passenger rights and compensations
- Flight cancellation rules
- Delay compensation guidelines
- Denied boarding procedures
- Baggage policies
- Complaint procedures
"""
    
    return enhanced_prompt

# ============================================================================
# TEST FUNCTION
# ============================================================================

def test_pdf_loader():
    """
    Test the PDF loader functionality
    """
    print("="*70)
    print("Testing PDF Context Loader")
    print("="*70)
    
    # Test loading
    sections = load_pdf_context()
    print(f"\n📊 Loaded Sections: {len(sections)}")
    
    # Show section titles
    print("\n📋 Section Titles:")
    for i, (section_id, section_data) in enumerate(list(sections.items())[:5]):
        print(f"  {i+1}. {section_data['title']} ({len(section_data['content'])} chars)")
    
    # Test query context
    test_queries = [
        "What compensation for flight cancellation?",
        "Flight delayed by 6 hours",
        "Denied boarding rights"
    ]
    
    print("\n🔍 Testing Context Retrieval:")
    for query in test_queries:
        print(f"\n  Query: '{query}'")
        context = get_context_for_query(query, max_length=500)
        print(f"  Context: {len(context)} characters")
        print(f"  Preview: {context[:150]}...")
    
    print("\n" + "="*70)
    print("✓ PDF Context Loader Test Complete")
    print("="*70)

if __name__ == "__main__":
    test_pdf_loader()
