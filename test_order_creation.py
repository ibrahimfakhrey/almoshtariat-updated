#!/usr/bin/env python3
from flask_app import app
from agentic_ai_service import agentic_ai_service
from models import Order
from app_init import db

with app.app_context():
    # Test order creation
    print("Testing order creation...")
    result = agentic_ai_service.process_user_request(9, 'أريد طلب 5 أجهزة كمبيوتر', language='ar')
    print('AI Response:')
    print('Success:', result.get('success'))
    print('Response:', result.get('response'))
    print('Function calls:', result.get('function_calls'))
    print('Error:', result.get('error'))
    
    # Check recent orders
    orders = Order.query.filter_by(company_id=9).order_by(Order.created_at.desc()).limit(3).all()
    print('\nRecent orders:')
    for o in orders:
        print(f'Order {o.id}: {o.order_name} - {o.created_at}')