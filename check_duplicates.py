#!/usr/bin/env python3
"""
Script to check for duplicate translations and untranslated English text
in the Arabic translation file and templates.
"""

import re
import os
from collections import defaultdict

def check_translation_duplicates(po_file_path):
    """Check for duplicate msgid entries in the .po file"""
    print(f"\n=== Checking duplicates in {po_file_path} ===")
    
    msgids = defaultdict(list)
    current_msgid = None
    line_num = 0
    
    with open(po_file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line.startswith('msgid "'):
                # Extract msgid content
                match = re.match(r'msgid "(.*)"', line)
                if match:
                    current_msgid = match.group(1)
                    if current_msgid:  # Skip empty msgids
                        msgids[current_msgid].append(line_num)
    
    # Find duplicates
    duplicates = {msgid: lines for msgid, lines in msgids.items() if len(lines) > 1}
    
    if duplicates:
        print("\n🔴 DUPLICATE TRANSLATIONS FOUND:")
        for msgid, lines in duplicates.items():
            print(f"  '{msgid}' appears on lines: {lines}")
    else:
        print("\n✅ No duplicate translations found")
    
    return duplicates

def find_untranslated_english(templates_dir):
    """Find hardcoded English text in templates"""
    print(f"\n=== Checking for hardcoded English in {templates_dir} ===")
    
    # Common English words that should be translated
    english_patterns = [
        r'\b(All Orders|Total Orders|Pending Orders)\b',
        r'\b(View All|View Offers)\b',
        r'\b(Items ready|Orders pending|Orders created)\b',
        r'\b(My Deliveries|Balance|AI Assistant)\b',
        r'\b(Dashboard|User Profile|My Orders|Create Order)\b',
        r'\b(Suppliers|Chats|chats)\b',
        r'\b(Items|Products|Cart Items)\b',
        r'\b(Company Dashboard|Client Chats)\b'
    ]
    
    issues = []
    
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith('.html'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    for pattern in english_patterns:
                        matches = re.finditer(pattern, content, re.IGNORECASE)
                        for match in matches:
                            # Skip if it's already wrapped in translation function
                            start = max(0, match.start() - 20)
                            end = min(len(content), match.end() + 20)
                            context = content[start:end]
                            
                            if "{{ _('" not in context and "{{_('" not in context:
                                line_num = content[:match.start()].count('\n') + 1
                                issues.append({
                                    'file': file_path,
                                    'line': line_num,
                                    'text': match.group(),
                                    'context': context.strip()
                                })
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    
    if issues:
        print("\n🔴 HARDCODED ENGLISH TEXT FOUND:")
        for issue in issues:
            rel_path = os.path.relpath(issue['file'], templates_dir)
            print(f"  {rel_path}:{issue['line']} - '{issue['text']}'")
            print(f"    Context: {issue['context'][:100]}...")
    else:
        print("\n✅ No hardcoded English text found")
    
    return issues

def check_missing_translations(po_file_path):
    """Check for missing Arabic translations (empty msgstr)"""
    print(f"\n=== Checking for missing translations in {po_file_path} ===")
    
    missing = []
    current_msgid = None
    line_num = 0
    
    with open(po_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('msgid "'):
            match = re.match(r'msgid "(.*)"', line)
            if match:
                current_msgid = match.group(1)
                msgid_line = i + 1
                
                # Look for the corresponding msgstr
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('msgstr'):
                    i += 1
                
                if i < len(lines):
                    msgstr_line = lines[i].strip()
                    if msgstr_line == 'msgstr ""' and current_msgid:
                        missing.append((current_msgid, msgid_line))
        i += 1
    
    if missing:
        print("\n🔴 MISSING TRANSLATIONS FOUND:")
        for msgid, line_num in missing:
            print(f"  Line {line_num}: '{msgid}' has empty translation")
    else:
        print("\n✅ All translations have content")
    
    return missing

def main():
    print("🔍 Translation Checker Script")
    print("=============================")
    
    # Paths
    po_file = '/Users/ibrahimfakhry/Desktop/mysite/translations/ar/LC_MESSAGES/messages.po'
    templates_dir = '/Users/ibrahimfakhry/Desktop/mysite/templates'
    
    # Check if files exist
    if not os.path.exists(po_file):
        print(f"❌ Translation file not found: {po_file}")
        return
    
    if not os.path.exists(templates_dir):
        print(f"❌ Templates directory not found: {templates_dir}")
        return
    
    # Run checks
    duplicates = check_translation_duplicates(po_file)
    missing = check_missing_translations(po_file)
    hardcoded = find_untranslated_english(templates_dir)
    
    # Summary
    print("\n" + "="*50)
    print("📊 SUMMARY")
    print("="*50)
    print(f"Duplicate translations: {len(duplicates)}")
    print(f"Missing translations: {len(missing)}")
    print(f"Hardcoded English text: {len(hardcoded)}")
    
    if duplicates or missing or hardcoded:
        print("\n⚠️  Issues found that need to be fixed!")
    else:
        print("\n✅ All checks passed!")

if __name__ == '__main__':
    main()