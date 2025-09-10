#!/usr/bin/env python3
"""
Script to unify sector dropdown menus across all HTML templates
This script will find and standardize all sector options in client/ and company/ folders
"""

import os
import re
from pathlib import Path

# Standardized sectors based on the flask_app.py sector mappings
STANDARD_SECTORS = [
    'Technology',
    'Electronics', 
    'IT',
    'Software',
    'Hardware',
    'General',
    'Other'
]

def find_html_templates():
    """Find all HTML templates in client/ and company/ folders"""
    templates = []
    
    for folder in ['templates/client', 'templates/company']:
        if os.path.exists(folder):
            for file in os.listdir(folder):
                if file.endswith('.html'):
                    templates.append(os.path.join(folder, file))
    
    return templates

def extract_sector_options(html_content):
    """Extract sector options from HTML content"""
    # Pattern to find sector dropdown options
    patterns = [
        # <option value="sector">sector</option>
        r'<option[^>]*value=["\']([^"\']*sector[^"\']*)["\'][^>]*>([^<]*)</option>',
        # <option>sector</option>
        r'<option[^>]*>([^<]*sector[^<]*)</option>',
        # data-sector="sector"
        r'data-sector=["\']([^"\']*)["\']',
        # sector="sector"
        r'sector=["\']([^"\']*)["\']',
        # sector: 'sector'
        r"sector:\s*['\"]([^'\"]*)['\"]",
        # sector: "sector"
        r'sector:\s*["\']([^"\']*)["\']',
    ]
    
    found_sectors = set()
    
    for pattern in patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                for item in match:
                    if item and 'sector' not in item.lower():
                        found_sectors.add(item.strip())
            else:
                if match and 'sector' not in match.lower():
                    found_sectors.add(match.strip())
    
    return found_sectors

def find_sector_dropdowns(html_content):
    """Find all sector dropdown menus in HTML content"""
    # Look for select elements that might contain sectors
    select_patterns = [
        r'<select[^>]*name=["\']sector["\'][^>]*>(.*?)</select>',
        r'<select[^>]*id=["\']sector["\'][^>]*>(.*?)</select>',
        r'<select[^>]*class=["\'][^"\']*sector[^"\']*["\'][^>]*>(.*?)</select>',
        r'<select[^>]*data-field=["\']sector["\'][^>]*>(.*?)</select>',
    ]
    
    dropdowns = []
    
    for pattern in select_patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
        for match in matches:
            dropdowns.append(match)
    
    return dropdowns

def replace_sector_options(html_content, old_sectors, new_sectors):
    """Replace old sector options with standardized ones"""
    modified_content = html_content
    
    # Replace sector options in select elements
    for old_sector in old_sectors:
        if old_sector and old_sector not in new_sectors:
            # Find the closest standard sector (simple matching)
            closest_sector = find_closest_sector(old_sector, new_sectors)
            
            # Replace in various formats
            patterns_to_replace = [
                (f'<option value="{old_sector}">{old_sector}</option>', 
                 f'<option value="{closest_sector}">{closest_sector}</option>'),
                (f'<option value="{old_sector}">', 
                 f'<option value="{closest_sector}">'),
                (f'<option>{old_sector}</option>', 
                 f'<option>{closest_sector}</option>'),
                (f'data-sector="{old_sector}"', 
                 f'data-sector="{closest_sector}"'),
                (f'sector="{old_sector}"', 
                 f'sector="{closest_sector}"'),
                (f"sector: '{old_sector}'", 
                 f"sector: '{closest_sector}'"),
                (f'sector: "{old_sector}"', 
                 f'sector: "{closest_sector}"'),
            ]
            
            for old_pattern, new_pattern in patterns_to_replace:
                modified_content = modified_content.replace(old_pattern, new_pattern)
    
    return modified_content

def find_closest_sector(old_sector, standard_sectors):
    """Find the closest matching standard sector"""
    old_lower = old_sector.lower()
    
    # Direct matches
    for sector in standard_sectors:
        if old_lower == sector.lower():
            return sector
    
    # Partial matches
    for sector in standard_sectors:
        if old_lower in sector.lower() or sector.lower() in old_lower:
            return sector
    
    # Default to 'General' if no match found
    return 'General'

def process_template_file(file_path):
    """Process a single HTML template file"""
    print(f"Processing: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract current sector options
        current_sectors = extract_sector_options(content)
        
        if current_sectors:
            print(f"  Found sectors: {current_sectors}")
            
            # Replace with standardized sectors
            modified_content = replace_sector_options(content, current_sectors, STANDARD_SECTORS)
            
            # Write back to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            print(f"  Updated sectors to: {STANDARD_SECTORS}")
        else:
            print("  No sector options found")
            
    except Exception as e:
        print(f"  Error processing {file_path}: {e}")

def main():
    """Main function to unify all sector dropdowns"""
    print("=== Sector Unification Script ===")
    print(f"Standard sectors: {STANDARD_SECTORS}")
    print()
    
    # Find all HTML templates
    templates = find_html_templates()
    print(f"Found {len(templates)} HTML templates")
    print()
    
    # Process each template
    for template in templates:
        process_template_file(template)
        print()
    
    print("=== Sector unification complete ===")
    print("All templates have been updated with standardized sector options.")

if __name__ == "__main__":
    main()

