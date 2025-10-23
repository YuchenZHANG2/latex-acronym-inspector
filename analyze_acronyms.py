import os
import re
from pathlib import Path
from collections import defaultdict
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from datetime import datetime

# === CONFIGURATION ====================================================
ENTRY_FILE = "main.tex"   # entry point
ROOT_DIR = "./sample_project"            # LaTeX project root
OUTPUT_NAME = "output_sample.pdf" # The name of the output PDF report
# ======================================================================

def read_latex_recursive(filename, seen=None):
    """Recursively gather text from all \input/\include files."""
    if seen is None:
        seen = set()
    path = Path(ROOT_DIR) / filename
    if path in seen or not path.exists():
        return []
    seen.add(path)

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    entries = []
    pattern = re.compile(r"\\(?:input|include)\{([^}]+)\}")
    for i, line in enumerate(lines, start=1):
        entries.append((path, i, line.strip()))
        for match in pattern.findall(line):
            included = match.strip()
            if not included.endswith(".tex"):
                included += ".tex"
            entries += read_latex_recursive(included, seen)
    return entries


def extract_defined_acronyms(entries):
    """Extract acronym definitions from \newacronym commands."""
    acronym_defs = {}
    pattern = re.compile(
        r"\\newacronym\{([^\}]+)\}\{([^\}]+)\}\{([^\}]+)\}"
    )
    for path, line_no, line in entries:
        match = pattern.search(line)
        if match:
            key, short, full = match.groups()
            acronym_defs[key] = {
                "short": short.strip(),
                "full": full.strip(),
                "file": path,
                "line": line_no,
            }
    return acronym_defs


def scan_acronyms(entries, acronym_defs):
    """Scan all files for defined and undefined acronym usages."""
    used_full = defaultdict(list)
    used_short = defaultdict(list)

    # Find the start of document content
    document_started = False
    content_entries = []
    
    for path, line_no, line in entries:
        if not document_started and "\\begin{document}" in line:
            document_started = True
        if document_started:
            content_entries.append((path, line_no, line))

    for key, data in acronym_defs.items():
        full = data["full"]
        short = data["short"]

        # Create comprehensive patterns for full forms (case-insensitive, plural variations)
        # Handle both simple plurals (s) and common word-ending changes
        escaped_full = re.escape(full)
        # For "World Model" -> matches "world model", "World Models", "world models", etc.
        full_pattern = re.compile(rf"\b{escaped_full}s?\b", re.IGNORECASE)
        
        # Also handle acronym short forms with plurals
        escaped_short = re.escape(short)
        short_pattern = re.compile(rf"\b{escaped_short}s?\b", re.IGNORECASE)

        # Only scan content after \begin{document}
        for path, line_no, line in content_entries:
            if full_pattern.search(line):
                used_full[key].append((path, line_no, line))
            if short_pattern.search(line):
                used_short[key].append((path, line_no, line))

    # --- Detect undefined acronyms via "(ACRONYM)" pattern
    undefined = []
    undefined_counts = defaultdict(list)  # Track all occurrences
    undefined_full_forms = {}  # Track what full forms we find for undefined acronyms
    pattern = re.compile(r"\(([A-Z]{2,10})\)")
    defined_shorts = {v["short"] for v in acronym_defs.values()}
    
    # Roman numerals to exclude (common section titles)
    roman_numerals = {'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 
                     'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX'}

    # Only scan content after \begin{document} for undefined acronyms too
    for path, line_no, line in content_entries:
        for match in pattern.findall(line):
            acronym = match.strip()
            if acronym not in defined_shorts and acronym not in roman_numerals:
                undefined_counts[acronym].append((path, line_no, line.strip()))
                
                # Try to extract the full form that precedes this acronym
                # Pattern: "Full Form Words (ACRONYM)" - capture only the actual definition
                # Look for proper noun phrases that are likely acronym definitions
                # This should capture "Austrian Institute of Technology (AIT)" but not include preceding context
                
                # Simple approach: look for the pattern (ACRONYM) and take up to 5 words before it
                # Find the position of the acronym in parentheses
                acronym_pattern = rf'\({re.escape(acronym)}\)'
                match_obj = re.search(acronym_pattern, line)
                
                if match_obj:
                    # Get the text before the parentheses
                    text_before = line[:match_obj.start()].strip()
                    
                    # Split into words and take the last 5 words
                    words = text_before.split()
                    if words:
                        # Take last 5 words (or fewer if less available)
                        candidate_words = words[-5:]
                        
                        # Use capital letter logic: find sequence of words that start with capital letters
                        # and could form the acronym definition
                        full_form_words = []
                        for word in reversed(candidate_words):  # Go backwards to build the definition
                            # Include words that start with capital letters or are common connecting words
                            if (word[0].isupper() or 
                                word.lower() in ['of', 'and', 'for', 'the', '&', 'to', 'in', 'on', 'with', 'at', 'by', 'from', 'de']):
                                full_form_words.append(word)
                            else:
                                break  # Stop when we hit a lowercase word that's not a connector
                        
                        if full_form_words:
                            # Reverse to get correct order and join
                            full_form = ' '.join(reversed(full_form_words))
                            
                            # Basic validation: should have at least one capital letter word
                            capital_words = [w for w in full_form_words if w[0].isupper()]
                            if capital_words and len(full_form_words) <= 6:  # Reasonable length
                                if acronym not in undefined_full_forms:
                                    undefined_full_forms[acronym] = set()
                                undefined_full_forms[acronym].add(full_form)
    
    # Only report acronyms that appear 2 or more times
    for acronym, occurrences in undefined_counts.items():
        if len(occurrences) >= 2:
            undefined.extend([(acronym, path, line_no, line) for path, line_no, line in occurrences])

    # --- Check for standalone usage of full forms (inconsistent usage)
    inconsistent_usage = defaultdict(list)
    
    # For each undefined acronym that we found full forms for
    for acronym, full_forms in undefined_full_forms.items():
        for full_form in full_forms:
            # Create a pattern to find standalone usage of this full form
            # (not followed by the acronym in parentheses)
            standalone_pattern = rf'\b{re.escape(full_form)}\b(?!\s*\({re.escape(acronym)}\))'
            
            # Search for standalone usage in all content
            for path, line_no, line in content_entries:
                if re.search(standalone_pattern, line, re.IGNORECASE):
                    inconsistent_usage[acronym].append((path, line_no, line.strip(), full_form))

    report = {
        "used_full": used_full,
        "used_short": used_short,
        "undefined": undefined,
        "undefined_full_forms": undefined_full_forms,
        "inconsistent_usage": inconsistent_usage,
    }
    return report


def extract_sentence_containing_text(text, target_text):
    """Extract the sentence containing the target text with practical balance between accuracy and readability."""
    
    # Find the position of the target text
    target_pos = text.find(target_text)
    if target_pos == -1:
        return text.strip()
    
    # Better sentence boundary detection that handles special cases
    def is_sentence_boundary(text, pos):
        """Check if position is a real sentence boundary."""
        if pos >= len(text) or text[pos] not in '.!?':
            return False
            
        # Check for common abbreviations and special cases
        before_context = text[max(0, pos-10):pos].lower()
        after_context = text[pos+1:pos+5] if pos+1 < len(text) else ""
        
        # Common abbreviations that shouldn't end sentences
        abbreviations = ['e.g', 'i.e', 'etc', 'vs', 'cf', 'al', 'fig', 'eq', 'sec', 'ch', 'vol', 'ed', 'pp', 'no', 'mr', 'mrs', 'dr', 'prof', 'inc', 'ltd', 'corp']
        
        for abbr in abbreviations:
            if before_context.endswith(abbr):
                return False
        
        # Check for email addresses (simple pattern)
        if pos > 0 and pos < len(text) - 1:
            # Look for patterns like "name@domain.com" 
            email_before = re.search(r'\S+@\S+$', before_context)
            if email_before and not after_context.startswith(' '):
                return False
        
        # Check for URLs
        if 'http' in before_context or 'www' in before_context:
            return False
            
        # Check for decimal numbers
        if pos > 0 and pos < len(text) - 1:
            if (text[pos-1].isdigit() and text[pos+1].isdigit()):
                return False
        
        # Check if next character is lowercase (likely continuation)
        if after_context and after_context[0].islower():
            return False
            
        # If we made it here, it's likely a real sentence boundary
        return True
    
    # Find sentence start (go backwards from target)
    sentence_start = 0
    for i in range(target_pos - 1, -1, -1):
        if is_sentence_boundary(text, i):
            sentence_start = i + 1
            break
    
    # Find sentence end (go forwards from target)
    sentence_end = len(text)
    for i in range(target_pos, len(text)):
        if is_sentence_boundary(text, i):
            sentence_end = i + 1
            break
    
    # Extract the sentence
    sentence = text[sentence_start:sentence_end].strip()
    
    # Practical readability: if sentence is too long (>400 chars), 
    # try to break it at natural points like semicolons or long clauses
    if len(sentence) > 400:
        # Try to find a good break point near the target
        context_before = max(0, target_pos - sentence_start - 100)
        context_after = min(len(sentence), target_pos - sentence_start + 150)
        
        # Look for natural break points (semicolons, long commas, etc.)
        break_chars = [';', ',', ':', '--', ' and ', ' but ', ' while ', ' although ']
        
        best_start = context_before
        best_end = context_after
        
        # Find best start point
        for i in range(context_before, 0, -1):
            for break_char in break_chars:
                if sentence[i:i+len(break_char)] == break_char:
                    best_start = i + len(break_char)
                    break
            if best_start != context_before:
                break
        
        # Find best end point
        for i in range(context_after, len(sentence)):
            for break_char in break_chars:
                if sentence[i:i+len(break_char)] == break_char:
                    best_end = i
                    break
            if best_end != context_after:
                break
        
        # Extract the focused segment
        focused_sentence = sentence[best_start:best_end].strip()
        
        # Make sure our target is still in the focused sentence
        if target_text in focused_sentence and len(focused_sentence) > 30:
            sentence = focused_sentence
    
    # If sentence is still too short or doesn't contain target, return more context
    if len(sentence) < 20 or target_text not in sentence:
        # Expand to include more context around target
        expanded_start = max(0, target_pos - 150)
        expanded_end = min(len(text), target_pos + 200)
        sentence = text[expanded_start:expanded_end].strip()
    
    return sentence


def generate_pdf_report(acronym_defs, report, output_filename="acronym_report.pdf"):
    """Generate a PDF report of the acronym analysis."""
    doc = SimpleDocTemplate(output_filename, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        textColor=colors.darkblue
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.darkgreen
    )
    
    # Small description style for category explanations
    description_style = ParagraphStyle(
        'CategoryDescription',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=10,
        fontName='Helvetica',
        textColor=colors.darkgreen,
    )
    
    # Title
    story.append(Paragraph("LaTeX Acronym Analysis Report", title_style))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 30))
    
    # Summary
    story.append(Paragraph("Summary", heading_style))
    
    # Count total undefined acronym instances (multiple informal definitions)
    undefined_count = len(report['undefined'])  # Total instances, not unique acronyms
    
    # Count total instances of glossary acronyms that also use full forms
    glossary_full_form_count = sum(len(usages) for k, usages in report["used_full"].items() 
                                  if k in acronym_defs and len(usages) > 1)
    
    summary_data = [
        ["Category", "Count"],
        ["Not in glossaries, defined multiple times", str(undefined_count)],
        ["Defined in glossaries but full name used", str(glossary_full_form_count)]
    ]
    
    summary_table = Table(summary_data, colWidths=[4.5*inch, 1.5*inch])
    summary_table.setStyle(TableStyle([
        # Header row styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        # Data rows styling
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        # General styling
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))
    
    # Defined but never used
    defined_never_used = [
        k for k in acronym_defs if k not in report["used_full"] and k not in report["used_short"]
    ]
    if defined_never_used:
        story.append(Paragraph("Defined but Never Used", heading_style))
        for k in defined_never_used:
            d = acronym_defs[k]
            story.append(Paragraph(f"• <b>{d['short']}</b> ({d['full']}) [<b><font color='blue'>{d['file'].name}</font></b>]", styles['Normal']))
        story.append(Spacer(1, 20))
    
    # Section 1: Not in glossaries and defined multiple times  
    if report['undefined']:
        story.append(Paragraph("1. Not in Glossaries and Defined Multiple Times", heading_style))
        story.append(Paragraph("(These acronyms appear in parentheses multiple times but are not formally defined in glossaries)", description_style))
        story.append(Spacer(1, 10))
        undefined_grouped = defaultdict(list)
        for acronym, path, line_no, line in report["undefined"]:
            undefined_grouped[acronym].append((path, line_no, line))
        
        for i, (acronym, occurrences) in enumerate(undefined_grouped.items(), 1):
            # Only show the acronym name, not the extracted full forms
            story.append(Paragraph(f"{i}. <b>{acronym}</b>", styles['Normal']))
            
            for path, line_no, line in occurrences:
                # Extract the sentence containing the acronym
                sentence = extract_sentence_containing_text(line, f"({acronym})")
                
                # Clean the sentence and highlight the acronym more carefully
                import html
                clean_sentence = html.escape(sentence)  # Escape HTML chars first
                
                # Get all known full forms for this acronym
                full_forms_found = report.get("undefined_full_forms", {}).get(acronym, set())
                
                # Start with the original sentence
                highlighted_sentence = clean_sentence
                
                # Highlight all variations of known full forms
                for full_form in full_forms_found:
                    # Create case-insensitive patterns for all variations
                    escaped_form = re.escape(full_form)
                    
                    # Pattern 1: Full form with acronym (e.g., "Variational Autoencoder (VAE)")
                    pattern_with_acronym = rf'({escaped_form})\s*\({re.escape(acronym)}\)'
                    highlighted_sentence = re.sub(pattern_with_acronym, 
                                                r'<font color="red">\1 (' + acronym + ')</font>', 
                                                highlighted_sentence, flags=re.IGNORECASE)
                    
                    # Pattern 2: Just the full form without acronym (e.g., "variational autoencoder")
                    pattern_standalone = rf'\b({escaped_form})\b(?!\s*\({re.escape(acronym)}\))'
                    highlighted_sentence = re.sub(pattern_standalone, 
                                                r'<font color="red">\1</font>', 
                                                highlighted_sentence, flags=re.IGNORECASE)
                
                # Also look for any other potential full forms in this specific line
                # Pattern: "Full phrase followed by (ACRONYM)" -> highlight entire thing in red
                # Use the same improved pattern to avoid over-capturing
                # Use the same simple approach as in scanning
                pattern = rf'\({re.escape(acronym)}\)'
                
                def highlight_definition(match_obj):
                    # Get the text before the parentheses in the sentence
                    text_before = highlighted_sentence[:match_obj.start()].strip()
                    words = text_before.split()
                    
                    if words:
                        # Take last 5 words and apply capital letter logic
                        candidate_words = words[-5:]
                        full_form_words = []
                        
                        for word in reversed(candidate_words):
                            if (word[0].isupper() or 
                                word.lower() in ['of', 'and', 'for', 'the', '&', 'to', 'in', 'on', 'with', 'at', 'by', 'from', 'de']):
                                full_form_words.append(word)
                            else:
                                break
                        
                        if full_form_words:
                            full_form = ' '.join(reversed(full_form_words))
                            # Calculate positions for highlighting
                            full_form_start = match_obj.start() - len(full_form) - 1  # -1 for space
                            if full_form_start >= 0:
                                prefix = highlighted_sentence[:full_form_start]
                                highlighted_def = f'<font color="blue"><b>{html.escape(full_form)}</b></font>'
                                highlighted_acronym = f' <font color="red"><b>{html.escape(match_obj.group(0))}</b></font>'
                                suffix = highlighted_sentence[match_obj.end():]
                                return prefix + highlighted_def + highlighted_acronym + suffix
                    
                    # Fallback: just highlight the acronym
                    return highlighted_sentence[:match_obj.start()] + f'<font color="red"><b>{html.escape(match_obj.group(0))}</b></font>' + highlighted_sentence[match_obj.end():]
                
                # Apply highlighting - but we need to do this more carefully
                matches = list(re.finditer(pattern, highlighted_sentence))
                if matches:
                    # Process from right to left to maintain positions
                    for match_obj in reversed(matches):
                        before = highlighted_sentence[:match_obj.start()]
                        words_before = before.strip().split()
                        
                        if words_before:
                            candidate_words = words_before[-5:]
                            full_form_words = []
                            
                            for word in reversed(candidate_words):
                                if (word[0].isupper() or 
                                    word.lower() in ['of', 'and', 'for', 'the', '&', 'to', 'in', 'on', 'with', 'at', 'by', 'from', 'de']):
                                    full_form_words.append(word)
                                else:
                                    break
                            
                            if full_form_words:
                                full_form = ' '.join(reversed(full_form_words))
                                # Find where the full form starts in the original sentence
                                full_form_pos = before.rfind(full_form)
                                if full_form_pos >= 0:
                                    prefix = highlighted_sentence[:full_form_pos]
                                    highlighted_def = f'<font color="red">{html.escape(full_form)}</font>'
                                    space_and_acronym = highlighted_sentence[full_form_pos + len(full_form):match_obj.end()]
                                    highlighted_acronym = re.sub(rf'\({re.escape(acronym)}\)', 
                                                                f'<font color="red">({acronym})</font>', 
                                                                space_and_acronym)
                                    suffix = highlighted_sentence[match_obj.end():]
                                    highlighted_sentence = prefix + highlighted_def + highlighted_acronym + suffix
                                    break  # Only process first match to avoid conflicts
                def highlight_full_definition(match):
                    full_definition = match.group(0).strip()  # Get the entire match including parentheses
                    return f'<font color="red">{full_definition}</font>'
                
                # If no full definition was found, just highlight the acronym in parentheses
                if '(' + acronym + ')' in clean_sentence and '<font color="red">' not in highlighted_sentence:
                    pattern = rf'\({re.escape(acronym)}\)'
                    highlighted_sentence = re.sub(pattern, f'(<font color="red">{acronym}</font>)', highlighted_sentence)
                
                # Show the sentence
                story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;<b><font color='blue'>{path.name}</font></b>: {highlighted_sentence}", styles['Normal']))
            story.append(Spacer(1, 10))

    # Section 2: In glossaries, but full name used
    story.append(Paragraph("2. In Glossaries, but Full Name Used", heading_style))
    story.append(Paragraph("(These acronyms are properly defined in glossaries but their full forms are also used in the text instead of using /gls or /glspl)", description_style))
    story.append(Spacer(1, 10))
    for key, data in acronym_defs.items():
        full = data["full"]
        short = data["short"]
        
        full_uses = report["used_full"].get(key, [])
        short_uses = report["used_short"].get(key, [])
        
        # Only show if there are full form uses after the first appearance
        if full_uses and len(full_uses) > 1:
            story.append(Paragraph(f"<b>{short}</b> ({full})", styles['Normal']))
            
            # Show all full form uses (highlight the full form in red)
            for f, l, t in full_uses:
                sentence = extract_sentence_containing_text(t, full)
                # Highlight the full form in red (preserve original case)
                def highlight_preserving_case(match):
                    return f'<font color="red">{match.group(0)}</font>'
                
                highlighted_sentence = re.sub(re.escape(full), highlight_preserving_case, sentence, flags=re.IGNORECASE)
                story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;<b><font color='blue'>{f.name}</font></b> — {highlighted_sentence}", styles['Normal']))
            
            story.append(Spacer(1, 10))
    
    # Build PDF
    doc.build(story)
    return output_filename


def main():
    entries = read_latex_recursive(ENTRY_FILE)
    acronym_defs = extract_defined_acronyms(entries)
    report = scan_acronyms(entries, acronym_defs)
    
    # Generate PDF report
    pdf_filename = OUTPUT_NAME
    output_file = generate_pdf_report(acronym_defs, report, pdf_filename)
    print(f"PDF report generated: {output_file}")


if __name__ == "__main__":
    main()
