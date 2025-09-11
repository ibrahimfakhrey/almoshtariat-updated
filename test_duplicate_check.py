#!/usr/bin/env python3

from app_init import app
from agentic_ai_service import agentic_ai_service
import json

with app.app_context():
    print("Testing duplicate order detection...\n")
    
    # Test 1: Try to create a laptop order (should find similar orders)
    print("Test 1: Creating laptop order (should find duplicates)")
    result1 = agentic_ai_service._create_order(1, {
        'products': [{'product_name': 'laptop', 'quantity': 5}],
        'order_name': 'Test Laptop Order',
        'description': 'Testing duplicate detection'
    })
    
    print(f"Result: {json.dumps(result1, indent=2, ensure_ascii=False)}\n")
    
    # Test 2: Try to create a completely different order (should not find duplicates)
    print("Test 2: Creating unique order (should not find duplicates)")
    result2 = agentic_ai_service._create_order(1, {
        'products': [{'product_name': 'unique_test_product_xyz', 'quantity': 1}],
        'order_name': 'Unique Test Order',
        'description': 'This should be unique'
    })
    
    print(f"Result: {json.dumps(result2, indent=2, ensure_ascii=False)}\n")
    
    # Test 3: Check what orders exist
    print("Test 3: Getting recent orders to see what exists")
    recent_orders = agentic_ai_service._get_recent_orders(1, {})
    print(f"Recent orders: {json.dumps(recent_orders, indent=2, ensure_ascii=False)}")