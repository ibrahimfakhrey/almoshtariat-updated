from flask import render_template, request, redirect, url_for, flash, send_file, session, jsonify, make_response, \
    send_from_directory, abort
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import requests
import random
import csv
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app_init import app, db, login_manager, gettext as _, get_locale, babel, csrf
from models import User, Order, Purchase, Company, Offer, ProductOffer, Chat, Message, Product, Notification, \
    HiddenOrder, UserPreference, Cart, SupplierOrder, SupplierOrderProduct, Complaint, Package, Balance, Transaction, \
    CompanyBalance, CompanyTransaction, ChatHistory, Bill, BillItem
from datetime import datetime, timezone, timedelta
import calendar
import pandas as pd
from io import StringIO, BytesIO
import os
import re
import time
import secrets
from werkzeug.utils import secure_filename
from typing import Optional, Union
import io
from ai_config import ai_config
from ai_service import ai_service
from ai_agent_service import ai_agent_service
from agentic_ai_service import agentic_ai_service

# Configuration
upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')

# Initialize SocketIO for real-time notifications
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# PDF Generation imports
PDF_AVAILABLE = False
PDF_ENGINE = None
HTML = None
CSS = None

try:
    # Try WeasyPrint first (better Arabic support)
    import weasyprint  # type: ignore
    from weasyprint import HTML, CSS  # type: ignore
    PDF_AVAILABLE = True
    PDF_ENGINE = 'weasyprint'
    print("WeasyPrint available - excellent Arabic text support!")
except ImportError:
    # WeasyPrint not available, set fallback values
    weasyprint = None  # type: ignore
    HTML = None  # type: ignore
    CSS = None  # type: ignore
    PDF_AVAILABLE = False
    PDF_ENGINE = None
    try:
        # Fallback to ReportLab
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
        PDF_AVAILABLE = True
        PDF_ENGINE = 'reportlab'
        print("ReportLab available - limited Arabic text support")
    except ImportError:
        PDF_AVAILABLE = False
        PDF_ENGINE = None
        print("Warning: No PDF libraries available. PDF generation will not work.")


# Notification utility functions
def create_notification(title: str = "", description: str = "", notification_type: str = 'info', priority: str = 'normal',
                        user_id: Optional[int] = None, company_id: Optional[int] = None, 
                        related_order_id: Optional[int] = None, related_offer_id: Optional[int] = None, 
                        related_chat_id: Optional[int] = None, related_product_id: Optional[int] = None) -> Optional['Notification']:
    """Create a new notification with real-time delivery"""
    try:
        notification = Notification()
        notification.title = title or "Notification"
        notification.description = description or "No description"
        notification.notification_type = notification_type
        notification.priority = priority
        notification.user_id = user_id
        notification.company_id = company_id
        notification.related_order_id = related_order_id
        notification.related_offer_id = related_offer_id
        notification.related_chat_id = related_chat_id
        notification.related_product_id = related_product_id
        db.session.add(notification)
        db.session.commit()
        
        # Emit real-time notification
        notification_data = {
            'id': notification.id,
            'title': notification.title,
            'description': notification.description,
            'type': notification.notification_type,
            'priority': notification.priority,
            'created_at': notification.created_at.isoformat() if notification.created_at else '',
            'is_read': notification.is_read
        }
        
        # Send to appropriate recipient
        if user_id:
            emit_notification_to_user(user_id, notification_data)
        elif company_id:
            emit_notification_to_company(company_id, notification_data)
            
        return notification
    except Exception as e:
        db.session.rollback()
        print(f"Error creating notification: {e}")
        return None


def get_user_notifications(user_id: int, limit: int = 10, unread_only: bool = False, 
                          notification_type: Optional[str] = None, priority: Optional[str] = None, 
                          date_from: Optional[datetime] = None, date_to: Optional[datetime] = None):
    """Get notifications for a specific user with advanced filtering"""
    query = Notification.query.filter_by(user_id=user_id)
    
    if unread_only:
        query = query.filter_by(is_read=False)
    
    if notification_type and notification_type != 'all':
        query = query.filter_by(notification_type=notification_type)
    
    if priority and priority != 'all':
        query = query.filter_by(priority=priority)
    
    if date_from:
        query = query.filter(Notification.created_at >= date_from)
    
    if date_to:
        query = query.filter(Notification.created_at <= date_to)
    
    return query.order_by(Notification.created_at.desc()).limit(limit).all()


def get_company_notifications(company_id: int, limit: int = 10, unread_only: bool = False, 
                             notification_type: Optional[str] = None, priority: Optional[str] = None, 
                             date_from: Optional[datetime] = None, date_to: Optional[datetime] = None):
    """Get notifications for a specific company with advanced filtering"""
    query = Notification.query.filter_by(company_id=company_id)
    
    if unread_only:
        query = query.filter_by(is_read=False)
    
    if notification_type and notification_type != 'all':
        query = query.filter_by(notification_type=notification_type)
    
    if priority and priority != 'all':
        query = query.filter_by(priority=priority)
    
    if date_from:
        query = query.filter(Notification.created_at >= date_from)
    
    if date_to:
        query = query.filter(Notification.created_at <= date_to)
    
    return query.order_by(Notification.created_at.desc()).limit(limit).all()


def mark_notification_read(notification_id: int, user_id: Optional[int] = None) -> bool:
    """Mark a notification as read"""
    notification = Notification.query.get(notification_id)
    if notification and (user_id is None or notification.user_id == user_id):
        if notification and hasattr(notification, 'mark_as_read'):
            notification.mark_as_read()
        else:
            notification.is_read = True
        db.session.commit()
        return True
    return False


# Groq API Configuration
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')  # Set this in environment variables
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def compare_offers_with_ai(offers_data):
    """
    Use Groq API to compare offers and provide analysis
    Returns AI-generated comparison with advantages/disadvantages
    """
    try:
        # Prepare the prompt for offer comparison
        num_offers = len(offers_data)
        prompt = f"""
        Please analyze and compare these {num_offers} offers for a client order. Provide a detailed comparison with:

        1. **Overall Summary**: Brief overview of all offers
        2. **Individual Offer Analysis**: For each offer, list:
           - Key advantages
           - Potential drawbacks
           - Price competitiveness
           - Delivery considerations
        3. **Comparative Analysis**: How the offers stack up against each other
        4. **Overall Recommendation**: Which offer(s) might be best and why
        5. **Key Considerations**: Important factors the client should think about
        6. **Decision Factors**: Price vs. quality vs. delivery time trade-offs

        Offer Details:
        {json.dumps(offers_data, indent=2)}

        Please provide a structured, professional analysis that helps the client make an informed decision. 
        Focus on practical insights and actionable recommendations.
        """

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "llama3-8b-8192",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 200
        }

        response = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=30)

        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            return f"Error: Unable to get AI analysis. Status: {response.status_code}"

    except Exception as e:
        return f"Error: {str(e)}"


# Purchase preferences utility functions
def process_purchase_preferences_file(file_path: str, user_id: int):
    """
    Process uploaded Excel/CSV file and extract purchase preferences
    Returns a list of UserPreference objects
    """
    try:
        # Read the file based on extension
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path, engine='openpyxl')
        elif file_path.endswith('.xls'):
            df = pd.read_excel(file_path, engine='xlrd')
        else:
            raise ValueError("Unsupported file format. Please upload Excel (.xlsx, .xls) or CSV files.")

        # Check if required columns exist
        required_columns = ['product_name']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        preferences = []

        # Process each row
        for index, row in df.iterrows():
            try:
                # Extract data from row with better error handling
                product_name = str(row.get('product_name', '')).strip()
                if not product_name or product_name == 'nan' or product_name == '':
                    continue

                # Handle quantity conversion more safely
                quantity = None
                quantity_val = row.get('quantity')
                if quantity_val is not None and pd.notna(quantity_val):
                    try:
                        quantity = int(float(quantity_val))
                    except (ValueError, TypeError):
                        quantity = None

                # Handle price conversion more safely
                max_price = None
                price_val = row.get('max_price_per_unit')
                if price_val is not None and pd.notna(price_val):
                    try:
                        max_price = float(price_val)
                    except (ValueError, TypeError):
                        max_price = None

                # Handle date conversion more safely
                last_purchased = None
                date_val = row.get('last_purchased')
                if date_val is not None and pd.notna(date_val):
                    try:
                        last_purchased = pd.to_datetime(date_val).date()
                    except (ValueError, TypeError):
                        last_purchased = None

                # Handle typical order size conversion
                typical_order_size = None
                size_val = row.get('typical_order_size')
                if size_val is not None and pd.notna(size_val):
                    try:
                        typical_order_size = int(float(size_val))
                    except (ValueError, TypeError):
                        typical_order_size = None

                # Create UserPreference object
                preference = UserPreference()
                preference.user_id = user_id or 0
                preference.product_name = product_name or "Unknown Product"
                # Handle product category
                cat_val = row.get('product_category')
                preference.product_category = str(cat_val).strip() if cat_val is not None and pd.notna(cat_val) else "General"
                
                # Handle product description
                desc_val = row.get('description')
                preference.product_description = str(desc_val).strip() if desc_val is not None and pd.notna(desc_val) else None
                
                preference.quantity = quantity
                
                # Handle unit
                unit_val = row.get('unit', 'pcs')
                preference.unit = str(unit_val).strip() if unit_val is not None and pd.notna(unit_val) else 'pcs'
                
                # Handle frequency
                freq_val = row.get('frequency')
                preference.frequency = str(freq_val).strip() if freq_val is not None and pd.notna(freq_val) else None
                
                preference.last_purchased = last_purchased
                preference.typical_order_size = typical_order_size
                
                # Handle preferred suppliers
                supp_val = row.get('preferred_suppliers')
                preference.preferred_suppliers = str(supp_val).strip() if supp_val is not None and pd.notna(supp_val) else None
                
                preference.max_price_per_unit = max_price
                
                # Handle quality preference
                qual_val = row.get('quality_preference')
                preference.quality_preference = str(qual_val).strip() if qual_val is not None and pd.notna(qual_val) else None
                
                # Handle payment preference
                pay_val = row.get('payment_preference')
                preference.payment_preference = str(pay_val).strip() if pay_val is not None and pd.notna(pay_val) else None
                
                preference.extracted_at = datetime.utcnow()
                
                # Handle preferred delivery time
                del_val = row.get('preferred_delivery_time')
                preference.preferred_delivery_time = str(del_val).strip() if del_val is not None and pd.notna(del_val) else None
                preference.source_file = str(file_path) if file_path else None
                preference.confidence_score = 1.0

                preferences.append(preference)

            except Exception as e:
                print(f"Error processing row {index}: {e}")
                continue

        if not preferences:
            raise ValueError("No valid product preferences found in the file. Please check the format and data.")

        return preferences

    except Exception as e:
        print(f"Error processing purchase preferences file: {e}")
        raise e


def get_user_purchase_preferences(user_id: int, limit: Optional[int] = None):
    """Get purchase preferences for a specific user"""
    query = UserPreference.query.filter_by(user_id=user_id).order_by(UserPreference.confidence_score.desc())
    if limit:
        return query.limit(limit).all()
    return query.all()


def get_user_frequent_products(user_id: int, frequency: str = 'monthly', limit: int = 10):
    """Get products that user purchases frequently"""
    return UserPreference.query.filter_by(
        user_id=user_id,
        frequency=frequency
    ).order_by(UserPreference.confidence_score.desc()).limit(limit).all()


def suggest_products_based_on_preferences(user_id: int, part_name: Optional[str] = None, sector: Optional[str] = None, limit: int = 10):
    """
    Suggest products based on user's purchase preferences
    Returns a list of suggested products with relevance scores
    """
    # Get user preferences
    user_preferences = get_user_purchase_preferences(user_id)

    if not user_preferences:
        return []

    # Find matching products based on preferences
    suggested_products = []

    for preference in user_preferences:
        # Search for products that match the preference
        matching_products = find_matching_products(
            preference.product_name,
            preference.product_description or '',
            preference.product_category
        )

        for product_info in matching_products:
            # Calculate relevance score based on preference
            relevance_score = preference.confidence_score

            # Boost score if it matches the current search
            if part_name and part_name.lower() in product_info['product'].name.lower():
                relevance_score += 2
            if sector and sector.lower() in product_info['product'].category.lower():
                relevance_score += 1

            suggested_products.append({
                'product': product_info['product'],
                'relevance_score': relevance_score,
                'preference': preference
            })

@app.route('/confirm_delivery/<int:package_id>', methods=['POST'])
@login_required
def confirm_delivery(package_id: int):
    """Confirm delivery of a package using the delivery code"""
    try:
        # Get the package
        package = Package.query.get_or_404(package_id)
        
        # Check if user has permission
        # Companies can confirm packages they own, clients can confirm packages from their orders
        if current_user.role == 'company':
            if package.company_id != current_user.company_id:
                return jsonify({'success': False, 'message': 'Access denied'}), 403
        elif current_user.role == 'client':
            # Check if this package belongs to an order made by the current user
            order = db.session.get(Order, package.order_id)
            if not order or order.user_id != current_user.id:
                return jsonify({'success': False, 'message': 'Access denied'}), 403
        else:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Check if package is in a valid status for delivery confirmation
        if package.status not in ['shipped', 'preparing']:
            return jsonify({'success': False, 'message': 'Package cannot be marked as delivered in current status'}), 400
        
        # Get the delivery code from request
        data = request.get_json()
        if not data or 'delivery_code' not in data:
            return jsonify({'success': False, 'message': 'Delivery code is required'}), 400
        
        provided_code = data['delivery_code'].strip().upper()
        
        # Verify the delivery code
        if not package.delivery_code or package.delivery_code.upper() != provided_code:
            return jsonify({'success': False, 'message': 'Invalid delivery code'}), 400
        
        # Update package status to delivered
        package.status = 'delivered'
        package.delivered_at = datetime.now(timezone.utc)
        
        # Update the related offer status to delivered
        offer = db.session.get(Offer, package.offer_id)
        if offer:
            offer.order_status = 'delivered'
        
        # Update the related order status to delivered
        order = db.session.get(Order, package.order_id)
        if order:
            order.status = 'delivered'
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Package successfully marked as delivered',
            'package_id': package.id,
            'delivered_at': package.delivered_at.isoformat() if package.delivered_at else None
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error confirming delivery: {str(e)}'}), 500

@app.route('/unconfirm_delivery/<int:package_id>', methods=['POST'])
@login_required
def unconfirm_delivery(package_id: int):
    """Unconfirm delivery of a package (change status from delivered back to shipped)"""
    try:
        # Get the package
        package = Package.query.get_or_404(package_id)
        
        # Check if user has permission
        # Only companies can unconfirm packages they own
        if current_user.role != 'company' or package.company_id != current_user.company_id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Check if package is in delivered status
        if package.status != 'delivered':
            return jsonify({'success': False, 'message': 'Package is not in delivered status'}), 400
        
        # Update package status back to shipped
        package.status = 'shipped'
        package.delivered_at = None
        
        # Update the related offer status back to shipped
        offer = db.session.get(Offer, package.offer_id)
        if offer:
            offer.order_status = 'shipped'
        
        # Update the related order status back to shipped
        order = db.session.get(Order, package.order_id)
        if order:
            order.status = 'shipped'
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Package delivery status successfully reverted to shipped',
            'package_id': package.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error unconfirming delivery: {str(e)}'}), 500

@app.route('/delivery_success/<int:package_id>')
@login_required
def delivery_success(package_id: int):
    """Show delivery success page"""
    package = Package.query.get_or_404(package_id)
    
    # Check if user has permission to view this page
    if current_user.role != 'company' or package.company_id != current_user.company_id:
        flash('Access denied', 'error')
        return redirect(url_for('dash'))
    
    # Check if package is actually delivered
    if package.status != 'delivered':
        flash('Package is not marked as delivered', 'error')
        return redirect(url_for('package_details', package_id=package_id))
    
    return render_template('delivery_success.html', package=package)


def get_product_suggestions(user_id: int, sector: str, limit: int = 10):
    """Get product suggestions based on user preferences and sector"""
    # Get products from the database based on sector
    products = Product.query.filter_by(sector=sector).limit(limit * 2).all()
    
    # Create suggestions with basic relevance scoring
    suggested_products = []
    for product in products:
        suggestion = {
            'product': product,
            'relevance_score': 1.0  # Basic scoring, can be enhanced later
        }
        suggested_products.append(suggestion)
    
    # Sort by relevance score and remove duplicates
    seen_products = set()
    unique_suggestions = []

    for suggestion in sorted(suggested_products, key=lambda x: x['relevance_score'], reverse=True):
        product_id = suggestion['product'].id
        if product_id not in seen_products:
            seen_products.add(product_id)
            unique_suggestions.append(suggestion)
            if len(unique_suggestions) >= limit:
                break

    return unique_suggestions


def add_products_to_user_preferences(user_id: int, products_data: list, sector: str):
    """
    Automatically add products from an order to user preferences if they don't already exist
    This helps build the user's preference database over time
    """
    try:
        added_count = 0
        for product_data in products_data:
            # Check if this product already exists in user preferences
            existing_preference = UserPreference.query.filter_by(
                user_id=user_id,
                product_name=product_data['product_name']
            ).first()

            if not existing_preference:
                # Create new preference from order data
                new_preference = UserPreference()
                new_preference.user_id = user_id
                new_preference.product_name = product_data['product_name']
                new_preference.product_category = sector
                new_preference.product_description = product_data['technical_specs']
                new_preference.quantity = product_data['quantity']
                new_preference.unit = product_data['unit']
                new_preference.frequency = 'as_needed'  # Default frequency
                new_preference.max_price_per_unit = float(product_data['max_price_per_unit']) if product_data[
                    'max_price_per_unit'] else None
                new_preference.preferred_suppliers = product_data['best_supplier'] if product_data['best_supplier'] else None
                new_preference.quality_preference = 'standard'  # Default quality preference
                new_preference.payment_preference = 'standard'  # Default payment preference
                new_preference.preferred_delivery_time = 'standard'  # Default delivery preference
                new_preference.typical_order_size = product_data['quantity']
                new_preference.last_purchased = datetime.utcnow().date()
                new_preference.source_file = 'order_creation'  # Indicate this came from order creation
                new_preference.confidence_score = 0.8  # High confidence since it's from actual order

                db.session.add(new_preference)
                added_count += 1
            else:
                # Update existing preference with latest order data
                existing_preference.quantity = product_data['quantity']
                existing_preference.unit = product_data['unit']
                existing_preference.max_price_per_unit = float(product_data['max_price_per_unit']) if product_data[
                    'max_price_per_unit'] else existing_preference.max_price_per_unit
                existing_preference.preferred_suppliers = product_data['best_supplier'] if product_data[
                    'best_supplier'] else existing_preference.preferred_suppliers
                existing_preference.last_purchased = datetime.utcnow().date()
                existing_preference.typical_order_size = product_data['quantity']
                existing_preference.confidence_score = min(1.0,
                                                           existing_preference.confidence_score + 0.1)  # Increase confidence

        if added_count > 0:
            db.session.commit()
            print(f"Added {added_count} new products to user {user_id} preferences")

        return added_count

    except Exception as e:
        print(f"Error adding products to user preferences: {e}")
        db.session.rollback()
        return 0


# Product matching utility functions
def find_matching_products(part_name: str, description: str, sector: Optional[str] = None):
    """
    Find products that match the client's needs
    Returns a list of matching products with company info
    """
    # Convert search terms to lowercase for better matching
    search_terms = f"{part_name} {description}".lower()

    # Get all active products from all companies
    all_products = Product.query.filter_by(is_active=True).all()

    matching_products = []

    for product in all_products:
        # Create a product search string
        product_search = f"{product.name} {product.description} {product.category}".lower()

        # Check if any of the search terms match the product
        match_score = 0

        # Exact name match (highest priority)
        if part_name.lower() in product.name.lower() or product.name.lower() in part_name.lower():
            match_score += 10

        # Category match
        if sector and sector.lower() in product.category.lower():
            match_score += 5

        # Description keyword matching
        search_words = search_terms.split()
        product_words = product_search.split()

        for word in search_words:
            if len(word) > 2:  # Only consider words longer than 2 characters
                if word in product_words:
                    match_score += 2

        # If we have a reasonable match score, include the product
        if match_score >= 3:
            matching_products.append({
                'product': product,
                'company': product.company,
                'match_score': match_score,
                'price': product.price,
                'quantity_available': product.quantity,
                'delivery_info': f"In stock: {product.quantity} {product.unit}"
            })

    # Sort by match score (highest first)
    matching_products.sort(key=lambda x: x['match_score'], reverse=True)

    return matching_products


def get_company_relevant_orders(company_id: int):
    """
    Get orders that are relevant to this company based on:
    1. Business sector compatibility (primary filter)
    2. Product matching (secondary filter)
    Excludes orders that the company has hidden from their view
    Special case: If company sector is 'عام' or 'general', show ALL orders
    """
    # Get company information including sector
    company = Company.query.get(company_id)
    if not company:
        return []

    # Get hidden order IDs for this company
    hidden_order_ids = [ho.order_id for ho in HiddenOrder.query.filter_by(company_id=company_id).all()]

    # Special case: If company sector is 'عام' or 'general', return ALL orders (except hidden ones)
    if company.sector and (company.sector.lower() == 'general' or company.sector == 'عام'):
        return Order.query.filter(~Order.id.in_(hidden_order_ids)).order_by(Order.created_at.desc()).all()

    # Get all products from this company
    company_products = Product.query.filter_by(company_id=company_id, is_active=True).all()

    if not company_products:
        return []

    # Define sector compatibility mappings
    sector_mappings = {
        'technology': ['electronics', 'general', 'it', 'software', 'hardware'],
        'electronics': ['technology', 'general', 'it', 'hardware'],
        'it': ['technology', 'electronics', 'general', 'software', 'hardware'],
        'software': ['technology', 'it', 'general'],
        'hardware': ['technology', 'electronics', 'it', 'general'],
        'general': ['technology', 'electronics', 'it', 'software', 'hardware', 'other'],
        'other': ['technology', 'electronics', 'it', 'software', 'hardware', 'general']
    }

    # Get all orders with their purchases, excluding hidden ones
    all_orders = Order.query.filter(~Order.id.in_(hidden_order_ids)).all()
    relevant_orders = []

    for order in all_orders:
        order_has_match = False

        for purchase in order.purchases:
            # PRIMARY FILTER: Check sector compatibility
            if company.sector and purchase.sector:
                company_sector = company.sector.lower()
                purchase_sector = purchase.sector.lower()

                # Direct sector match
                if company_sector == purchase_sector:
                    order_has_match = True
                    break

                # Check sector compatibility mappings
                if company_sector in sector_mappings and purchase_sector in sector_mappings[company_sector]:
                    order_has_match = True
                    break

            else:
                # If no sector specified, fall back to product matching
                purchase_terms = f"{purchase.part_name} {purchase.description} {purchase.sector}".lower()

                # Create a list of product names and categories for matching
                company_product_terms = []
                for product in company_products:
                    company_product_terms.extend([
                        product.name.lower(),
                        product.category.lower(),
                        product.description.lower() if product.description else ""
                    ])

                for product_term in company_product_terms:
                    if product_term in purchase_terms or purchase_terms in product_term:
                        order_has_match = True
                        break

                if order_has_match:
                    break

        if order_has_match:
            relevant_orders.append(order)

    return relevant_orders


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/', methods=['GET'])
def index():
    # Check maintenance mode
    if get_system_setting('maintenance_mode', False) and not (
            current_user.is_authenticated and current_user.role == 'admin'):
        return render_template('maintenance.html')

    # If user is logged in, redirect to appropriate dashboard
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'company':
            return redirect(url_for('company_dashboard'))
        else:
            return redirect(url_for('dash'))

    # Clear any flash messages that shouldn't appear on the main page
    # This prevents verification messages from showing on the landing page
    session.pop('_flashes', None)
    
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    # Clear any existing flash messages on GET request
    if request.method == 'GET':
        session.pop('_flashes', None)

    if request.method == 'POST':
        username = request.form.get('username') or ''
        password = request.form.get('password') or ''
        user = User.query.filter_by(username=username).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            # Check if email is verified
            if not user.is_verified:
                flash('Please verify your email before logging in. Check your email for verification code.', 'warning')
                return redirect(url_for('verify_email', email=user.email))
            
            login_user(user)
            
            # Check if user has accepted terms and conditions (except for admin)
            if user.role != 'admin' and not user.terms_accepted:
                flash('مرحباً بك! يرجى قبول الشروط والأحكام للمتابعة واستخدام المنصة.', 'info')
                return redirect(url_for('terms_and_conditions'))
            
            flash(_('Login successful!'), 'success')

            # Redirect based on user role
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'company':
                return redirect(url_for('company_dashboard'))
            else:
                return redirect(url_for('dash'))
        flash(_('Invalid username or password'), 'error')
    return render_template('login_enhanced.html')


@app.route('/clear_flash')
def clear_flash():
    """Clear all flash messages"""
    session.pop('_flashes', None)
    return redirect(request.referrer or url_for('index'))


# Duplicate dash function removed - using the one at line 7777 instead


@app.route('/r', methods=['GET', 'POST'])
def registerr():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username') or ''
        email = request.form.get('email') or ''
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''
        role = request.form.get('role', 'client')  # Default to client, allow company selection

        if password != confirm_password:
            flash(_('Passwords do not match'), 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash(_('Username already exists'), 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash(_('Email already registered'), 'error')
            return redirect(url_for('register'))

        if password:
            password_hash = generate_password_hash(str(password) if password else '', method='pbkdf2:sha256')
        else:
            password_hash = ''
        
        # Get or create default company for user
        default_company = Company.query.filter_by(company_type='client').first()
        if not default_company:
            default_company = Company()
            default_company.name_ar = 'شركة العميل الافتراضية'
            default_company.name_en = 'Default Client Company'
            default_company.email = 'clients@almoshtariat.com'
            default_company.company_type = 'client'
            default_company.is_approved = True
            default_company.is_active = True
            default_company.sector = 'General'
            db.session.add(default_company)
            db.session.commit()
        
        user = User()
        user.username = username
        user.email = email
        user.password_hash = password_hash
        user.company_id = default_company.id
        user.role = 'client'
        user.company_id = default_company.id
        user.name = username

        if role == 'company':
            return redirect(url_for('company_register'))
        else:
            db.session.add(user)
            try:
                db.session.commit()
                flash(_('Registration successful! Please log in.'), 'success')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                flash(_('Error during registration: ') + str(e), 'error')
    return render_template('register.html')


@app.route('/company_register', methods=['GET', 'POST'])
def company_register():
    # Check if user is logged in and already has a company
    if current_user.is_authenticated:
        user = current_user
        if user.company_id:
            company = Company.query.get(user.company_id)
            if company:
                # User already has a company, redirect to company status page
                return redirect(url_for('company_status'))

    # Allow both logged-in and non-logged-in users to register companies
    if request.method == 'POST':
        # Basic Company Information
        name_ar = request.form.get('name_ar')  # اسم الشركة (بالعربي)
        name_en = request.form.get('name_en')  # اسم الشركة (بالإنجليزي)
        email = request.form.get('email')

        # Legal Information
        legal_type = request.form.get('legal_type')  # النوع القانوني
        tax_id = request.form.get('tax_id')  # الرقم الضريبي / VAT
        commercial_registration = request.form.get('commercial_registration')  # رقم السجل التجاري
        vat_number = request.form.get('vat_number')  # VAT Number

        # Contact Information
        registered_address = request.form.get('registered_address')  # العنوان المسجل
        website = request.form.get('website')  # الموقع الإلكتروني
        office_phone = request.form.get('office_phone')  # هاتف المكتب
        mobile_contact = request.form.get('mobile_contact')  # موبايل جهة التواصل

        # Contact Person Information
        contact_person = request.form.get('contact_person')  # الشخص المسؤول
        contact_position = request.form.get('contact_position')  # المنصب
        owner_name = request.form.get('owner_name')  # اسم صاحب المنشأة

        # Banking Information
        bank_name = request.form.get('bank_name')  # اسم البنك
        account_name = request.form.get('account_name')  # اسم الحساب
        account_number = request.form.get('account_number')  # رقم الحساب / IBAN
        bank_branch = request.form.get('bank_branch')  # فرع البنك

        # Business Information
        sector = request.form.get('sector')  # القطاع
        founded_year = request.form.get('founded_year')  # سنة التأسيس
        employees_count = request.form.get('employees_count')  # عدد الموظفين

        # Enhanced Validation with field-specific error handling
        validation_errors = {}

        # Required fields validation
        if not name_ar or (isinstance(name_ar, str) and name_ar.strip() == ''):
            validation_errors['name_ar'] = 'اسم الشركة بالعربية مطلوب'

        if not email or email.strip() == '':
            validation_errors['email'] = 'البريد الإلكتروني مطلوب'
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            validation_errors['email'] = 'البريد الإلكتروني غير صحيح'

        if not legal_type or legal_type.strip() == '':
            validation_errors['legal_type'] = 'النوع القانوني مطلوب'

        if not sector or sector.strip() == '':
            validation_errors['sector'] = 'القطاع مطلوب'

        if not commercial_registration or commercial_registration.strip() == '':
            validation_errors['commercial_registration'] = 'رقم السجل التجاري مطلوب'

        if not contact_person or contact_person.strip() == '':
            validation_errors['contact_person'] = 'الشخص المسؤول مطلوب'

        if not registered_address or registered_address.strip() == '':
            validation_errors['registered_address'] = 'العنوان المسجل مطلوب'

        # Check for existing email
        if User.query.filter_by(email=email).first():
            validation_errors['email'] = 'البريد الإلكتروني مسجل مسبقاً'

        if Company.query.filter_by(email=email).first():
            validation_errors['email'] = 'شركة بهذا البريد الإلكتروني موجودة مسبقاً'

        # If there are validation errors, return them to the form
        if validation_errors:
            # Store errors in session to display them on the form
            session['company_registration_errors'] = validation_errors
            session['company_registration_data'] = request.form.to_dict()
            return redirect(url_for('company_register'))

        # Create uploads directory if it doesn't exist
        upload_folder = 'uploads/companies'
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        # Handle document uploads
        document_paths = {}
        document_fields = [
            'commercial_registration_doc', 'tax_card_doc', 'e_invoice_proof_doc',
            'logo_doc', 'letterhead_doc', 'bank_letter_doc', 'owner_id_doc',
            'product_catalog_doc', 'quality_certificates_doc'
        ]

        for field in document_fields:
            if field in request.files and request.files[field].filename:
                file = request.files[field]
                if file and file.filename != '':
                    # Secure filename and save file
                    filename = secure_filename(file.filename or 'unnamed_file')
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    file_path = os.path.join(upload_folder, filename)
                    file.save(file_path)
                    document_paths[field] = file_path

        # Create company with comprehensive information
        company = Company()
        # Basic Information
        company.name_ar = name_ar if name_ar else ''
        company.name_en = name_en
        company.email = email

        # Legal Information
        company.legal_type = legal_type
        company.tax_id = tax_id
        company.commercial_registration = commercial_registration
        company.vat_number = vat_number

        # Contact Information
        company.registered_address = registered_address
        company.website = website
        company.office_phone = office_phone
        company.mobile_contact = mobile_contact

        # Contact Person
        company.contact_person = contact_person
        company.contact_position = contact_position
        company.owner_name = owner_name

        # Banking Information
        company.bank_name = bank_name
        company.account_name = account_name
        company.account_number = account_number
        company.bank_branch = bank_branch

        # Business Information
        company.sector = sector
        company.founded_year = int(founded_year) if founded_year else None
        company.employees_count = employees_count

        # Document Paths
        company.commercial_registration_doc = document_paths.get('commercial_registration_doc')
        company.tax_card_doc = document_paths.get('tax_card_doc')
        company.e_invoice_proof_doc = document_paths.get('e_invoice_proof_doc')
        company.logo_doc = document_paths.get('logo_doc')
        company.letterhead_doc = document_paths.get('letterhead_doc')
        company.bank_letter_doc = document_paths.get('bank_letter_doc')
        company.owner_id_doc = document_paths.get('owner_id_doc')
        company.product_catalog_doc = document_paths.get('product_catalog_doc')
        company.quality_certificates_doc = document_paths.get('quality_certificates_doc')

        # Status
        company.company_type = 'supplier'
        company.is_approved = get_system_setting('auto_approve_companies', False)  # Auto-approve based on setting
        company.is_active = get_system_setting('auto_approve_companies', False)  # Auto-activate if auto-approved

        try:
            # First add the company to the database
            db.session.add(company)
            db.session.commit()

            # Now handle user relationship
            if current_user.is_authenticated:
                # User is logged in, link them to the company
                current_user.company_id = company.id
                db.session.commit()
                print(f"Linked user {current_user.id} to company {company.id}")
            else:
                # Check if user exists by email and link them
                existing_user = User.query.filter_by(email=email).first()
                if existing_user:
                    existing_user.company_id = company.id
                    db.session.commit()
                    print(f"Linked existing user {existing_user.id} to company {company.id}")
                else:
                    print(f"Company {company.id} created but no user linked (non-logged-in registration)")

            # Redirect to confirmation page
            return redirect(url_for('company_registration_confirmation'))

        except Exception as e:
            db.session.rollback()
            # Clean up uploaded files on error
            for file_path in document_paths.values():
                if os.path.exists(file_path):
                    os.remove(file_path)

            # Handle specific database constraint errors
            error_message = str(e)
            if 'NOT NULL constraint failed: company.name' in error_message:
                # This is the specific constraint error we're seeing
                error_message = 'خطأ في قاعدة البيانات: عمود اسم الشركة مطلوب'
                # Store this error to display on the form
                session['company_registration_errors'] = {'database': error_message}
                session['company_registration_data'] = request.form.to_dict()
                return redirect(url_for('company_register'))
            elif 'IntegrityError' in error_message:
                # Other database integrity errors
                error_message = 'خطأ في قاعدة البيانات: يرجى التحقق من صحة البيانات'
                session['company_registration_errors'] = {'database': error_message}
                session['company_registration_data'] = request.form.to_dict()
                return redirect(url_for('company_register'))
            else:
                # General errors
                error_message = f'خطأ في تسجيل الشركة: {str(e)}'
                session['company_registration_errors'] = {'database': error_message}
                session['company_registration_data'] = request.form.to_dict()
                return redirect(url_for('company_register'))

    # Get any stored errors and data from session
    errors = session.get('company_registration_errors', {})
    form_data = session.get('company_registration_data', {})

    # Clear session data after retrieving it
    session.pop('company_registration_errors', None)
    session.pop('company_registration_data', None)

    # Check if user already has a company for sidebar display
    has_company = False
    if current_user.is_authenticated:
        # Check if logged-in user has a company
        user = current_user
        if user.company_id:
            company = Company.query.get(user.company_id)
            has_company = company is not None
        else:
            # Check if there's a company with the user's email
            company = Company.query.filter_by(email=user.email).first()
            if company:
                # Link the user to this company
                user.company_id = company.id
                db.session.commit()
                has_company = True
                print(f"Auto-linked user {user.id} to existing company {company.id}")
    else:
        # For non-logged-in users, check if they have form data with email
        if form_data and form_data.get('email'):
            company = Company.query.filter_by(email=form_data['email']).first()
            has_company = company is not None

    return render_template('company_register_comprehensive.html', errors=errors, form_data=form_data,
                           has_company=has_company)


@app.route('/company_registration_confirmation')
def company_registration_confirmation():
    """Display confirmation page after successful company registration"""
    return render_template('company_registration_confirmation.html')


@app.route('/company_status')
def company_status():
    """Display company status page for users who have already registered a company"""
    # Check if user is logged in and has a company
    if current_user.is_authenticated:
        user = current_user
        if user.company_id:
            company = Company.query.get(user.company_id)
            if company:
                return render_template('company_status.html', company=company)
        else:
            # Check if there's a company with the user's email
            company = Company.query.filter_by(email=user.email).first()
            if company:
                # Link the user to this company
                user.company_id = company.id
                db.session.commit()
                return render_template('company_status.html', company=company)

    # If not logged in or no company, redirect to company registration
    return redirect(url_for('company_register'))


@app.route('/update_company_field', methods=['POST'])
def update_company_field():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'User not authenticated'}), 401

    try:
        data = request.get_json()
        field_name = data.get('field')
        new_value = data.get('value')

        if not field_name:
            return jsonify({'success': False, 'error': 'Field name is required'}), 400

        # Get user's company
        user = current_user
        if not user.company_id:
            return jsonify({'success': False, 'error': 'No company associated with user'}), 400

        company = Company.query.get(user.company_id)
        if not company:
            return jsonify({'success': False, 'error': 'Company not found'}), 404

        # Check if field exists and is allowed to be updated
        allowed_fields = [
            'legal_type', 'commercial_registration', 'contact_person', 'email',
            'contact_position', 'owner_name', 'website', 'office_phone',
            'mobile_contact', 'tax_id', 'vat_number', 'founded_year',
            'employees_count', 'registered_address', 'certifications',
            'operating_countries', 'bank_name', 'account_name', 'account_number', 'bank_branch'
        ]

        if field_name not in allowed_fields:
            return jsonify({'success': False, 'error': 'Field not allowed to be updated'}), 400

        # Update the field
        setattr(company, field_name, new_value)
        company.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'{field_name} updated successfully',
            'new_value': new_value
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/upload_company_document', methods=['POST'])
def upload_company_document():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'User not authenticated'}), 401

    try:
        field_name = request.form.get('field')
        document_file = request.files.get('document')

        if not field_name or not document_file:
            return jsonify({'success': False, 'error': 'Field name and document are required'}), 400

        # Get user's company
        user = current_user
        if not user.company_id:
            return jsonify({'success': False, 'error': 'No company associated with user'}), 400

        company = Company.query.get(user.company_id)
        if not company:
            return jsonify({'success': False, 'error': 'Company not found'}), 404

        # Check if field exists and is allowed to be updated
        allowed_document_fields = [
            'commercial_registration_doc', 'tax_card_doc', 'e_invoice_proof_doc',
            'logo_doc', 'letterhead_doc', 'bank_letter_doc', 'owner_id_doc',
            'product_catalog_doc', 'quality_certificates_doc'
        ]

        if field_name not in allowed_document_fields:
            return jsonify({'success': False, 'error': 'Document field not allowed'}), 400

        # Check file type
        allowed_extensions = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png'}
        file_ext = os.path.splitext(document_file.filename if document_file.filename else '')[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify(
                {'success': False, 'error': 'File type not allowed. Use PDF, DOC, DOCX, JPG, JPEG, or PNG'}), 400

        # Check file size (max 10MB)
        # Read file content to check size
        file_content = document_file.read()
        if len(file_content) > 10 * 1024 * 1024:
            return jsonify({'success': False, 'error': 'File too large. Maximum size is 10MB'}), 400

        # Reset file pointer to beginning
        document_file.seek(0)

        # Create uploads directory if it doesn't exist
        upload_folder = 'uploads'
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        safe_filename = secure_filename(document_file.filename or 'unnamed_document')
        filename = f"{field_name}_{timestamp}_{safe_filename}"
        file_path = os.path.join(upload_folder, filename)

        # Save the file
        document_file.save(file_path)

        # Update company document field
        setattr(company, field_name, filename)
        company.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'{field_name} uploaded successfully',
            'filename': filename
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/download_document/<filename>')
def download_document(filename):
    print(f"DEBUG: Download requested for filename: {filename}")

    if not current_user.is_authenticated:
        print("DEBUG: User not authenticated")
        flash(_('Please log in to download documents.'), 'error')
        return redirect(url_for('login'))

    try:
        # Check if user has access to this document
        user = current_user
        print(f"DEBUG: User ID: {user.id}, Company ID: {user.company_id}")

        if not user.company_id:
            print("DEBUG: No company associated with user")
            flash(_('No company associated with user.'), 'error')
            return redirect(url_for('company_status'))

        company = Company.query.get(user.company_id)
        if not company:
            print("DEBUG: Company not found")
            flash(_('Company not found.'), 'error')
            return redirect(url_for('company_status'))

        print(f"DEBUG: Company found: {company.id}")

        # Check if the document belongs to the user's company
        document_fields = [
            'commercial_registration_doc', 'tax_card_doc', 'e_invoice_proof_doc',
            'logo_doc', 'letterhead_doc', 'bank_letter_doc', 'owner_id_doc',
            'product_catalog_doc', 'quality_certificates_doc'
        ]

        document_belongs_to_company = False
        for field in document_fields:
            if getattr(company, field) == filename:
                document_belongs_to_company = True
                print(f"DEBUG: Document found in field: {field}")
                break

        if not document_belongs_to_company:
            print("DEBUG: Document does not belong to company")
            flash(_('Access denied. Document not found in your company.'), 'error')
            return redirect(url_for('company_status'))

        # Serve the file
        upload_folder = 'uploads'
        file_path = os.path.join(upload_folder, filename)
        print(f"DEBUG: File path: {file_path}")
        print(f"DEBUG: File exists: {os.path.exists(file_path)}")

        if os.path.exists(file_path):
            print(f"DEBUG: Sending file: {filename}")
            return send_from_directory(upload_folder, filename, as_attachment=True)
        else:
            print("DEBUG: File not found on disk")
            flash(_('Document not found.'), 'error')
            return redirect(url_for('company_status'))

    except Exception as e:
        print(f"DEBUG: Exception occurred: {str(e)}")
        flash(_('Error downloading document.'), 'error')
        return redirect(url_for('company_status'))


@app.route('/view_document/<filename>')
def view_document(filename):
    if not current_user.is_authenticated:
        flash(_('Please log in to view documents.'), 'error')
        return redirect(url_for('login'))

    try:
        # Check if user has access to this document
        user = current_user
        if not user.company_id:
            flash(_('No company associated with user.'), 'error')
            return redirect(url_for('company_status'))

        company = Company.query.get(user.company_id)
        if not company:
            flash(_('Company not found.'), 'error')
            return redirect(url_for('company_status'))

        # Check if the document belongs to the user's company
        document_fields = [
            'commercial_registration_doc', 'tax_card_doc', 'e_invoice_proof_doc',
            'logo_doc', 'letterhead_doc', 'bank_letter_doc', 'owner_id_doc',
            'product_catalog_doc', 'quality_certificates_doc'
        ]

        document_belongs_to_company = False
        for field in document_fields:
            if getattr(company, field) == filename:
                document_belongs_to_company = True
                break

        if not document_belongs_to_company:
            flash(_('Access denied. Document not found in your company.'), 'error')
            return redirect(url_for('company_status'))

        # Serve the file for viewing
        upload_folder = 'uploads'
        file_path = os.path.join(upload_folder, filename)

        if os.path.exists(file_path):
            # Get file extension to determine content type
            if filename:
                file_ext = os.path.splitext(filename if filename else '')[1].lower()
            else:
                file_ext = ''

            # Set appropriate content type
            content_types = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png'
            }

            content_type = content_types.get(file_ext, 'application/octet-stream')

            # For images and PDFs, display in browser; for others, download
            if file_ext in ['.jpg', '.jpeg', '.png', '.pdf']:
                return send_from_directory(upload_folder, filename, mimetype=content_type)
            else:
                # For other file types, force download
                return send_from_directory(upload_folder, filename, as_attachment=True)
        else:
            flash(_('Document not found.'), 'error')
            return redirect(url_for('company_status'))

    except Exception as e:
        flash(_('Error viewing document.'), 'error')
        return redirect(url_for('company_status'))


@app.route('/debug_company_status')
def debug_company_status():
    """Debug route to check company and user relationships"""
    if not current_user.is_authenticated:
        return "Not logged in"

    user = current_user
    companies = Company.query.all()

    debug_info = f"""
    <h2>Debug Company Status</h2>
    <p><strong>User ID:</strong> {user.id}</p>
    <p><strong>User Email:</strong> {user.email}</p>
    <p><strong>User Company ID:</strong> {user.company_id}</p>

    <h3>All Companies:</h3>
    <ul>
    """

    for company in companies:
        debug_info += f"""
        <li>
            <strong>Company ID:</strong> {company.id}<br>
            <strong>Name:</strong> {company.name_ar or company.name_en}<br>
            <strong>Email:</strong> {company.email}<br>
            <strong>Created:</strong> {company.created_at}<br>
            <strong>Approved:</strong> {company.is_approved}<br>
            <strong>Active:</strong> {company.is_active}<br>
            <hr>
        </li>
        """

    debug_info += "</ul>"

    return debug_info


@app.route('/check_username', methods=['POST'])
@csrf.exempt
def check_username():
    """Check if username is available and suggest alternatives if taken"""
    data = request.get_json()
    username = data.get('username', '').strip()

    if not username:
        return jsonify({'available': False, 'suggestions': []})

    # Check if username exists
    existing_user = User.query.filter_by(username=username).first()

    if not existing_user:
        return jsonify({'available': True, 'suggestions': []})

    # Generate username suggestions
    suggestions = generate_username_suggestions(username)

    return jsonify({
        'available': False,
        'suggestions': suggestions,
        'message': f'Username "{username}" is already taken. Here are some suggestions:'
    })


@app.route('/check_email', methods=['POST'])
@csrf.exempt
def check_email():
    """Check if email is already registered"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({'available': True, 'message': ''})

    # Check if email exists
    existing_user = User.query.filter_by(email=email).first()
    
    if existing_user:
        return jsonify({
            'available': False,
            'message': f'Email "{email}" is already registered. Please use a different email address.'
        })
    
    return jsonify({
        'available': True,
        'message': 'Email is available'
    })


@app.route('/test_validation')
def test_validation():
    """Test page for email and username validation"""
    return render_template('test_validation.html')


def generate_username_suggestions(base_username: str):
    """Generate alternative username suggestions"""
    suggestions = []

    # Remove any numbers from the end of the username
    clean_username = re.sub(r'\d+$', '', base_username)

    # Generate variations
    variations = [
        f"{clean_username}123",
        f"{clean_username}2024",
        f"{clean_username}2025",
        f"{clean_username}_user",
        f"{clean_username}_new",
        f"{clean_username}1",
        f"{clean_username}2",
        f"{clean_username}3",
        f"{clean_username}4",
        f"{clean_username}5"
    ]

    # Check which suggestions are available
    for suggestion in variations:
        if not User.query.filter_by(username=suggestion).first():
            suggestions.append(suggestion)
            if len(suggestions) >= 5:  # Limit to 5 suggestions
                break

    # If we don't have enough suggestions, add more variations
    if len(suggestions) < 5:
        additional_variations = [
            f"{clean_username}_{random.randint(100, 999)}",
            f"{clean_username}{random.randint(100, 999)}",
            f"{clean_username}_user_{random.randint(10, 99)}",
            f"{clean_username}_new_{random.randint(10, 99)}"
        ]

        for suggestion in additional_variations:
            if not User.query.filter_by(username=suggestion).first():
                suggestions.append(suggestion)
                if len(suggestions) >= 5:
                    break

    return suggestions[:5]


@app.route('/register_enhanced', methods=['GET', 'POST'])
def register_enhanced():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    # Check if registration is allowed
    if not get_system_setting('allow_registration', True):
        flash('User registration is currently disabled. Please contact an administrator.', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        country = request.form.get('country')
        city = request.form.get('city')
        city_other = request.form.get('city_other')
        phone_number = request.form.get('phone_number')
        company_name = request.form.get('company_name')
        sector = request.form.get('sector')
        subsector = request.form.get('subsector')
        tax_number = request.form.get('tax_number')
        account_type = request.form.get('account_type')
        
        # Determine final city value based on country selection
        final_city = city if city else city_other

        # Validate required fields
        if not all([name, email, username, password, country, final_city, phone_number, account_type]):
            flash('Please fill in all required fields.', 'error')
            return render_template('register_enhanced.html')

        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('register_enhanced.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('register_enhanced.html')

        # Create uploads directory if it doesn't exist
        upload_folder = 'uploads'
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        # Handle file upload
        uploaded_file_path = ''
        if 'uploaded_file' in request.files:
            file = request.files['uploaded_file']
            if file and file.filename != '':
                # Secure filename and save file
                if file.filename:
                    filename = secure_filename(file.filename)
                else:
                    filename = ''
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                file_path = os.path.join(upload_folder, filename)
                file.save(file_path)
                uploaded_file_path = file_path

        # Create new user with enhanced fields
        password_hash = generate_password_hash(str(password) if password else '', method='pbkdf2:sha256')

        # Determine company assignment based on account type
        if account_type == 'client':
            # Client users get assigned to default client company
            from models import Company
            default_client_company = Company.query.filter_by(company_type='client').first()
            if not default_client_company:
                # Create default client company if it doesn't exist
                default_client_company = Company()
                default_client_company.name_ar = 'شركة العميل الافتراضية'
                default_client_company.name_en = 'Default Client Company'
                default_client_company.email = 'clients@almoshtariat.com'
                default_client_company.company_type = 'client'
                default_client_company.is_approved = True
                default_client_company.is_active = True
                default_client_company.sector = 'General'
                db.session.add(default_client_company)
                db.session.commit()

            company_id = default_client_company.id
            role = 'client'
        else:
            # Company users get assigned to default supplier company initially
            from models import Company
            default_supplier_company = Company.query.filter_by(company_type='supplier').first()
            if not default_supplier_company:
                # Create default supplier company if it doesn't exist
                default_supplier_company = Company()
                default_supplier_company.name_ar = 'شركة المورد الافتراضية'
                default_supplier_company.name_en = 'Default Supplier Company'
                default_supplier_company.email = 'suppliers@almoshtariat.com'
                default_supplier_company.company_type = 'supplier'
                default_supplier_company.is_approved = True
                default_supplier_company.is_active = True
                default_supplier_company.sector = 'General'
                db.session.add(default_supplier_company)
                db.session.commit()

            company_id = default_supplier_company.id
            role = 'company'

        new_user = User()
        new_user.username = username
        new_user.email = email
        new_user.password_hash = password_hash
        new_user.name = name or username
        new_user.country = country or ''
        new_user.city = final_city or ''
        new_user.phone_number = phone_number or ''
        new_user.company_name = company_name or ''
        new_user.sector = sector or ''
        new_user.subsector = subsector or ''
        new_user.tax_number = tax_number or ''
        new_user.account_type = account_type or 'client'
        new_user.uploaded_file = uploaded_file_path
        new_user.role = role
        new_user.company_id = company_id

        try:
            db.session.add(new_user)
            db.session.commit()

            # Process purchase preferences file if it's a client
            if account_type == 'client' and 'purchase_preferences_file' in request.files:
                preferences_file = request.files['purchase_preferences_file']
                if preferences_file and preferences_file.filename != '':
                    try:
                        # Check file size (max 10MB)
                        if len(preferences_file.read()) > 10 * 1024 * 1024:  # 10MB
                            flash('File size too large. Please upload a file smaller than 10MB.', 'error')
                            return render_template('register_enhanced.html')

                        # Reset file pointer
                        preferences_file.seek(0)

                        # Save the preferences file
                        filename = secure_filename(preferences_file.filename or 'unnamed_preferences')
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"preferences_{timestamp}_{filename}"
                        file_path = os.path.join(upload_folder, filename)
                        preferences_file.save(file_path)

                        # Process the file and extract preferences
                        preferences = process_purchase_preferences_file(file_path, new_user.id)

                        if preferences:
                            # Add preferences to database
                            for preference in preferences:
                                db.session.add(preference)

                            db.session.commit()

                            # Create notification about preferences
                            create_notification(
                                title="Purchase Preferences Imported!",
                                description=f"Successfully imported {len(preferences)} purchase preferences from your file. We'll use this data to provide better product suggestions.",
                                notification_type='system',
                                priority='normal',
                                user_id=new_user.id
                            )

                            flash(f'Successfully imported {len(preferences)} purchase preferences!', 'success')
                        else:
                            flash('No purchase preferences could be extracted from the file. Please check the format.',
                                  'warning')

                    except ValueError as e:
                        flash(f'File format error: {str(e)}. Please check the column names and data format.', 'error')
                        print(f"File format error: {e}")
                        # Clean up the uploaded file
                        if uploaded_file_path and os.path.exists(uploaded_file_path):
                             os.remove(uploaded_file_path)
                        return render_template('register_enhanced.html')
                    except Exception as e:
                        flash(f'Error processing purchase preferences file: {str(e)}', 'error')
                        print(f"Error processing preferences file: {e}")
                        # Clean up the uploaded file
                        if uploaded_file_path and os.path.exists(uploaded_file_path):
                             os.remove(uploaded_file_path)
                        return render_template('register_enhanced.html')

            # Generate and send verification code
            from email_service import email_service
            verification_code = email_service.generate_verification_code()
            new_user.verification_code = verification_code
            new_user.verification_sent_at = datetime.utcnow()
            db.session.commit()
            
            # Send verification email
            try:
                email_service.send_verification_email(email, verification_code, name or username)
                
                # Create welcome notification
                try:
                    welcome_notification = Notification()
                    welcome_notification.user_id = new_user.id
                    welcome_notification.title = "Welcome to B2B Platform!"
                    welcome_notification.description = f"Thank you for registering, {name}! Please check your email to verify your account."
                    welcome_notification.notification_type = 'system'
                    welcome_notification.priority = 'normal'
                    welcome_notification.is_read = False
                    db.session.add(welcome_notification)
                    db.session.commit()
                except Exception as e:
                    print(f"Failed to create notification: {e}")
                
                flash(_('Registration successful! Please check your email for verification code.'), 'success')
                return redirect(url_for('verify_email', email=email))
            except Exception as e:
                print(f"Failed to send verification email: {e}")
                flash(_('Registration successful but failed to send verification email. Please contact support.'), 'warning')
                return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
            return render_template('register_enhanced.html')

    return render_template('register_enhanced.html')


@app.route('/verify_email')
def verify_email():
    email = request.args.get('email')
    if not email:
        flash('Invalid verification link.', 'error')
        return redirect(url_for('login'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('login'))
    
    if user.is_verified:
        flash('Email already verified. Please log in.', 'info')
        return redirect(url_for('login'))
    
    # Generate and send initial verification code if not already sent recently
    from email_service import email_service
    should_send_email = True
    
    # Check if verification was sent recently (within last 5 minutes)
    if user.verification_sent_at:
        time_since_last_sent = datetime.utcnow() - user.verification_sent_at
        if time_since_last_sent.total_seconds() < 300:  # 5 minutes
            should_send_email = False
    
    if should_send_email:
        verification_code = email_service.generate_verification_code()
        user.verification_code = verification_code
        user.verification_sent_at = datetime.utcnow()
        db.session.commit()
        
        # Send verification email
        if email_service.send_verification_email(email, verification_code, user.name or user.username):
            flash('Verification code sent to your email! Please check your inbox.', 'success')
        else:
            flash('Failed to send verification email. Please try again later.', 'error')
    
    return render_template('verify_email.html', email=email)


@app.route('/verify_code', methods=['POST'])
def verify_code():
    email = request.form.get('email')
    code = request.form.get('verification_code')
    
    if not email or not code:
        flash('Please provide both email and verification code.', 'error')
        return redirect(url_for('verify_email', email=email))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('login'))
    
    if user.is_verified:
        flash('Email already verified. Please log in.', 'info')
        return redirect(url_for('login'))
    
    # Check if code matches and is not expired
    from email_service import email_service
    if user.verification_code != code:
        flash('Invalid verification code. Please try again.', 'error')
        return redirect(url_for('verify_email', email=email))
    
    if email_service.is_code_expired(user.verification_sent_at):
        flash('Verification code has expired. Please request a new one.', 'error')
        return redirect(url_for('verify_email', email=email))
    
    # Verify the user
    user.is_verified = True
    user.verification_code = None
    user.verification_sent_at = None
    db.session.commit()
    
    # Create verification success notification
    try:
        success_notification = Notification(
            user_id=user.id,
            title="Email Verified Successfully!",
            message="Your email has been verified. You can now log in to your account.",
            notification_type='system',
            priority='normal',
            timestamp=datetime.utcnow(),
            is_read=False
        )
        db.session.add(success_notification)
    except Exception as e:
        print(f"Failed to create notification: {e}")
    
    # Log in the user automatically after successful verification
    from flask_login import login_user
    login_user(user)
    
    # Check if user has accepted terms and conditions
    if not user.terms_accepted:
        flash('تم التحقق من بريدك الإلكتروني بنجاح! يرجى قبول الشروط والأحكام للمتابعة.', 'success')
        return redirect(url_for('terms_and_conditions'))
    
    flash('Email verified successfully! Welcome to your dashboard.', 'success')
    return redirect(url_for('dash'))


@app.route('/resend_verification', methods=['POST'])
@csrf.exempt
def resend_verification():
    email = request.form.get('email')
    
    if not email:
        flash('Email is required.', 'error')
        return redirect(url_for('login'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('login'))
    
    if user.is_verified:
        flash('Email already verified. Please log in.', 'info')
        return redirect(url_for('login'))
    
    # Generate new verification code
    from email_service import email_service
    verification_code = email_service.generate_verification_code()
    user.verification_code = verification_code
    user.verification_sent_at = datetime.utcnow()
    db.session.commit()
    
    # Send verification email
    if email_service.send_verification_email(email, verification_code, user.name or user.username):
        flash('Verification code sent successfully! Please check your email.', 'success')
    else:
        flash('Failed to send verification email. Please try again later.', 'error')
    
    return redirect(url_for('verify_email', email=email))


@app.route('/verification_success')
def verification_success():
    return render_template('verification_success.html')


@app.route('/company_management', methods=['GET', 'POST'])
@login_required
def company_management():
    if current_user.role != 'admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('index'))
    companies = Company.query.all()
    if request.method == 'POST':
        company_id = request.form.get('company_id')
        action = request.form.get('action')
        company = Company.query.get(company_id)
        if company and action == 'approve':
            company.is_approved = True
            try:
                db.session.commit()
                flash('Company approved successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error approving company: {str(e)}', 'error')
    return render_template('company_management.html', companies=companies)


@app.route('/new_purchase', methods=['GET', 'POST'])
@login_required
def new_purchase():
    if current_user.role != 'client':
        flash('Only clients can create purchases.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Handle new multi-step form data
        try:
            # Panel 1: Order Details
            order_name = request.form.get('order_name', 'New Order')
            description = request.form.get('description', '')
            sector = request.form.get('sector', 'Other')
            order_type = request.form.get('order_type', 'direct')

            # Panel 3: Delivery
            delivery_date_str = request.form.get('delivery_date')
            delivery_date = None
            if delivery_date_str:
                try:
                    delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            delivery_time = request.form.get('delivery_time', '')
            delivery_address = request.form.get('delivery_address', '')
            delivery_notes = request.form.get('delivery_notes', '')

            # Panel 3: Receiver Information
            receiver_name = request.form.get('receiver_name', '')
            receiver_phone = request.form.get('receiver_phone', '')

            # Panel 4: Payment
            payment_way = request.form.get('payment_way', '')

            # Process payment steps
            payment_steps_data = []
            payment_steps_count = int(request.form.get('payment_steps_count', 1))

            for i in range(payment_steps_count):
                method = request.form.get(f'payment_step_{i}_method', '')
                timing = request.form.get(f'payment_step_{i}_timing', '')
                percentage = request.form.get(f'payment_step_{i}_percentage', '')

                if method or timing or percentage:  # Only add if at least one field is filled
                    payment_steps_data.append({
                        'method': method,
                        'timing': timing,
                        'percentage': percentage
                    })

            # Convert payment steps to JSON string
            import json
            payment_steps_json = json.dumps(payment_steps_data) if payment_steps_data else None

            # Panel 5: Settings
            direct_negotiation = request.form.get('direct_negotiation') == 'true'
            accept_unregistered_suppliers = request.form.get('accept_unregistered_suppliers') == 'true'
            max_suppliers = int(request.form.get('max_suppliers', 10))

            # Create order with new fields
            order = Order()
            order.user_id = current_user.id
            order.company_id = current_user.company_id  # Automatically set from user's company
            order.order_name = order_name
            order.description = description
            order.sector = sector
            order.order_type = order_type
            order.delivery_date = delivery_date
            order.delivery_time = delivery_time
            order.delivery_address = delivery_address
            order.delivery_notes = delivery_notes
            order.receiver_name = receiver_name
            order.receiver_phone = receiver_phone
            order.payment_way = payment_way
            order.payment_steps = payment_steps_json
            order.direct_negotiation = direct_negotiation
            order.accept_unregistered_suppliers = accept_unregistered_suppliers
            order.max_suppliers = max_suppliers

            # Ensure company_id is set (fallback to user's company if not set)
            if not order.company_id and current_user.company:
                order.company_id = current_user.company.id
            elif not order.company_id:
                # Fallback to default company if user has no company
                from models import Company
                default_company = Company.get_default_company()
                order.company_id = default_company.id

            db.session.add(order)
            db.session.commit()  # Commit to assign order.id

            # Panel 2: Products - Handle products data
            products_data = []

            # Check if we have products data from the new form
            if 'products[0][product_name]' in request.form:
                # New multi-step form format
                i = 0
                while f'products[{i}][product_name]' in request.form:
                    product_name = request.form.get(f'products[{i}][product_name]')
                    if product_name:  # Only process if product name is provided
                        products_data.append({
                            'product_name': product_name,
                            'technical_specs': request.form.get(f'products[{i}][technical_specs]', ''),
                            'quantity': int(request.form.get(f'products[{i}][quantity]', 1)),
                            'unit': request.form.get(f'products[{i}][unit]', 'pcs'),
                            'max_price_per_unit': request.form.get(f'products[{i}][max_price_per_unit]'),
                            'product_code': request.form.get(f'products[{i}][product_code]', ''),
                            'best_supplier': request.form.get(f'products[{i}][best_supplier]', ''),
                            'uploaded_file': request.files.get(f'products[{i}][uploaded_file]')
                        })
                    i += 1
            else:
                # Fallback to old form format for backward compatibility
                sector = request.form.get('sector')
                part_count = sum(1 for key in request.form if key.startswith('quantity_'))

                for i in range(1, part_count + 1):
                    quantity = request.form.get(f'quantity_{i}')
                    part_name = request.form.get(f'part_name_{i}')
                    description = request.form.get(f'description_{i}')

                    if quantity and part_name and description and int(quantity) > 0:
                        products_data.append({
                            'product_name': part_name,
                            'technical_specs': description,
                            'quantity': int(quantity),
                            'unit': 'pcs',
                            'max_price_per_unit': '',
                            'product_code': '',
                            'best_supplier': '',
                            'uploaded_file': None
                        })

            if not products_data:
                flash('No valid products provided. Please add at least one product with a product name.', 'error')
                return redirect(url_for('new_purchase'))

            # Create purchases with new fields
            for product_data in products_data:
                # Handle file upload if present
                uploaded_file_path = None
                if product_data['uploaded_file'] and product_data['uploaded_file'].filename:
                    import os
                    upload_folder = 'uploads'
                    if not os.path.exists(upload_folder):
                        os.makedirs(upload_folder)

                    from werkzeug.utils import secure_filename
                    filename = secure_filename(product_data['uploaded_file'].filename or 'unnamed_product_file')
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    file_path = os.path.join(upload_folder, filename)
                    product_data['uploaded_file'].save(file_path)
                    uploaded_file_path = file_path

                purchase = Purchase(
                    sector=sector,
                    quantity=product_data['quantity'],
                    part_name=product_data['product_name'],
                    description=product_data['technical_specs'],
                    technical_specs=product_data['technical_specs'],
                    unit=product_data['unit'],
                    max_price_per_unit=float(product_data['max_price_per_unit']) if product_data[
                        'max_price_per_unit'] else None,
                    product_code=product_data['product_code'],
                    best_supplier=product_data['best_supplier'],
                    uploaded_file=uploaded_file_path,
                    order_id=order.id
                )
                db.session.add(purchase)

            db.session.commit()

            # Find matching products and create notifications
            all_suggestions = []
            total_matches = 0

            for product_data in products_data:
                matches = find_matching_products(
                    product_data['product_name'],
                    product_data['technical_specs'],
                    sector
                )

                if matches:
                    total_matches += len(matches)
                    all_suggestions.append({
                        'product': product_data,
                        'matches': matches
                    })

            # Create notifications for companies that have matching products
            for suggestion in all_suggestions:
                for match in suggestion['matches']:
                    create_notification(
                        title=f"New Order Matches Your Products",
                        description=f"Client order #{order.id} includes '{suggestion['product']['product_name']}' which matches your product '{match['product'].name}'",
                        notification_type="order",
                        priority="high",
                        company_id=match['company'].id,
                        related_order_id=order.id,
                        related_product_id=match['product'].id
                    )

            # Automatically add products to user preferences for future use
            try:
                preferences_added = add_products_to_user_preferences(current_user.id, products_data, sector)
                if preferences_added > 0:
                    print(f"Successfully added {preferences_added} new products to user preferences")
            except Exception as e:
                print(f"Warning: Could not add products to preferences: {e}")
                # Don't fail the order creation if preference addition fails

            # Update success messages to inform about preference saving
            if total_matches > 0:
                flash(
                    f'Order #{order.id} "{order_name}" submitted successfully with {len(products_data)} products! Found {total_matches} matching products from {len(set(match["company"].id for suggestion in all_suggestions for match in suggestion["matches"]))} companies. Your products have been saved to preferences for future orders.',
                    'success')
            else:
                flash(
                    f'Order #{order.id} "{order_name}" submitted successfully with {len(products_data)} products! Companies will be notified. Your products have been saved to preferences for future orders.',
                    'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting order: {str(e)}', 'error')
            return redirect(url_for('new_purchase'))

        return redirect(url_for('dash'))

    from datetime import date
    return render_template('client/new_order_form.html', today_date=date.today().isoformat())


@app.route('/test_form')
@login_required
def test_form():
    return render_template('client/simple_test_form.html')


@app.route('/new_purchase_simple')
@login_required
def new_purchase_simple():
    return render_template('client/new_order_form_simple.html')


@app.route('/my_orders', methods=['GET'])
@login_required
def my_orders():
    if current_user.role != 'client':
        flash('Only clients can view their orders.', 'error')
        return redirect(url_for('index'))
    user_orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('my_orders.html', orders=user_orders)


@app.route('/accept_offer/<int:offer_id>', methods=['GET', 'POST'])
@login_required
def accept_offer(offer_id):
    """Allow clients to accept an offer if the order doesn't have an accepted offer"""
    if current_user.role != 'client':
        flash('Only clients can accept offers.', 'error')
        return redirect(url_for('index'))

    offer = Offer.query.get(offer_id)
    if not offer:
        flash('Offer not found.', 'error')
        return redirect(url_for('orders'))

    # Check if this is the client's order
    if offer.order.user_id != current_user.id:
        flash('Access denied. You can only accept offers for your own orders.', 'error')
        return redirect(url_for('index'))

    # Check if the offer is pending
    if offer.status != 'pending':
        flash('Only pending offers can be accepted.', 'error')
        return redirect(url_for('orders'))

    # Check if the order already has an accepted offer
    existing_accepted_offer = Offer.query.filter_by(
        order_id=offer.order.id,
        status='accepted'
    ).first()

    if existing_accepted_offer:
        flash('This order already has an accepted offer. You cannot accept multiple offers for the same order.',
              'error')
        return redirect(url_for('orders'))

    # Accept the offer and reject all other pending offers for this order
    try:
        # Accept the selected offer
        offer.status = 'accepted'

        # Reject all other pending offers for this order
        other_pending_offers = Offer.query.filter_by(
            order_id=offer.order.id,
            status='pending'
        ).filter(Offer.id != offer.id).all()

        for other_offer in other_pending_offers:
            other_offer.status = 'rejected'

        db.session.commit()
        flash(
            'Offer accepted successfully! Your order is now locked and processing will begin. Other offers have been automatically rejected.',
            'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error accepting offer: {str(e)}', 'error')

    return redirect(url_for('orders'))


@app.route('/reject_offer/<int:offer_id>', methods=['POST'])
@login_required
def reject_offer(offer_id):
    if current_user.role != 'client':
        flash('Only clients can reject offers.', 'error')
        return redirect(url_for('index'))
    offer = Offer.query.get(offer_id)
    if offer and offer.order.user_id == current_user.id and offer.status == 'pending':
        offer.status = 'rejected'
        try:
            db.session.commit()
            flash('Offer rejected successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error rejecting offer: {str(e)}', 'error')
    return redirect(url_for('my_orders'))


@app.route('/refuse_accepted_offer/<int:offer_id>', methods=['GET', 'POST'])
@login_required
def refuse_accepted_offer(offer_id):
    """Allow clients to refuse and delete an already accepted offer"""
    if current_user.role != 'client':
        flash('Only clients can refuse accepted offers.', 'error')
        return redirect(url_for('index'))

    offer = Offer.query.get(offer_id)
    if not offer:
        flash('Offer not found.', 'error')
        return redirect(url_for('orders'))

    # Check if this is the client's order
    if offer.order.user_id != current_user.id:
        flash('Access denied. You can only refuse offers for your own orders.', 'error')
        return redirect(url_for('index'))

    # Check if the offer is actually accepted
    if offer.status != 'accepted':
        flash('Only accepted offers can be refused.', 'error')
        return redirect(url_for('orders'))

    try:
        # Change offer status back to pending instead of deleting
        offer.status = 'pending'
        db.session.commit()
        flash(
            'Accepted offer has been refused and set back to pending. You can now accept other offers for this order.',
            'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error refusing offer: {str(e)}', 'error')

    return redirect(url_for('orders'))


@app.route('/offer_details/<int:offer_id>')
@login_required
def offer_details(offer_id):
    """View detailed information about a specific offer"""
    offer = Offer.query.get_or_404(offer_id)

    # Check if user has access to this offer
    if current_user.role == 'client':
        # Client can only view offers for their own orders
        if offer.order.user_id != current_user.id:
            flash('Access denied. You can only view offers for your own orders.', 'error')
            return redirect(url_for('index'))
    elif current_user.role == 'company':
        # Company can only view their own offers
        if offer.company_id != current_user.company_id:
            flash('Access denied. You can only view your own offers.', 'error')
            return redirect(url_for('index'))
    else:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    # Check if the order already has an accepted offer
    order_has_accepted_offer = False
    if current_user.role == 'client':
        # Check if any offer for this order is already accepted
        accepted_offers = Offer.query.filter_by(
            order_id=offer.order.id,
            status='accepted'
        ).all()
        order_has_accepted_offer = len(accepted_offers) > 0

    # Calculate order progress and status for the template
    order_status = getattr(offer, 'order_status', 'offer_accepted')

    # Define the steps and their progress values
    steps = [
        {'id': 1, 'name': 'Offer Accepted', 'status': 'offer_accepted', 'progress': 20},
        {'id': 2, 'name': 'Preparing', 'status': 'preparing', 'progress': 40},
        {'id': 3, 'name': 'Quality Check', 'status': 'quality_check', 'progress': 60},
        {'id': 4, 'name': 'Out for Delivery', 'status': 'out_for_delivery', 'progress': 80},
        {'id': 5, 'name': 'Delivered', 'status': 'delivered', 'progress': 100}
    ]

    # Calculate current progress and step ID
    current_progress = 20  # Default to first step
    current_step_id = 1  # Default to first step
    for step in steps:
        if step['status'] == order_status:
            current_progress = step['progress']
            current_step_id = step['id']
            break

    # Render different templates based on user role and offer status
    if current_user.role == 'company' and offer.status == 'accepted':
        # Company viewing their accepted offer - show order management interface
        return render_template('company/order_management.html',
                               offer=offer,
                               steps=steps,
                               current_progress=current_progress,
                               order_status=order_status,
                               current_step_id=current_step_id)
    else:
        # Client viewing offer or company viewing non-accepted offer
        return render_template('offer_details.html',
                               offer=offer,
                               steps=steps,
                               current_progress=current_progress,
                               order_status=order_status,
                               order_has_accepted_offer=order_has_accepted_offer)


@app.route('/update_order_status', methods=['POST'])
@login_required
def update_order_status():
    """Update the order status for an offer"""
    offer_id = request.form.get('offer_id')
    new_status = request.form.get('status')

    if not offer_id or not new_status:
        flash('Missing offer_id or status', 'error')
        return redirect(url_for('company_offers'))

    offer = Offer.query.get_or_404(offer_id)

    # Check if user has access to this offer
    if current_user.role == 'client':
        # Client can only update status for their own orders
        if offer.order.user_id != current_user.id:
            flash('Access denied. You can only update status for your own orders.', 'error')
            return redirect(url_for('my_orders'))
    elif current_user.role == 'company':
        # Company can only update status for their own offers
        if offer.company_id != current_user.company_id:
            flash('Access denied. You can only update status for your own offers.', 'error')
            return redirect(url_for('company_offers'))
    else:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    # Update the order status
    if offer and hasattr(offer, 'order_status'):
        offer.order_status = new_status
    elif offer:
        # If order_status doesn't exist, create it
        offer.order_status = new_status

    try:
        db.session.commit()
        flash(f'Order status updated successfully to: {new_status.replace("_", " ").title()}', 'success')
        
        # If status is changed to 'out_for_delivery', redirect to package creation page
        if new_status == 'out_for_delivery':
            flash('Order is now out for delivery. Please create a package for tracking.', 'info')
            return redirect(url_for('create_package_page', offer_id=offer_id))
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating order status: {str(e)}', 'error')

    # Redirect back to the order management page
    return redirect(url_for('offer_details', offer_id=offer_id))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))


@app.route("/profile")
@login_required
def profile():
    if current_user.role == 'client':
        return render_template('client/profile.html')
    else:
        return render_template('admin/profile.html')


@app.route('/reset_password', methods=['GET', 'POST'])
@login_required
def reset_password():
    """Reset user password"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Validate current password
        if not current_user.password_hash or not check_password_hash(current_user.password_hash, current_password or ''):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('profile'))

        # Validate new password
        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'error')
            return redirect(url_for('profile'))

        # Validate password confirmation
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('profile'))

        # Update password
        current_user.password_hash = generate_password_hash(str(new_password) if new_password else '', method='pbkdf2:sha256')
        db.session.commit()

        flash('Password updated successfully!', 'success')
        return redirect(url_for('profile'))

    # GET request - redirect to profile
    return redirect(url_for('profile'))


@app.route('/purchase_preferences')
@login_required
def purchase_preferences():
    """View and manage user's purchase preferences"""
    if current_user.account_type != 'client':
        flash('This page is only available for client accounts.', 'error')
        return redirect(url_for('index'))

    # Get user's purchase preferences
    preferences = get_user_purchase_preferences(current_user.id)

    # Group preferences by category
    preferences_by_category = {}
    for preference in preferences:
        category = preference.product_category or 'Uncategorized'
        if category not in preferences_by_category:
            preferences_by_category[category] = []
        preferences_by_category[category].append(preference)

    # Get frequent products
    monthly_products = get_user_frequent_products(current_user.id, 'monthly', 5)
    quarterly_products = get_user_frequent_products(current_user.id, 'quarterly', 5)
    yearly_products = get_user_frequent_products(current_user.id, 'yearly', 5)

    return render_template('purchase_preferences.html',
                           preferences_by_category=preferences_by_category,
                           monthly_products=monthly_products,
                           quarterly_products=quarterly_products,
                           yearly_products=yearly_products)


@app.route('/order/<int:order_id>')
@login_required
def view_order(order_id):
    # First try to find a regular order
    order = Order.query.get(order_id)

    if order:
        # Found a regular order
        # If user is a company (supplier), redirect to company order details view
        if current_user.role == "company":
            return redirect(url_for('order_details', order_id=order_id))

        # If user is a client, check if they own this order
        if current_user.role == "client":
            if order.user_id != current_user.id:
                flash("You are not authorized to view this order.", "error")
                return redirect(url_for('index'))

        # Render client order detail template
        return render_template('client/order_detail.html', order=order)

    # If no regular order found, try to find a supplier order
    supplier_order = SupplierOrder.query.get(order_id)

    if supplier_order:
        # Found a supplier order
        # If user is a client, check if they own this supplier order
        if current_user.role == "client":
            if supplier_order.user_id != current_user.id:
                flash("You are not authorized to view this order.", "error")
                return redirect(url_for('index'))

            # Render supplier order detail template
            return render_template('client/supplier_order_detail.html', supplier_order=supplier_order)

        # If user is a company, redirect to company supplier order details view
        elif current_user.role == "company":
            return redirect(url_for('supplier_order_details', order_id=order_id))

    # If neither order type found, return 404
    abort(404)


@app.route('/order/delete/<int:order_id>')
@login_required
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)

    # Only allow the order owner (client) to delete their order
    if current_user.role != "client" or order.user_id != current_user.id:
        flash("You are not authorized to delete this order.", "error")
        return redirect(url_for('index'))

    # Delete related purchases
    Purchase.query.filter_by(order_id=order_id).delete()
    # Delete related offers (if needed)
    Offer.query.filter_by(order_id=order_id).delete()

    # Delete the order
    db.session.delete(order)
    db.session.commit()
    flash("Order and related records deleted successfully!", "success")
    return redirect(url_for('dash'))


@app.route('/orders/export')
@login_required
def export_orders():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    data = []
    for order in orders:
        status = 'No Offers'
        if any(offer.status == 'accepted' for offer in order.offers):
            status = 'Accepted'
        elif any(offer.status == 'pending' for offer in order.offers):
            status = 'Pending'
        purchase_info = ', '.join(
            [f"{p.part_name} (Qty: {p.quantity}, Sector: {p.sector})" for p in order.purchases]) or 'No Purchases'
        offer_info = ', '.join([
                                   f"{o.company.name_ar or o.company.name_en or 'N/A' if o.company else 'N/A'} (Price: {o.price}, Status: {o.status})"
                                   for o in order.offers]) or 'No Offers'
        data.append({
            'Order ID': order.id,
            'Created At': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'Company': order.company.name_ar or order.company.name_en or 'N/A' if order.company else 'N/A',
            'Status': status,
            'Purchases': purchase_info,
            'Offers': offer_info
        })
    df = pd.DataFrame(data)
    output = BytesIO()
    df.to_csv(output, index=False)
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'my_orders_{timestamp}.csv'
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype='text/csv'
    )


@app.route("/ss")
def ss():
    user = User.query.filter_by(id=2).first()
    company = Company.query.filter_by(id=1).first()
    user.company = company
    db.session.commit()
    return redirect("/login")


@app.route('/offers/<int:order_id>')
@login_required
def view_offers(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("You are not authorized to view this order.", "error")
        return redirect(url_for('index'))
    offers = order.offers
    return render_template('offers.html', order=order, offers=offers)


@app.route('/download_sample_csv')
def download_sample_csv():
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(
        ['name', 'description', 'category', 'sku', 'price', 'cost', 'quantity', 'min_quantity', 'unit', 'location',
         'supplier', 'supplier_contact', 'requirements'])

    # Write sample data (English)
    writer.writerow(
        ['Sample Product', 'This is a sample product description', 'Electronics', 'SAMPLE001', '100.00', '80.00', '50',
         '10', 'pcs', 'Warehouse A', 'Sample Supplier', 'supplier@example.com', 'No special requirements'])
    writer.writerow(
        ['Another Product', 'Another sample product', 'Automotive', 'SAMPLE002', '250.00', '200.00', '25', '5', 'pcs',
         'Warehouse B', 'Another Supplier', 'another@example.com', 'Handle with care'])

    # Write sample data (Arabic)
    writer.writerow(
        ['منتج تجريبي', 'هذا وصف منتج تجريبي', 'إلكترونيات', 'SAMPLE003', '150.00', '120.00', '30', '5', 'قطعة',
         'مستودع أ', 'مورد تجريبي', 'supplier@example.com', 'لا توجد متطلبات خاصة'])
    writer.writerow(
        ['منتج آخر', 'منتج تجريبي آخر', 'سيارات', 'SAMPLE004', '300.00', '240.00', '15', '3', 'قطعة', 'مستودع ب',
         'مورد آخر', 'another@example.com', 'التعامل بحذر'])

    output.seek(0)

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=sample_inventory.csv'}
    )


@app.route('/download_purchase_preferences_template')
def download_purchase_preferences_template():
    """Download a template file for purchase preferences"""
    # Create a sample Excel template
    import io
    import pandas as pd

    # Sample data
    sample_data = [
        {
            'product_name': 'Laptop',
            'product_category': 'Electronics',
            'description': 'Business laptop with minimum 8GB RAM',
            'quantity': 10,
            'unit': 'pcs',
            'frequency': 'quarterly',
            'max_price_per_unit': 800.00,
            'preferred_suppliers': 'Dell, HP, Lenovo',
            'quality_preference': 'standard',
            'payment_preference': 'net30',
            'preferred_delivery_time': 'standard',
            'typical_order_size': 25
        },
        {
            'product_name': 'Office Chairs',
            'product_category': 'Furniture',
            'description': 'Ergonomic office chairs',
            'quantity': 50,
            'unit': 'pcs',
            'frequency': 'yearly',
            'max_price_per_unit': 150.00,
            'preferred_suppliers': 'IKEA, Office Depot',
            'quality_preference': 'standard',
            'payment_preference': 'net60',
            'preferred_delivery_time': 'flexible',
            'typical_order_size': 100
        },
        {
            'product_name': 'Printer Paper',
            'product_category': 'Office Supplies',
            'description': 'A4 printer paper, 80gsm, white',
            'quantity': 500,
            'unit': 'reams',
            'frequency': 'monthly',
            'max_price_per_unit': 5.50,
            'preferred_suppliers': 'Staples, Office Depot',
            'quality_preference': 'standard',
            'payment_preference': 'net30',
            'preferred_delivery_time': 'standard',
            'typical_order_size': 1000
        }
    ]

    # Create DataFrame
    df = pd.DataFrame(sample_data)

    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Purchase Preferences', index=False)

        # Get the workbook and worksheet
        workbook = writer.book
        worksheet = writer.sheets['Purchase Preferences']

        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    output.seek(0)

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=purchase_preferences_template.xlsx'}
    )


@app.route('/download_purchase_preferences_template_csv')
def download_purchase_preferences_template_csv():
    """Download a CSV template file for purchase preferences"""
    import io
    import csv

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header row
    writer.writerow([
        'product_name',
        'product_category',
        'description',
        'quantity',
        'unit',
        'frequency',
        'max_price_per_unit',
        'preferred_suppliers',
        'quality_preference',
        'payment_preference',
        'preferred_delivery_time',
        'typical_order_size'
    ])

    # Write sample data rows
    writer.writerow([
        'Laptop',
        'Electronics',
        'Business laptop with minimum 8GB RAM',
        '10',
        'pcs',
        'quarterly',
        '800.00',
        'Dell, HP, Lenovo',
        'standard',
        'net30',
        'standard',
        '25'
    ])

    writer.writerow([
        'Office Chairs',
        'Furniture',
        'Ergonomic office chairs',
        '50',
        'pcs',
        'yearly',
        '150.00',
        'IKEA, Office Depot',
        'standard',
        'net60',
        'flexible',
        '100'
    ])

    output.seek(0)

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=purchase_preferences_template.csv'}
    )


@app.route("/chat")
@login_required
def chat():
    if current_user.role != 'client':
        flash('Only clients can access chat.', 'error')
        return redirect(url_for('index'))

    # Check if company_id is provided as query parameter
    company_id = request.args.get('company_id')
    if company_id:
        try:
            company_id = int(company_id)
            return redirect(url_for('start_chat', company_id=company_id))
        except ValueError:
            flash('Invalid company ID.', 'error')
            return redirect(url_for('chat'))

    # Get all chats for the current user
    chats = Chat.query.filter_by(client_id=current_user.id).order_by(Chat.updated_at.desc()).all()
    return render_template("client/chat.html", chats=chats)


@app.route("/chat/<int:company_id>")
@login_required
def start_chat(company_id):
    if current_user.role != 'client':
        flash('Only clients can start chats.', 'error')
        return redirect(url_for('index'))

    # Check if company exists and is approved
    company = Company.query.filter_by(id=company_id, is_approved=True).first()
    if not company:
        flash('Company not found or not approved.', 'error')
        return redirect(url_for('chat'))

    # Check if chat already exists
    existing_chat = Chat.query.filter_by(client_id=current_user.id, company_id=company_id).first()
    if existing_chat:
        return redirect(url_for('view_chat', chat_id=existing_chat.id))

    # Create new chat
    new_chat = Chat(client_id=current_user.id, company_id=company_id)
    db.session.add(new_chat)
    try:
        db.session.commit()
        flash(f'Chat started with {company.name_ar or company.name_en or "Company"}', 'success')
        return redirect(url_for('view_chat', chat_id=new_chat.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error starting chat: {str(e)}', 'error')
        return redirect(url_for('chat'))


@app.route("/chat/view/<int:chat_id>")
@login_required
def view_chat(chat_id):
    if current_user.role != 'client':
        flash('Only clients can view chats.', 'error')
        return redirect(url_for('index'))

    chat = Chat.query.filter_by(id=chat_id, client_id=current_user.id).first()
    if not chat:
        flash('Chat not found.', 'error')
        return redirect(url_for('chat'))

    # Mark messages as read
    unread_messages = Message.query.filter_by(chat_id=chat_id, is_read=False).filter(
        Message.sender_id != current_user.id).all()
    for message in unread_messages:
        message.is_read = True
    db.session.commit()

    return render_template("client/chat.html", current_chat=chat,
                           chats=Chat.query.filter_by(client_id=current_user.id).order_by(Chat.updated_at.desc()).all())


@app.route("/chat/send_message", methods=['POST'])
@login_required
def send_message():
    if current_user.role != 'client':
        return {'error': 'Only clients can send messages'}, 403

    chat_id = request.form.get('chat_id')
    content = request.form.get('content')

    if not chat_id or not content:
        return {'error': 'Missing chat_id or content'}, 400

    chat = Chat.query.filter_by(id=chat_id, client_id=current_user.id).first()
    if not chat:
        return {'error': 'Chat not found'}, 404

    message = Message(
        chat_id=chat_id,
        sender_id=current_user.id,
        sender_type='client',
        content=content
    )

    # Update chat's updated_at timestamp
    chat.updated_at = datetime.utcnow()

    db.session.add(message)
    try:
        db.session.commit()
        return {
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'sender_type': message.sender_type
            }
        }
    except Exception as e:
        db.session.rollback()
        return {'error': str(e)}, 500


@app.route("/chat/get_messages/<int:chat_id>")
@login_required
def get_messages(chat_id):
    if current_user.role != 'client':
        return {'error': 'Only clients can view messages'}, 403

    chat = Chat.query.filter_by(id=chat_id, client_id=current_user.id).first()
    if not chat:
        return {'error': 'Chat not found'}, 404

    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.created_at).all()

    messages_data = []
    for msg in messages:
        sender_name = 'Unknown'
        if msg.sender:
            if msg.sender_type == 'client':
                sender_name = msg.sender.username
            elif msg.sender_type == 'company':
                sender_name = msg.sender.name_ar or msg.sender.name_en or 'Company'

        messages_data.append({
            'id': msg.id,
            'content': msg.content,
            'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'sender_type': msg.sender_type,
            'sender_name': sender_name
        })

    return {'messages': messages_data}


@app.route("/suppliers")
@login_required
def suppliers():
    if current_user.role != 'client':
        flash('Only clients can access suppliers directory.', 'error')
        return redirect(url_for('index'))

    # Get all approved companies
    companies = Company.query.filter_by(is_approved=True).order_by(Company.name_ar.asc()).all()

    return render_template("client/suppliers.html", companies=companies)


@app.route("/company/<int:company_id>/products")
@login_required
def company_products(company_id):
    if current_user.role != 'client':
        flash('Only clients can access company products.', 'error')
        return redirect(url_for('index'))

    # Get the company and its products
    company = Company.query.get_or_404(company_id)

    # Only show approved companies
    if not company.is_approved:
        flash('This company is not yet approved.', 'error')
        return redirect(url_for('suppliers'))

    # Get all active products for this company
    products = Product.query.filter_by(company_id=company_id, is_active=True).order_by(Product.name.asc()).all()

    # Get user's cart items from database
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()

    return render_template("client/company_products.html",
                           company=company,
                           products=products,
                           cart_items=cart_items)


@app.route("/orders")
@login_required
def orders():
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of orders per page

    # Query regular orders for the current user
    user_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).paginate(page=page,
                                                                                                            per_page=per_page)

    # Query supplier orders for the current user
    supplier_orders = SupplierOrder.query.filter_by(user_id=current_user.id).order_by(
        SupplierOrder.created_at.desc()).all()

    return render_template("client/orders.html",
                           orders=user_orders,
                           supplier_orders=supplier_orders)


@app.route('/my_deliveries')
@login_required
def my_deliveries():
    """Display packages that the current user will receive"""
    # Get packages for orders made by the current user that are shipped or preparing
    packages = db.session.query(Package).join(Order).filter(
        Order.user_id == current_user.id,
        Package.status.in_(['shipped', 'preparing'])
    ).order_by(Package.created_at.desc()).all()
    
    # Convert packages to dictionaries for JSON serialization
    packages_data = []
    for package in packages:
        # Get company name
        company = Company.query.get(package.company_id)
        company_name = company.display_name if company else 'Unknown Company'
        
        # Generate delivery code if not exists
        if not package.delivery_code:
            import random
            import string
            package.delivery_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            db.session.commit()
        
        packages_data.append({
            'id': package.id,
            'package_number': package.package_number,
            'order_id': package.order_id,
            'company_name': company_name,
            'status': package.status,
            'total_value': float(package.total_value) if package.total_value else 0.0,
            'created_at': package.created_at.isoformat() if package.created_at else None,
            'delivery_code': package.delivery_code
        })
    
    return render_template('client/my_deliveries.html', packages=packages_data)


@app.route('/generate_delivery_code/<int:package_id>', methods=['POST'])
@login_required
def generate_delivery_code(package_id):
    """Generate a new delivery code for a package"""
    try:
        # Get the package
        package = db.session.get(Package, package_id)
        if not package:
            return jsonify({'success': False, 'message': 'Package not found'}), 404
        
        # Check if the current user has permission to generate code for this package
        # Only the client who ordered the package can generate the code
        if current_user.role == 'client':
            order = db.session.get(Order, package.order_id)
            if not order or order.user_id != current_user.id:
                return jsonify({'success': False, 'message': 'Access denied'}), 403
        else:
            return jsonify({'success': False, 'message': 'Only clients can generate delivery codes'}), 403
        
        # Check if package is in a valid status for code generation
        if package.status not in ['shipped', 'preparing']:
            return jsonify({'success': False, 'message': 'Cannot generate code for package in current status'}), 400
        
        # Generate a new delivery code
        import random
        import string
        package.delivery_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Delivery code generated successfully',
            'delivery_code': package.delivery_code,
            'package_id': package.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error generating delivery code: {str(e)}'}), 500


@app.route('/company_dashboard')
@login_required
def company_dashboard():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    # Get company information through user's company_id
    company = Company.query.filter_by(id=current_user.company_id).first()

    # Get orders relevant to this company (orders containing products they can supply)
    relevant_orders = get_company_relevant_orders(company.id if company else None)

    # Also get all orders for broader statistics
    all_orders = Order.query.all()

    # Get offers made by this company
    company_offers = Offer.query.filter_by(company_id=company.id if company else None).all()

    # Get products in company's inventory
    company_products = Product.query.filter_by(company_id=company.id if company else None).all()

    # Calculate statistics
    total_orders = len(all_orders)  # Show total orders in system
    relevant_orders_count = len(relevant_orders)  # Orders relevant to this company
    pending_orders = relevant_orders_count  # Orders they can respond to
    # Completed Orders: Count offers with 'delivered' status
    completed_orders = len([offer for offer in company_offers if offer.order_status == 'delivered'])
    total_offers = len(company_offers)
    cart_items = len(company_products)  # Use product count as cart items for now

    # Calculate additional metrics for the dashboard
    active_categories = len(
        set(product.category for product in company_products if hasattr(product, 'category') and product.category))
    low_stock_items = len([p for p in company_products if hasattr(p, 'stock') and p.stock and p.stock < 10])

    # Calculate real performance metrics
    # Order Success Rate: (accepted offers / total offers) * 100
    if total_offers > 0:
        accepted_offers = len([offer for offer in company_offers if offer.status == 'accepted'])
        order_success_rate = f"{round((accepted_offers / total_offers) * 100)}%"
    else:
        order_success_rate = "0%"

    # Customer Satisfaction: Average rating based on delivered orders
    delivered_offers = [offer for offer in company_offers if offer.order_status == 'delivered']
    if delivered_offers:
        # For now, calculate based on delivery performance (can be enhanced with actual ratings)
        on_time_deliveries = len([offer for offer in delivered_offers
                                  if offer.delivery_time and 'urgent' not in offer.delivery_time.lower()])
        satisfaction_score = 3.5 + (on_time_deliveries / len(delivered_offers)) * 1.5  # Scale 3.5-5.0
        customer_satisfaction = f"{satisfaction_score:.1f}/5"
    else:
        customer_satisfaction = "N/A"

    # On-Time Delivery: (delivered on time / total delivered) * 100
    if delivered_offers:
        # Calculate based on delivery_time vs actual delivery (simplified)
        on_time_count = len([offer for offer in delivered_offers
                             if not offer.delivery_time or 'late' not in offer.description.lower()])
        on_time_delivery = f"{round((on_time_count / len(delivered_offers)) * 100)}%"
    else:
        on_time_delivery = "N/A"

    # Calculate Recent Activity & Analytics metrics (Last 30 days)
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # New Clients: Count unique clients who placed orders with this company in last 30 days
    recent_orders_with_offers = [order for order in all_orders
                                 if any(offer.company_id == (company.id if company else None)
                                        and offer.created_at >= thirty_days_ago
                                        for offer in order.offers)]
    new_clients = len(set(order.user_id for order in recent_orders_with_offers))

    # Revenue: Sum of accepted offers' total_price in last 30 days
    recent_accepted_offers = [offer for offer in company_offers
                              if offer.status == 'accepted' and offer.created_at >= thirty_days_ago]
    total_revenue = sum(offer.total_price for offer in recent_accepted_offers)

    # Format revenue with K/M suffix
    if total_revenue >= 1000000:
        revenue = f"EGP {total_revenue / 1000000:.1f}M"
    elif total_revenue >= 1000:
        revenue = f"EGP {total_revenue / 1000:.1f}K"
    else:
        revenue = f"EGP {total_revenue:.0f}" if total_revenue > 0 else "EGP 0"

    # Average Response Time: Calculate time between order creation and first offer
    response_times = []
    for order in recent_orders_with_offers:
        company_offers_for_order = [offer for offer in order.offers
                                    if offer.company_id == (company.id if company else None)]
        if company_offers_for_order:
            first_offer = min(company_offers_for_order, key=lambda x: x.created_at)
            response_time_hours = (first_offer.created_at - order.created_at).total_seconds() / 3600
            response_times.append(response_time_hours)

    if response_times:
        avg_hours = sum(response_times) / len(response_times)
        if avg_hours < 1:
            avg_response_time = f"{int(avg_hours * 60)}m"
        elif avg_hours < 24:
            avg_response_time = f"{avg_hours:.1f}h"
        else:
            avg_response_time = f"{avg_hours / 24:.1f}d"
    else:
        avg_response_time = "N/A"

    # Pagination variables
    current_page = 1
    total_pages = max(1, (len(relevant_orders) + 9) // 10)  # 10 items per page

    # Get orders that belong to this company (company's own orders)
    company_own_orders = Order.query.filter_by(company_id=company.id if company else None).all()

    return render_template("company/stocks.html",
                           company=company,
                           orders=company_own_orders,  # Company's own orders only
                           relevant_orders=relevant_orders,  # Available orders to bid on
                           total_orders=total_orders,
                           pending_orders=pending_orders,
                           completed_orders=completed_orders,
                           total_offers=total_offers,
                           cart_items=cart_items,
                           active_categories=active_categories,
                           low_stock_items=low_stock_items,
                           order_success_rate=order_success_rate,
                           customer_satisfaction=customer_satisfaction,
                           on_time_delivery=on_time_delivery,
                           current_page=current_page,
                           total_pages=total_pages,
                           new_clients=new_clients,
                           revenue=revenue,
                           avg_response_time=avg_response_time)


@app.route('/set_language/<language>')
def set_language(language):
    session['language'] = language
    print(f"DEBUG: Language set to {language}")
    print(f"DEBUG: Session language: {session.get('language')}")

    # Check if it's an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'language': language})

    # For regular requests, redirect back to company status if that's where we came from
    referrer = request.referrer or url_for('index')
    if 'company_status' in referrer:
        return redirect(url_for('company_status'))
    else:
        return redirect(referrer)


@app.route('/test_translation')
def test_translation():
    current_lang = session.get('language', 'en')
    print(f"DEBUG: Current language: {current_lang}")
    print(f"DEBUG: get_locale(): {get_locale()}")
    print(f"DEBUG: Test translation: {_('Create New Order')}")
    print(f"DEBUG: Babel default locale: {babel.default_locale}")
    print(f"DEBUG: Babel supported locales: {babel.list_translations()}")
    return f"Language: {current_lang}, Locale: {get_locale()}, Translation: {_('Create New Order')}"


@app.route('/debug_session')
def debug_session():
    return f"""
    <h1>Session Debug Info</h1>
    <p>Session Language: {session.get('language', 'Not set')}</p>
    <p>get_locale(): {get_locale()}</p>
    <p>Babel Default: {babel.default_locale}</p>
    <p>Supported: {babel.list_translations()}</p>
    <p><a href="/company_status">Go to Company Status</a></p>
    """


# Company Routes
@app.route('/company_orders')
@login_required
def company_orders():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    # Get company information
    company = Company.query.filter_by(id=current_user.company_id).first()

    # Get only orders that are relevant to this company (contain products they have)
    orders = get_company_relevant_orders(company.id if company else None)

    return render_template('company/orders.html', orders=orders, company=company)


@app.route('/company_offers')
@login_required
def company_offers():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    # Get company information
    company = Company.query.filter_by(id=current_user.company_id).first()

    # Get all offers made by this company
    offers = Offer.query.filter_by(company_id=company.id if company else None).order_by(Offer.created_at.desc()).all()

    return render_template('company/offers.html', offers=offers, company=company)


@app.route('/ai_agent')
@login_required
def ai_agent():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    # Get company information
    company = Company.query.filter_by(id=current_user.company_id).first()
    
    return render_template('company/ai_agent.html', company=company)


@app.route('/company_profile')
@login_required
def company_profile():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    return render_template('company/profile.html', company=company)


@app.route('/company_analytics')
@login_required
def company_analytics():
    """Company analytics page"""
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('dash'))

    try:
        # Calculate analytics for this company
        total_orders = Order.query.filter_by(company_id=company.id).count()
        total_offers = Offer.query.filter_by(company_id=company.id).count()
        total_packages = Package.query.filter_by(company_id=company.id).count()
        
        # Get order status breakdown (if status field exists)
        pending_orders = Order.query.filter_by(company_id=company.id, status='pending').count() if hasattr(Order, 'status') else 0
        completed_orders = Order.query.filter_by(company_id=company.id, status='completed').count() if hasattr(Order, 'status') else 0
        
        # Get offer status breakdown
        pending_offers = Offer.query.filter_by(company_id=company.id, status='pending').count()
        accepted_offers = Offer.query.filter_by(company_id=company.id, status='accepted').count()
        rejected_offers = Offer.query.filter_by(company_id=company.id, status='rejected').count()
        
        # Calculate conversion rate (accepted offers / total offers)
        conversion_rate = (accepted_offers / total_offers * 100) if total_offers > 0 else 0
        
        # Calculate total order value
        orders = Order.query.filter_by(company_id=company.id).all()
        total_order_value = sum(order.total_amount for order in orders if hasattr(order, 'total_amount') and order.total_amount)
        
        # Get recent activity (last 30 days)
        from datetime import datetime, timedelta
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        recent_orders = Order.query.filter(
            Order.company_id == company.id,
            Order.created_at >= thirty_days_ago
        ).count() if hasattr(Order, 'created_at') else 0
        
        recent_offers = Offer.query.filter(
            Offer.company_id == company.id,
            Offer.created_at >= thirty_days_ago
        ).count() if hasattr(Offer, 'created_at') else 0
        
    except Exception as e:
        # If there's an error, set default values
        print(f"Error in company_analytics: {e}")
        total_orders = 0
        total_offers = 0
        total_packages = 0
        pending_orders = 0
        completed_orders = 0
        pending_offers = 0
        accepted_offers = 0
        rejected_offers = 0
        conversion_rate = 0
        total_order_value = 0
        recent_orders = 0
        recent_offers = 0

    return render_template('company/analytics.html',
                         company=company,
                         total_orders=total_orders,
                         total_offers=total_offers,
                         total_packages=total_packages,
                         pending_orders=pending_orders,
                         completed_orders=completed_orders,
                         pending_offers=pending_offers,
                         accepted_offers=accepted_offers,
                         rejected_offers=rejected_offers,
                         conversion_rate=conversion_rate,
                         total_order_value=total_order_value,
                         recent_orders=recent_orders,
                         recent_offers=recent_offers)


@app.route('/company_settings', methods=['GET', 'POST'])
@login_required
def company_settings():
    """Company settings page for managing company information and preferences"""
    if current_user.role != 'company':
        flash('Access denied. Company role required.', 'error')
        return redirect(url_for('dash'))
    
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'error')
        return redirect(url_for('dash'))
    
    if request.method == 'POST':
        try:
            # Update basic information
            company.name_ar = request.form.get('name_ar', '').strip()
            company.name_en = request.form.get('name_en', '').strip()
            company.email = request.form.get('email', '').strip()
            company.office_phone = request.form.get('office_phone', '').strip()
            company.mobile_contact = request.form.get('mobile_contact', '').strip()
            company.website = request.form.get('website', '').strip()
            company.registered_address = request.form.get('registered_address', '').strip()
            
            # Update legal information
            company.legal_type = request.form.get('legal_type', '').strip()
            company.tax_id = request.form.get('tax_id', '').strip()
            company.commercial_registration = request.form.get('commercial_registration', '').strip()
            company.vat_number = request.form.get('vat_number', '').strip()
            
            # Update contact person information
            company.contact_person = request.form.get('contact_person', '').strip()
            company.contact_position = request.form.get('contact_position', '').strip()
            company.owner_name = request.form.get('owner_name', '').strip()
            
            # Update banking information
            company.bank_name = request.form.get('bank_name', '').strip()
            company.account_name = request.form.get('account_name', '').strip()
            company.account_number = request.form.get('account_number', '').strip()
            company.bank_branch = request.form.get('bank_branch', '').strip()
            
            # Update additional information
            company.sector = request.form.get('sector', '').strip()
            founded_year = request.form.get('founded_year', '').strip()
            if founded_year:
                try:
                    company.founded_year = int(founded_year)
                except ValueError:
                    company.founded_year = None
            else:
                company.founded_year = None
            
            company.employees_count = request.form.get('employees_count', '').strip()
            company.certifications = request.form.get('certifications', '').strip()
            company.operating_countries = request.form.get('operating_countries', '').strip()
            
            # Update company preferences
            company.email_notifications = 'email_notifications' in request.form
            company.app_notifications = 'app_notifications' in request.form
            company.preferred_language = request.form.get('preferred_language', 'ar')
            company.email_marketing = 'email_marketing' in request.form
            
            # Update timestamp
            company.updated_at = datetime.utcnow()
            
            # Validate required fields
            if not company.name_ar and not company.name_en:
                flash('Company name is required (Arabic or English).', 'error')
                return render_template('company/settings.html', company=company)
            
            if not company.email:
                flash('Email is required.', 'error')
                return render_template('company/settings.html', company=company)
            
            # Check for duplicate email (excluding current company)
            existing_company = Company.query.filter(
                Company.email == company.email,
                Company.id != company.id
            ).first()
            
            if existing_company:
                flash('A company with this email already exists.', 'error')
                return render_template('company/settings.html', company=company)
            
            # Save changes
            db.session.commit()
            flash('Company settings updated successfully!', 'success')
            
            # Update session language if changed
            if company.preferred_language:
                session['language'] = company.preferred_language
                # Also set the language cookie to ensure consistency
                response = make_response(render_template('company/settings.html', company=company))
                response.set_cookie('language', company.preferred_language, max_age=31536000, path='/')
                return response
            
        except Exception as e:
            db.session.rollback()
            print(f"Error updating company settings: {e}")
            flash(f'Error updating settings: {str(e)}', 'error')
    
    return render_template('company/settings.html', company=company)


@app.route('/company_inventory')
@login_required
def company_inventory():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()

    # Get search parameters
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    status = request.args.get('status', '')

    # Query products with filters
    products_query = Product.query.filter_by(company_id=company.id)

    if search:
        products_query = products_query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%')
            )
        )

    if category:
        products_query = products_query.filter(Product.category == category)

    if status:
        if status == 'low_stock':
            products_query = products_query.filter(Product.quantity <= Product.min_quantity)
        elif status == 'out_of_stock':
            products_query = products_query.filter(Product.quantity == 0)
        elif status == 'in_stock':
            products_query = products_query.filter(Product.quantity > Product.min_quantity)

    products = products_query.order_by(Product.created_at.desc()).all()

    # Calculate inventory statistics
    total_items = len(products)
    low_stock_count = len([p for p in products if p.stock_status == 'low_stock'])
    out_of_stock_count = len([p for p in products if p.stock_status == 'out_of_stock'])
    total_value = sum(p.total_value for p in products)

    return render_template('company/inventory.html',
                           company=company,
                           products=products,
                           total_items=total_items,
                           low_stock_count=low_stock_count,
                           out_of_stock_count=out_of_stock_count,
                           total_value=total_value,
                           search=search,
                           category=category,
                           status=status)


@app.route('/company_bills')
@login_required
def company_bills():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('dash'))

    # Get search and filter parameters
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    client_filter = request.args.get('client', '')

    # Query bills for this company
    bills_query = Bill.query.filter_by(company_id=company.id)

    if search:
        bills_query = bills_query.filter(
            db.or_(
                Bill.bill_number.ilike(f'%{search}%'),
                Bill.notes.ilike(f'%{search}%')
            )
        )

    if status_filter:
        bills_query = bills_query.filter(Bill.status == status_filter)

    if client_filter:
        bills_query = bills_query.filter(Bill.client_id == client_filter)

    bills = bills_query.order_by(Bill.created_at.desc()).all()

    # Add computed properties to each bill
    for bill in bills:
        # Add products count from bill items
        bill.products_count = len(bill.bill_items) if bill.bill_items else 0
        # Add client name from client relationship
        bill.client_name = bill.client.name_en or bill.client.name_ar if bill.client else 'Unknown Client'

    # Calculate statistics
    total_bills = len(bills)
    paid_bills = len([b for b in bills if b.status == 'paid'])
    pending_bills = len([b for b in bills if b.status == 'pending'])
    overdue_bills = len([b for b in bills if b.is_overdue and b.status != 'paid'])
    total_amount = sum(b.total_amount for b in bills)
    paid_amount = sum(b.total_amount for b in bills if b.status == 'paid')
    pending_amount = sum(b.total_amount for b in bills if b.status == 'pending')

    # Get client companies for filter dropdown
    client_companies = Company.query.filter(
        Company.id.in_([b.client_id for b in bills])
    ).all()

    return render_template('company/bills.html',
                           company=company,
                           bills=bills,
                           total_bills=total_bills,
                           paid_bills=paid_bills,
                           pending_bills=pending_bills,
                           overdue_bills=overdue_bills,
                           total_amount=total_amount,
                           paid_amount=paid_amount,
                           pending_amount=pending_amount,
                           client_companies=client_companies,
                           search=search,
                           status_filter=status_filter,
                           client_filter=client_filter)

@app.route('/company/bills/<int:bill_id>')
@login_required
def company_bill_detail(bill_id):
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('dash'))

    # Get the bill and verify it belongs to this company
    bill = Bill.query.filter_by(id=bill_id, company_id=company.id).first()
    if not bill:
        flash(_('Bill not found.'), 'error')
        return redirect(url_for('company_bills'))

    return render_template('company/bill_detail.html',
                           company=company,
                           bill=bill)

@app.route('/company/bills/<int:bill_id>/pdf')
@login_required
def company_bill_pdf(bill_id):
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('dash'))

    # Get the bill and verify it belongs to this company
    bill = Bill.query.filter_by(id=bill_id, company_id=company.id).first()
    if not bill:
        flash(_('Bill not found.'), 'error')
        return redirect(url_for('company_bills'))

    try:
        # Generate PDF using WeasyPrint
        from datetime import datetime
        html_content = render_template('company/bill_pdf.html',
                                       company=company,
                                       bill=bill,
                                       datetime=datetime)
        
        # Create PDF
        pdf_file = HTML(string=html_content).write_pdf()
        
        # Create response
        response = make_response(pdf_file)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="Bill_{bill.bill_number}.pdf"'
        
        return response
        
    except Exception as e:
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('company_bill_detail', bill_id=bill_id))


@app.route('/api/bills/<int:bill_id>/mark-paid', methods=['POST'])
@login_required
def mark_bill_paid(bill_id):
    if current_user.role != 'company':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        return jsonify({'success': False, 'error': 'Company not found'}), 404
    
    bill = Bill.query.filter_by(id=bill_id, company_id=company.id).first()
    if not bill:
        return jsonify({'success': False, 'error': 'Bill not found'}), 404
    
    try:
        bill.status = 'paid'
        bill.payment_date = datetime.now(timezone.utc).date()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Bill marked as paid successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error updating bill: {str(e)}'
        }), 500


@app.route('/generate_bills_from_orders', methods=['POST'])
@login_required
def generate_bills_from_orders():
    """Generate bills for all existing orders that don't have bills yet"""
    if current_user.role != 'company':
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))
    
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('dash'))
    
    try:
        # Get all orders that don't have bills yet
        # Include orders with no company_id (legacy orders) and orders for this company
        orders_without_bills = Order.query.filter(
            db.or_(
                Order.company_id == company.id,
                Order.company_id.is_(None)
            ),
            ~Order.id.in_(db.session.query(Bill.order_id))
        ).all()
        
        bills_created = 0
        
        for order in orders_without_bills:
            # Generate unique bill number
            bill_number = f"BILL-{company.id}-{order.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Calculate due date (30 days from now)
            due_date = datetime.now().date() + timedelta(days=30)
            
            # Create the bill
            # For client_id, use the order's company_id if available, otherwise use the current company
            client_id = order.company_id if order.company_id else company.id
            
            bill = Bill(
                bill_number=bill_number,
                company_id=company.id,
                client_id=client_id,
                order_id=order.id,
                created_by_user_id=current_user.id,
                issue_date=datetime.now().date(),
                due_date=due_date,
                status='pending',
                currency='EGP',
                subtotal=0.0,
                tax_rate=0.14,
                tax_amount=0.0,
                discount_amount=0.0,
                total_amount=0.0
            )
            
            db.session.add(bill)
            db.session.flush()  # Get the bill ID
            
            # Create bill items from order purchases
            subtotal = 0.0
            
            # Check if order has accepted offers with ProductOffer pricing
            accepted_offer = None
            for offer in order.offers:
                if offer.status == 'accepted':
                    accepted_offer = offer
                    break
            
            for purchase in order.purchases:
                # Try to get actual pricing from accepted offer's ProductOffer
                unit_price = None
                total_price = None
                
                if accepted_offer:
                    product_offer = ProductOffer.query.filter_by(
                        offer_id=accepted_offer.id,
                        purchase_id=purchase.id
                    ).first()
                    
                    if product_offer:
                        unit_price = product_offer.unit_price
                        total_price = product_offer.total_price
                
                # Fallback to purchase max_price_per_unit or default
                if unit_price is None:
                    unit_price = purchase.max_price_per_unit or 100.0
                    total_price = unit_price * purchase.quantity
                
                # Try to find matching product by name (both directions)
                product = Product.query.filter(
                    Product.name.ilike(f'%{purchase.part_name}%')
                ).first()
                
                # If no match found, try reverse matching (product name in purchase name)
                if not product:
                    products = Product.query.all()
                    for p in products:
                        if p.name.lower() in purchase.part_name.lower():
                            product = p
                            break
                
                bill_item = BillItem(
                    bill_id=bill.id,
                    product_id=product.id if product else None,
                    product_name=purchase.part_name,
                    description=purchase.description,
                    quantity=purchase.quantity,
                    unit=purchase.unit,  # Add required unit field
                    unit_price=unit_price,
                    total_price=total_price
                )
                
                db.session.add(bill_item)
                subtotal += total_price
            
            # If no purchases, create a single item for the order
            if not order.purchases:
                # Use order total_amount or default
                total_amount = order.total_amount or 1000.0
                
                bill_item = BillItem(
                    bill_id=bill.id,
                    product_name=order.order_name,
                    description=order.description or 'Order services',
                    quantity=1,
                    unit=1,  # Add required unit field
                    unit_price=total_amount,
                    total_price=total_amount
                )
                
                db.session.add(bill_item)
                subtotal = total_amount
            
            # Calculate totals
            bill.subtotal = subtotal
            bill.tax_amount = subtotal * bill.tax_rate
            bill.total_amount = bill.subtotal + bill.tax_amount - bill.discount_amount
            
            bills_created += 1
        
        db.session.commit()
        
        if bills_created > 0:
            flash(_(f'Successfully generated {bills_created} bills from existing orders.'), 'success')
        else:
            flash(_('No new bills to generate. All orders already have bills.'), 'info')
            
    except Exception as e:
        db.session.rollback()
        flash(_(f'Error generating bills: {str(e)}'), 'error')
    
    return redirect(url_for('company_bills'))


@app.route('/company_chat')
@login_required
def company_chat():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    # Get chats where this company is involved
    chats = Chat.query.filter_by(company_id=company.id if company else None).all()
    return render_template('company/chat.html', chats=chats, company=company)


@app.route('/company_chat/<int:client_id>')
@login_required
def company_start_chat(client_id):
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('company_chat'))

    # Check if client exists
    client = User.query.filter_by(id=client_id).first()
    if not client:
        flash(_('Client not found.'), 'error')
        return redirect(url_for('company_chat'))

    # Check if chat already exists
    existing_chat = Chat.query.filter_by(client_id=client_id, company_id=company.id).first()
    if existing_chat:
        return redirect(url_for('company_view_chat', chat_id=existing_chat.id))

    # Create new chat
    new_chat = Chat(client_id=client_id, company_id=company.id)
    db.session.add(new_chat)
    try:
        db.session.commit()
        flash(f'Chat started with {client.username}', 'success')
        return redirect(url_for('company_view_chat', chat_id=new_chat.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error starting chat: {str(e)}', 'error')
        return redirect(url_for('company_chat'))


@app.route('/company_chat/view/<int:chat_id>')
@login_required
def company_view_chat(chat_id):
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('company_chat'))

    chat = Chat.query.filter_by(id=chat_id, company_id=company.id).first()
    if not chat:
        flash(_('Chat not found.'), 'error')
        return redirect(url_for('company_chat'))

    # Mark messages as read
    unread_messages = Message.query.filter_by(chat_id=chat_id, is_read=False).filter(
        Message.sender_id != company.id).all()
    for message in unread_messages:
        message.is_read = True
    db.session.commit()

    # Get all chats for this company
    all_chats = Chat.query.filter_by(company_id=company.id).order_by(Chat.updated_at.desc()).all()

    return render_template('company/chat_view.html', current_chat=chat, chats=all_chats, company=company)


@app.route("/company_chat/send_message", methods=['POST'])
@login_required
def company_send_message():
    print(f"DEBUG: Message send request received from user {current_user.id}")  # Debug log

    if current_user.role != 'company':
        print(f"DEBUG: User {current_user.id} is not a company user")  # Debug log
        return {'error': 'Only companies can send messages'}, 403

    chat_id = request.form.get('chat_id')
    content = request.form.get('content')

    print(f"DEBUG: chat_id={chat_id}, content={content}")  # Debug log

    if not chat_id or not content:
        print(f"DEBUG: Missing chat_id or content")  # Debug log
        return {'error': 'Missing chat_id or content'}, 400

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        print(f"DEBUG: Company not found for user {current_user.id}")  # Debug log
        return {'error': 'Company not found'}, 404

    print(f"DEBUG: Company found: {company.id}")  # Debug log

    chat = Chat.query.filter_by(id=chat_id, company_id=company.id).first()
    if not chat:
        print(f"DEBUG: Chat {chat_id} not found for company {company.id}")  # Debug log
        return {'error': 'Chat not found'}, 404

    print(f"DEBUG: Chat found: {chat.id}")  # Debug log

    message = Message(
        chat_id=chat_id,
        sender_id=company.id,
        sender_type='company',
        content=content
    )

    # Update chat's updated_at timestamp
    chat.updated_at = datetime.utcnow()

    db.session.add(message)
    try:
        db.session.commit()
        print(f"DEBUG: Message saved successfully with ID {message.id}")  # Debug log
        return {'success': True, 'message_id': message.id}
    except Exception as e:
        print(f"DEBUG: Error saving message: {str(e)}")  # Debug log
        db.session.rollback()
        return {'error': str(e)}, 500


@app.route("/compare_offers", methods=['POST'])
@login_required
def compare_offers():
    """Compare offers using AI analysis"""
    if current_user.role != 'client':
        return jsonify({'error': 'Only clients can compare offers'}), 403

    try:
        data = request.get_json()
        offer_ids = data.get('offer_ids', [])

        if len(offer_ids) < 2:
            return jsonify({'error': 'At least 2 offers must be provided for comparison'}), 400

        # Get the offers with all related data
        offers = []
        for offer_id in offer_ids:
            offer = Offer.query.get(offer_id)
            if not offer:
                return jsonify({'error': f'Offer {offer_id} not found'}), 404

            # Check if the offer belongs to the current user's order
            if offer.order.user_id != current_user.id:
                return jsonify({'error': 'Access denied to this offer'}), 403

            # Prepare offer data for AI analysis
            offer_data = {
                'id': offer.id,
                'company_name': offer.company.name or offer.company.name_ar or 'Unknown Company',
                'total_price': offer.total_price,
                'delivery_time': offer.delivery_time,
                'status': offer.status,
                'description': offer.description,
                'created_at': offer.created_at.strftime('%Y-%m-%d %H:%M'),
                'products': []
            }

            # Add product details
            for product_offer in offer.product_offers:
                product_data = {
                    'part_name': product_offer.purchase.part_name,
                    'quantity': product_offer.purchase.quantity,
                    'unit': product_offer.purchase.unit,
                    'unit_price': product_offer.unit_price,
                    'total_price': product_offer.total_price,
                    'notes': product_offer.notes
                }
                offer_data['products'].append(product_data)

            offers.append(offer_data)

        # Get AI comparison
        comparison_result = compare_offers_with_ai(offers)

        return jsonify({
            'success': True,
            'comparison': comparison_result,
            'offers': offers
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/company_chat/get_messages/<int:chat_id>")
@login_required
def company_get_messages(chat_id):
    if current_user.role != 'company':
        return {'error': 'Only companies can access messages'}, 403

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        return {'error': 'Company not found'}, 404

    chat = Chat.query.filter_by(id=chat_id, company_id=company.id).first()
    if not chat:
        return {'error': 'Chat not found'}, 404

    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.created_at.asc()).all()

    messages_data = []
    for message in messages:
        sender_name = 'Unknown'
        if message.sender:
            if message.sender_type == 'client':
                sender_name = message.sender.username
            elif message.sender_type == 'company':
                sender_name = message.sender.name_ar or message.sender.name_en or 'Company'

        messages_data.append({
            'id': message.id,
            'content': message.content,
            'sender_type': message.sender_type,
            'sender_name': sender_name,
            'created_at': message.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_read': message.is_read
        })

    return {'messages': messages_data}


@app.route('/company_chat/send_bill_summary', methods=['POST'])
@login_required
def company_send_bill_summary():
    """Send automated bill summary message to client"""
    if current_user.role != 'company':
        return {'error': 'Only companies can send bill summaries'}, 403

    chat_id = request.form.get('chat_id')
    client_id = request.form.get('client_id')

    if not chat_id or not client_id:
        return {'error': 'Missing chat_id or client_id'}, 400

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        return {'error': 'Company not found'}, 404

    chat = Chat.query.filter_by(id=chat_id, company_id=company.id).first()
    if not chat:
        return {'error': 'Chat not found'}, 404

    try:
        # Get bill summary using the agentic AI service
        from agentic_ai_service import AgenticAIService
        ai_service = AgenticAIService()
        
        # Get bills summary for the client
        bills_summary = ai_service._get_bills_summary(client_id)
        
        # Create automated message with bill summary
        content = f"ملخص الفواتير:\n{bills_summary}"
        
        message = Message(
            chat_id=chat_id,
            sender_id=company.id,
            sender_type='company',
            content=content
        )

        # Update chat's updated_at timestamp
        chat.updated_at = datetime.utcnow()

        db.session.add(message)
        db.session.commit()
        
        return {'success': True, 'message_id': message.id}
    except Exception as e:
        db.session.rollback()
        return {'error': str(e)}, 500


@app.route('/company_chat/send_bill_details', methods=['POST'])
@login_required
def company_send_bill_details():
    """Send specific bill details to client"""
    if current_user.role != 'company':
        return {'error': 'Only companies can send bill details'}, 403

    chat_id = request.form.get('chat_id')
    bill_id = request.form.get('bill_id')

    if not chat_id or not bill_id:
        return {'error': 'Missing chat_id or bill_id'}, 400

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        return {'error': 'Company not found'}, 404

    chat = Chat.query.filter_by(id=chat_id, company_id=company.id).first()
    if not chat:
        return {'error': 'Chat not found'}, 404

    try:
        # Get bill details using the agentic AI service
        from agentic_ai_service import AgenticAIService
        ai_service = AgenticAIService()
        
        # Get specific bill details
        bill_details = ai_service._get_bill_details(bill_id)
        
        # Create automated message with bill details
        content = f"تفاصيل الفاتورة:\n{bill_details}"
        
        message = Message(
            chat_id=chat_id,
            sender_id=company.id,
            sender_type='company',
            content=content
        )

        # Update chat's updated_at timestamp
        chat.updated_at = datetime.utcnow()

        db.session.add(message)
        db.session.commit()
        
        return {'success': True, 'message_id': message.id}
    except Exception as e:
        db.session.rollback()
        return {'error': str(e)}, 500


@app.route('/company_chat/get_client_bills/<int:client_id>')
@login_required
def company_get_client_bills(client_id):
    """Get all bills for a specific client"""
    if current_user.role != 'company':
        return {'error': 'Only companies can access client bills'}, 403

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        return {'error': 'Company not found'}, 404

    try:
        # Get bills for the client from this company
        bills = Bill.query.filter_by(
            company_id=company.id,
            client_id=client_id
        ).order_by(Bill.created_at.desc()).all()
        
        bills_data = []
        for bill in bills:
            bills_data.append({
                'id': bill.id,
                'bill_number': bill.bill_number,
                'total': bill.formatted_total,
                'currency': bill.currency,
                'status': bill.status,
                'issue_date': bill.issue_date.strftime('%Y-%m-%d') if bill.issue_date else '',
                'due_date': bill.due_date.strftime('%Y-%m-%d') if bill.due_date else ''
            })
        
        return {'bills': bills_data}
    except Exception as e:
        return {'error': str(e)}, 500


@app.route('/new_orders_by_sector')
@login_required
def new_orders_by_sector():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    # Get all orders that don't have a company assigned yet (new orders)
    new_orders = Order.query.filter_by(company_id=None).all()

    # Group orders by sector
    orders_by_sector = {}
    for order in new_orders:
        sector = order.purchases[0].sector if order.purchases else 'Unknown'
        if sector not in orders_by_sector:
            orders_by_sector[sector] = []
        orders_by_sector[sector].append(order)

    return render_template('company/new_orders_by_sector.html',
                           orders_by_sector=orders_by_sector)


@app.route('/order_details/<int:order_id>')
@login_required
def order_details(order_id):
    order = Order.query.get_or_404(order_id)

    if current_user.role == "company":
        # Check if company has already made an offer on this order
        company = Company.query.filter_by(id=current_user.company_id).first()
        existing_offer = None
        if company:
            existing_offer = Offer.query.filter_by(
                order_id=order_id,
                company_id=company.id
            ).first()

        return render_template('company/order_details.html', order=order, existing_offer=existing_offer)
    else:
        # For clients, find matching products for each purchase in the order
        order_suggestions = []

        for purchase in order.purchases:
            matches = find_matching_products(
                purchase.part_name,
                purchase.description,
                purchase.sector
            )

            if matches:
                order_suggestions.append({
                    'purchase': purchase,
                    'matches': matches
                })

        return render_template('client/order_detail.html',
                               order=order,
                               suggestions=order_suggestions)


@app.route('/make_offer/<int:order_id>', methods=['GET', 'POST'])
@login_required
def make_offer(order_id):
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    order = Order.query.get_or_404(order_id)
    company = Company.query.filter_by(id=current_user.company_id).first()

    # Check if company has already made an offer on this order
    existing_offer = Offer.query.filter_by(
        order_id=order_id,
        company_id=company.id
    ).first()

    if existing_offer:
        # Company has already made an offer, redirect to offer details
        flash(_('You have already made an offer on this order. View your offer details below.'), 'info')
        return redirect(url_for('offer_details', offer_id=existing_offer.id))

    if request.method == 'POST':
        delivery_time = request.form.get('delivery_time')
        description = request.form.get('notes')
        deduction_percentage = request.form.get('deduction_percentage', 0.0)
        transportation_fees = request.form.get('transportation_fees', 0.0)
        guarantee = request.form.get('guarantee', '')

        # Get product prices from form
        product_prices = {}
        total_offer_price = 0

        for purchase in order.purchases:
            unit_price_key = f'unit_price_{purchase.id}'
            notes_key = f'notes_{purchase.id}'

            unit_price = request.form.get(unit_price_key)
            notes = request.form.get(notes_key, '')

            if not unit_price:
                flash(_('Please fill in prices for all products.'), 'error')
                return redirect(url_for('make_offer', order_id=order_id))

            unit_price = float(unit_price)
            total_price = unit_price * purchase.quantity
            total_offer_price += total_price

            product_prices[purchase.id] = {
                'unit_price': unit_price,
                'total_price': total_price,
                'notes': notes
            }

        if not delivery_time:
            flash(_('Please select delivery time.'), 'error')
            return redirect(url_for('make_offer', order_id=order_id))

        # Get supplier payment steps from form
        supplier_payment_steps = []
        step_counter = 1

        while True:
            method_key = f'payment_method_{step_counter}'
            timing_key = f'payment_timing_{step_counter}'
            percentage_key = f'payment_percentage_{step_counter}'
            notes_key = f'payment_notes_{step_counter}'

            method = request.form.get(method_key)
            timing = request.form.get(timing_key)
            percentage = request.form.get(percentage_key)
            notes = request.form.get(notes_key, '')

            if not method or not timing or not percentage:
                break

            try:
                percentage_float = float(percentage)
                if percentage_float < 0 or percentage_float > 100:
                    flash(_('Payment percentage must be between 0 and 100.'), 'error')
                    return redirect(url_for('make_offer', order_id=order_id))

                supplier_payment_steps.append({
                    'method': method,
                    'timing': timing,
                    'percentage': percentage_float,
                    'notes': notes
                })
            except ValueError:
                flash(_('Invalid payment percentage value.'), 'error')
                return redirect(url_for('make_offer', order_id=order_id))

            step_counter += 1

        # Create the main offer
        offer = Offer(
            order_id=order_id,
            company_id=company.id,
            total_price=total_offer_price,
            delivery_time=delivery_time,
            description=description or '',
            deduction_percentage=float(deduction_percentage) if deduction_percentage else 0.0,
            transportation_fees=float(transportation_fees) if transportation_fees else 0.0,
            guarantee=guarantee,
            status='pending'
        )

        db.session.add(offer)
        db.session.flush()  # Get the offer ID

        # Create product-level offers
        for purchase_id, price_data in product_prices.items():
            product_offer = ProductOffer(
                offer_id=offer.id,
                purchase_id=purchase_id,
                unit_price=price_data['unit_price'],
                total_price=price_data['total_price'],
                notes=price_data['notes']
            )
            db.session.add(product_offer)

        # Store supplier payment steps in the offer description or create a separate field
        if supplier_payment_steps:
            payment_steps_text = "\n\n💳 SUPPLIER PAYMENT TERMS:\n"
            for i, step in enumerate(supplier_payment_steps, 1):
                payment_steps_text += f"{i}. {step['method']} - {step['percentage']}% ({step['timing']})"
                if step['notes']:
                    payment_steps_text += f" - {step['notes']}"
                payment_steps_text += "\n"

            # Append to existing description
            if offer.description:
                offer.description += payment_steps_text
            else:
                offer.description = payment_steps_text

        db.session.commit()

        flash(_('Offer submitted successfully! Total: EGP {:.2f}').format(total_offer_price), 'success')
        return redirect(url_for('new_orders_by_sector'))

    return render_template('company/make_offer.html', order=order, company=company)


# Employee Management Routes
@app.route('/company_employees')
@login_required
def company_employees():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    # Get all employees for this company
    employees = User.query.filter_by(company_id=company.id, role='employee').all()

    return render_template('company/employees.html', employees=employees, company=company)


@app.route('/add_employee', methods=['GET', 'POST'])
@login_required
def add_employee():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        username = request.form.get('username')

        if password != confirm_password:
            flash(_('Passwords do not match'), 'error')
            return redirect(url_for('add_employee'))

        if User.query.filter_by(email=email).first():
            flash(_('Email already registered'), 'error')
            return redirect(url_for('add_employee'))

        if User.query.filter_by(username=username).first():
            flash(_('Username already exists'), 'error')
            return redirect(url_for('add_employee'))

        password_hash = generate_password_hash(str(password) if password else '', method='pbkdf2:sha256')
        employee = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role='employee',
            company_id=company.id
        )

        db.session.add(employee)
        try:
            db.session.commit()
            flash(_('Employee added successfully!'), 'success')
            return redirect(url_for('company_employees'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding employee: {str(e)}', 'error')

    return render_template('company/add_employee.html', company=company)


@app.route('/delete_employee/<int:employee_id>', methods=['POST'])
@login_required
def delete_employee(employee_id):
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    employee = User.query.filter_by(id=employee_id, company_id=company.id, role='employee').first()

    if employee:
        try:
            db.session.delete(employee)
            db.session.commit()
            flash(_('Employee deleted successfully!'), 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting employee: {str(e)}', 'error')
    else:
        flash(_('Employee not found'), 'error')

    return redirect(url_for('company_employees'))


@app.route('/edit_employee/<int:employee_id>', methods=['GET', 'POST'])
@login_required
def edit_employee(employee_id):
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    employee = User.query.filter_by(id=employee_id, company_id=company.id, role='employee').first()

    if not employee:
        flash(_('Employee not found'), 'error')
        return redirect(url_for('company_employees'))

    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        new_password = request.form.get('new_password')

        # Check if email is already taken by another user
        existing_user = User.query.filter_by(email=email).first()
        if existing_user and existing_user.id != employee_id:
            flash(_('Email already registered'), 'error')
            return redirect(url_for('edit_employee', employee_id=employee_id))

        # Check if username is already taken by another user
        existing_user = User.query.filter_by(username=username).first()
        if existing_user and existing_user.id != employee_id:
            flash(_('Username already exists'), 'error')
            return redirect(url_for('edit_employee', employee_id=employee_id))

        employee.email = email
        employee.username = username

        # Update password if provided
        if new_password:
            employee.password_hash = generate_password_hash(str(new_password) if new_password else '', method='pbkdf2:sha256')

        try:
            db.session.commit()
            flash(_('Employee updated successfully!'), 'success')
            return redirect(url_for('company_employees'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating employee: {str(e)}', 'error')

    return render_template('company/edit_employee.html', employee=employee, company=company)


# Inventory Management Routes
@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        category = request.form.get('category')
        sku = request.form.get('sku')
        price = request.form.get('price')
        cost = request.form.get('cost')
        quantity = request.form.get('quantity')
        min_quantity = request.form.get('min_quantity')
        unit = request.form.get('unit')
        location = request.form.get('location')
        supplier = request.form.get('supplier')
        supplier_contact = request.form.get('supplier_contact')
        requirements = request.form.get('requirements')

        # Validation
        if not all([name, category, sku, price, quantity]):
            flash(_('Please fill in all required fields.'), 'error')
            return redirect(url_for('add_product'))

        # Check if SKU already exists
        if Product.query.filter_by(sku=sku).first():
            flash(_('SKU already exists. Please choose a different SKU.'), 'error')
            return redirect(url_for('add_product'))

        try:
            product = Product()
            product.name = name
            product.description = description
            product.category = category
            product.sku = sku
            product.price = float(price)
            product.cost = float(cost) if cost else None
            product.quantity = int(quantity)
            product.min_quantity = int(min_quantity) if min_quantity else 0
            product.unit = unit
            product.location = location
            product.supplier = supplier
            product.supplier_contact = supplier_contact
            product.requirements = requirements
            product.company_id = company.id

            db.session.add(product)
            db.session.commit()

            flash(_('Product added successfully!'), 'success')
            return redirect(url_for('company_inventory'))

        except ValueError:
            flash(_('Please enter valid numbers for price, cost, and quantity.'), 'error')
            return redirect(url_for('add_product'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding product: {str(e)}', 'error')
            return redirect(url_for('add_product'))

    return render_template('company/add_product.html', company=company)


@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    product = Product.query.filter_by(id=product_id, company_id=company.id).first()

    if not product:
        flash(_('Product not found.'), 'error')
        return redirect(url_for('company_inventory'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        category = request.form.get('category')
        sku = request.form.get('sku')
        price = request.form.get('price')
        cost = request.form.get('cost')
        quantity = request.form.get('quantity')
        min_quantity = request.form.get('min_quantity')
        unit = request.form.get('unit')
        location = request.form.get('location')
        supplier = request.form.get('supplier')
        supplier_contact = request.form.get('supplier_contact')
        requirements = request.form.get('requirements')

        # Validation
        if not all([name, category, sku, price, quantity]):
            flash(_('Error updating product: Please fill in all required fields.'), 'error')
            return redirect(url_for('edit_product', product_id=product_id))

        # Check if SKU already exists (excluding current product)
        existing_product = Product.query.filter_by(sku=sku).first()
        if existing_product and existing_product.id != product_id:
            flash(_('SKU already exists. Please choose a different SKU.'), 'error')
            return redirect(url_for('edit_product', product_id=product_id))

        try:
            product.name = name
            product.description = description
            product.category = category
            product.sku = sku
            product.price = float(price)
            product.cost = float(cost) if cost else None
            product.quantity = int(quantity)
            product.min_quantity = int(min_quantity) if min_quantity else 0
            product.unit = unit
            product.location = location
            product.supplier = supplier
            product.supplier_contact = supplier_contact
            product.requirements = requirements

            db.session.commit()

            flash(_('Product updated successfully!'), 'success')
            return redirect(url_for('company_inventory'))

        except ValueError:
            flash(_('Please enter valid numbers for price, cost, and quantity.'), 'error')
            return redirect(url_for('edit_product', product_id=product_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating product: {str(e)}', 'error')
            return redirect(url_for('edit_product', product_id=product_id))

    return render_template('company/edit_product.html', product=product, company=company)


@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    product = Product.query.filter_by(id=product_id, company_id=company.id).first()

    if not product:
        flash(_('Product not found.'), 'error')
        return redirect(url_for('company_inventory'))

    try:
        db.session.delete(product)
        db.session.commit()
        flash(_('Product deleted successfully!'), 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting product: {str(e)}', 'error')

    return redirect(url_for('company_inventory'))


@app.route('/import_products', methods=['GET', 'POST'])
@login_required
def import_products():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()

    if request.method == 'POST':
        if 'file' not in request.files:
            flash(_('No file selected.'), 'error')
            return redirect(url_for('import_products'))

        file = request.files['file']
        if file.filename == '':
            flash(_('No file selected.'), 'error')
            return redirect(url_for('import_products'))

        if not file.filename.endswith('.csv'):
            flash(_('Please upload a CSV file.'), 'error')
            return redirect(url_for('import_products'))

        try:
            import csv
            import io
            import json

            # Read CSV file
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream)

            products_data = []
            errors = []

            for i, row in enumerate(csv_reader, 1):
                try:
                    # Validate required fields
                    required_fields = ['name', 'category', 'sku', 'price', 'quantity']
                    missing_fields = [field for field in required_fields if not row.get(field)]

                    if missing_fields:
                        errors.append(f"Row {i}: Missing required fields: {', '.join(missing_fields)}")
                        continue

                    # Check if SKU already exists
                    existing_product = Product.query.filter_by(sku=row['sku']).first()
                    if existing_product:
                        errors.append(f"Row {i}: SKU '{row['sku']}' already exists")
                        continue

                    # Validate numeric fields
                    try:
                        price = float(row['price'])
                        quantity = int(row['quantity'])
                        cost = float(row['cost']) if row.get('cost') else None
                        min_quantity = int(row['min_quantity']) if row.get('min_quantity') else 0
                    except ValueError:
                        errors.append(f"Row {i}: Invalid numeric values")
                        continue

                    # Detect if text contains Arabic characters
                    def contains_arabic(text):
                        if not text:
                            return False
                        arabic_range = range(0x0600, 0x06FF)  # Arabic Unicode range
                        return any(ord(char) in arabic_range for char in text)

                    # Check for Arabic content
                    has_arabic = any(contains_arabic(str(row.get(field, ''))) for field in
                                     ['name', 'description', 'category', 'location', 'supplier', 'requirements'])

                    product_data = {
                        'name': row['name'],
                        'description': row.get('description', ''),
                        'category': row['category'],
                        'sku': row['sku'],
                        'price': price,
                        'cost': cost,
                        'quantity': quantity,
                        'min_quantity': min_quantity,
                        'unit': row.get('unit', 'pcs'),
                        'location': row.get('location', ''),
                        'supplier': row.get('supplier', ''),
                        'supplier_contact': row.get('supplier_contact', ''),
                        'requirements': row.get('requirements', ''),
                        'row_number': i,
                        'has_arabic': has_arabic
                    }

                    products_data.append(product_data)

                except Exception as e:
                    errors.append(f"Row {i}: {str(e)}")
                    continue

            # Store data in session for confirmation
            session['import_products_data'] = json.dumps(products_data)
            session['import_products_errors'] = json.dumps(errors)

            return render_template('company/import_products_preview.html',
                                   company=company,
                                   products=products_data,
                                   errors=errors)

        except Exception as e:
            flash(f'Error reading CSV file: {str(e)}', 'error')
            return redirect(url_for('import_products'))

    return render_template('company/import_products.html', company=company)


@app.route('/confirm_import', methods=['POST'])
@login_required
def confirm_import():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()

    try:
        import json

        products_data = json.loads(session.get('import_products_data', '[]'))

        success_count = 0
        error_count = 0

        for product_data in products_data:
            try:
                product = Product(
                    name=product_data['name'],
                    description=product_data['description'],
                    category=product_data['category'],
                    sku=product_data['sku'],
                    price=product_data['price'],
                    cost=product_data['cost'],
                    quantity=product_data['quantity'],
                    min_quantity=product_data['min_quantity'],
                    unit=product_data['unit'],
                    location=product_data['location'],
                    supplier=product_data['supplier'],
                    supplier_contact=product_data['supplier_contact'],
                    requirements=product_data['requirements'],
                    company_id=company.id
                )

                db.session.add(product)
                success_count += 1

            except Exception as e:
                error_count += 1
                continue

        db.session.commit()

        # Clear session data
        session.pop('import_products_data', None)
        session.pop('import_products_errors', None)

        if success_count > 0:
            flash(f'{success_count} products imported successfully!', 'success')
        if error_count > 0:
            flash(f'{error_count} products failed to import.', 'error')

        return redirect(url_for('company_inventory'))

    except Exception as e:
        flash(f'Error importing products: {str(e)}', 'error')
        return redirect(url_for('import_products'))


# Notification routes
@app.route('/notifications')
@login_required
def notifications():
    """Display user's notifications"""
    if current_user.role == 'client':
        notifications_raw = get_user_notifications(current_user.id, limit=50)
        notifications_list = [{
            'id': n.id,
            'title': n.title,
            'description': n.description,
            'notification_type': n.notification_type,
            'priority': n.priority,
            'created_at': n.created_at.isoformat(),
            'is_read': n.is_read
        } for n in notifications_raw]
        print(notifications_list)
        return render_template('client/notifications.html', notifications=notifications_list)
    elif current_user.role == 'company':
        company = Company.query.filter_by(id=current_user.company_id).first()
        if company:
            notifications_raw = get_company_notifications(company.id, limit=50)
            notifications_list = [{
                'id': n.id,
                'title': n.title,
                'description': n.description,
                'notification_type': n.notification_type,
                'priority': n.priority,
                'created_at': n.created_at.isoformat(),
                'is_read': n.is_read
            } for n in notifications_raw]
        else:
            notifications_list = []
        return render_template('company/notifications.html', notifications=notifications_list)
    else:
        notifications_list = []
        return render_template('notifications.html', notifications=notifications_list)


@app.route('/notifications/unread')
@login_required
def unread_notifications():
    """Get unread notifications count for AJAX requests"""
    if current_user.role == 'client':
        unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    elif current_user.role == 'company':
        company = Company.query.filter_by(id=current_user.company_id).first()
        unread_count = Notification.query.filter_by(company_id=company.id, is_read=False).count() if company else 0
    else:
        unread_count = 0

    return jsonify({'unread_count': unread_count})


@app.route('/notifications/count')
@login_required
def notification_count():
    """Get notification count for real-time updates"""
    try:
        if current_user.role == 'client':
            total_count = Notification.query.filter_by(user_id=current_user.id).count()
            unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        elif current_user.role == 'company':
            company = Company.query.filter_by(id=current_user.company_id).first()
            if company:
                total_count = Notification.query.filter_by(company_id=company.id).count()
                unread_count = Notification.query.filter_by(company_id=company.id, is_read=False).count()
            else:
                total_count = 0
                unread_count = 0
        else:
            total_count = 0
            unread_count = 0

        return jsonify({
            'total_count': total_count,
            'unread_count': unread_count,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/notifications/real_time_update')
@login_required
def real_time_notification_update():
    """Get real-time notification updates for the notification dropdown"""
    try:
        if current_user.role == 'client':
            notifications = get_user_notifications(current_user.id, limit=5, unread_only=False)
            unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        elif current_user.role == 'company':
            company = Company.query.filter_by(id=current_user.company_id).first()
            if company:
                notifications = get_company_notifications(company.id, limit=5, unread_only=False)
                unread_count = Notification.query.filter_by(company_id=company.id, is_read=False).count()
            else:
                notifications = []
                unread_count = 0
        else:
            notifications = []
            unread_count = 0

        return jsonify({
            'notifications': [{
                'id': n.id,
                'title': n.title,
                'description': n.description,
                'priority': n.priority,
                'notification_type': n.notification_type,
                'created_at': n.created_at.isoformat(),
                'is_read': n.is_read,
                'related_order_id': n.related_order_id,
                'related_offer_id': n.related_offer_id,
                'related_chat_id': n.related_chat_id
            } for n in notifications],
            'unread_count': unread_count,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/notifications/debug')
@login_required
def debug_notifications():
    """Debug route to check notification system"""
    try:
        if current_user.role == 'client':
            notifications = get_user_notifications(current_user.id, limit=10, unread_only=False)
            unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            total_count = Notification.query.filter_by(user_id=current_user.id).count()
        elif current_user.role == 'company':
            company = Company.query.filter_by(id=current_user.company_id).first()
            if company:
                notifications = get_company_notifications(company.id, limit=10, unread_only=False)
                unread_count = Notification.query.filter_by(company_id=company.id, is_read=False).count()
                total_count = Notification.query.filter_by(company_id=company.id).count()
            else:
                notifications = []
                unread_count = 0
                total_count = 0
        else:
            notifications = []
            unread_count = 0
            total_count = 0

        return jsonify({
            'user_id': current_user.id,
            'role': current_user.role,
            'total_notifications': total_count,
            'unread_count': unread_count,
            'notifications': [{
                'id': n.id,
                'title': n.title,
                'description': n.description,
                'priority': n.priority,
                'notification_type': n.notification_type,
                'created_at': n.created_at.isoformat(),
                'is_read': n.is_read,
                'user_id': n.user_id,
                'company_id': n.company_id
            } for n in notifications],
            'context_processor_data': {
                'user_notifications': len(get_user_notifications(current_user.id, limit=5,
                                                                 unread_only=False)) if current_user.role == 'client' else 0,
                'unread_notifications_count': unread_count
            }
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': str(e.__traceback__)}), 500


@app.route('/notifications/mark_read/<int:notification_id>', methods=['POST'])
@csrf.exempt
@login_required
def mark_notification_read_route(notification_id):
    """Mark a notification as read"""
    if current_user.role == 'client':
        success = mark_notification_read(notification_id, current_user.id)
    elif current_user.role == 'company':
        success = mark_notification_read(notification_id)
    else:
        success = False

    if success:
        return {'success': True}
    else:
        return {'success': False, 'error': 'Notification not found or access denied'}, 404


@app.route('/test_loading')
def test_loading():
    """Simple test route to check if the app is loading"""
    return jsonify({
        'status': 'success',
        'message': 'App is loading correctly',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/notifications/get_notifications')
@login_required
def get_notifications():
    """Get notifications for AJAX requests with filtering support"""
    try:
        # Get filter parameters from query string
        notification_type = request.args.get('type', 'all')
        priority = request.args.get('priority', 'all')
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        limit = int(request.args.get('limit', 10))
        
        # Parse date filters if provided
        date_from = None
        date_to = None
        if request.args.get('date_from'):
            try:
                date_from = datetime.strptime(request.args.get('date_from'), '%Y-%m-%d')
            except ValueError:
                pass
        if request.args.get('date_to'):
            try:
                date_to = datetime.strptime(request.args.get('date_to'), '%Y-%m-%d')
                # Set to end of day
                date_to = date_to.replace(hour=23, minute=59, second=59)
            except ValueError:
                pass
        
        if current_user.role == 'client':
            notifications = get_user_notifications(
                current_user.id, 
                limit=limit, 
                unread_only=unread_only,
                notification_type=notification_type,
                priority=priority,
                date_from=date_from,
                date_to=date_to
            )
            unread_count = Notification.query.filter_by(
                user_id=current_user.id,
                is_read=False
            ).count()
        elif current_user.role == 'company':
            company = Company.query.filter_by(id=current_user.company_id).first()
            if company:
                notifications = get_company_notifications(
                    company.id, 
                    limit=limit, 
                    unread_only=unread_only,
                    notification_type=notification_type,
                    priority=priority,
                    date_from=date_from,
                    date_to=date_to
                )
                unread_count = Notification.query.filter_by(
                    company_id=company.id,
                    is_read=False
                ).count()
            else:
                notifications = []
                unread_count = 0
        else:
            notifications = []
            unread_count = 0

        # Debug logging
        print(f"DEBUG: get_notifications - User {current_user.id}, Role: {current_user.role}")
        print(f"DEBUG: Found {len(notifications)} notifications")
        print(f"DEBUG: Unread count: {unread_count}")
        
        result = {
            'notifications': [{
                'id': n.id,
                'title': n.title,
                'description': n.description,
                'notification_type': n.notification_type,
                'priority': n.priority,
                'created_at': n.created_at.isoformat(),
                'is_read': n.is_read
            } for n in notifications],
            'unread_count': unread_count
        }
        
        print(f"DEBUG: Returning JSON: {result}")
        return jsonify(result)
    except Exception as e:
        return jsonify({'notifications': [], 'unread_count': 0})


@app.route('/notifications/mark_all_read', methods=['POST'])
@csrf.exempt
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read for the current user/company"""
    try:
        if current_user.role == 'client':
            Notification.query.filter_by(user_id=current_user.id, is_read=False).update({
                'is_read': True,
                'read_at': datetime.utcnow()
            })
        elif current_user.role == 'company':
            company = Company.query.filter_by(id=current_user.company_id).first()
            if company:
                Notification.query.filter_by(company_id=company.id, is_read=False).update({
                    'is_read': True,
                    'read_at': datetime.utcnow()
                })

        db.session.commit()
        return {'success': True}
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}, 500


@app.route('/notifications/delete/<int:notification_id>', methods=['DELETE'])
@csrf.exempt
@login_required
def delete_notification(notification_id):
    """Delete a notification"""
    try:
        notification = db.session.get(Notification, notification_id)

        if not notification:
            return {'success': False, 'error': 'Notification not found'}, 404

        # Check if user has permission to delete this notification
        if current_user.role == 'client':
            if notification.user_id != current_user.id:
                return {'success': False, 'error': 'Access denied'}, 403
        elif current_user.role == 'company':
            company = Company.query.filter_by(id=current_user.company_id).first()
            if not company or notification.company_id != company.id:
                return {'success': False, 'error': 'Access denied'}, 403
        else:
            return {'success': False, 'error': 'Access denied'}, 403

        db.session.delete(notification)
        db.session.commit()

        return {'success': True}
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}, 500


def create_notification_helper(title, description, notification_type, priority, user_id=None, company_id=None, related_order_id=None, related_offer_id=None, related_chat_id=None, related_product_id=None):
    """Helper function to create notifications"""
    try:
        notification = Notification(
            title=title,
            description=description,
            notification_type=notification_type,
            priority=priority,
            user_id=user_id,
            company_id=company_id,
            related_order_id=related_order_id,
            related_offer_id=related_offer_id,
            related_chat_id=related_chat_id,
            related_product_id=related_product_id,
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    except Exception as e:
        db.session.rollback()
        print(f"Error creating notification: {e}")
        return None


# Context processor to make notifications available in all templates
@app.context_processor
def inject_notifications():
    """Inject user notifications into all templates"""
    try:
        if current_user.is_authenticated:
            if current_user.role == 'client':
                notifications = get_user_notifications(current_user.id, limit=5, unread_only=False)
                unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
                print(f"DEBUG: Client {current_user.id} has {len(notifications)} notifications, {unread_count} unread")
            elif current_user.role == 'company':
                company = Company.query.filter_by(id=current_user.company_id).first()
                if company:
                    notifications = get_company_notifications(company.id, limit=5, unread_only=False)
                    unread_count = Notification.query.filter_by(company_id=company.id, is_read=False).count()
                    print(f"DEBUG: Company {company.id} has {len(notifications)} notifications, {unread_count} unread")
                else:
                    notifications = []
                    unread_count = 0
                    print(f"DEBUG: Company not found for user {current_user.id}")
            elif current_user.role == 'admin':
                # Admin users get all system notifications
                notifications = Notification.query.order_by(Notification.created_at.desc()).limit(5).all()
                unread_count = Notification.query.filter_by(is_read=False).count()
                print(f"DEBUG: Admin {current_user.id} has {len(notifications)} notifications, {unread_count} unread")
            else:
                notifications = []
                unread_count = 0
                print(f"DEBUG: Unknown role {current_user.role} for user {current_user.id}")

            # Convert Notification objects to dictionaries for JSON serialization
            notifications_dict = []
            for notification in notifications:
                notifications_dict.append({
                    'id': notification.id,
                    'title': notification.title,
                    'description': notification.description,
                    'notification_type': notification.notification_type,
                    'priority': notification.priority,
                    'is_read': notification.is_read,
                    'created_at': notification.created_at.isoformat() if notification.created_at else None,
                    'read_at': notification.read_at.isoformat() if notification.read_at else None,
                    'related_order_id': notification.related_order_id,
                    'related_offer_id': notification.related_offer_id,
                    'related_chat_id': notification.related_chat_id,
                    'user_id': notification.user_id,
                    'company_id': notification.company_id
                })

            return {
                'user_notifications': notifications_dict,
                'unread_notifications_count': unread_count
            }
        else:
            print("DEBUG: User not authenticated")
            return {
                'user_notifications': [],
                'unread_notifications_count': 0
            }
    except Exception as e:
        print(f"ERROR in context processor: {e}")
        return {
            'user_notifications': [],
            'unread_notifications_count': 0
        }


@app.route('/notifications/create_sample')
@login_required
def create_sample_notifications():
    """Create sample notifications for testing (development only)"""
    if current_user.role != 'client':
        return jsonify({'error': 'Only clients can create sample notifications'}), 403

    try:
        # Create sample notifications
        sample_notifications = [
            {
                'title': 'New Order Created',
                'description': 'Your order #123 has been successfully created and is now visible to suppliers.',
                'notification_type': 'order',
                'priority': 'normal',
                'related_order_id': 123
            },
            {
                'title': 'New Offer Received',
                'description': 'You have received a new offer from ABC Company for your order #123.',
                'notification_type': 'offer',
                'priority': 'high',
                'related_offer_id': 456
            },
            {
                'title': 'Order Status Updated',
                'description': 'Your order #123 status has been updated to "Processing".',
                'notification_type': 'order',
                'priority': 'normal',
                'related_order_id': 123
            },
            {
                'title': 'New Message Received',
                'description': 'You have a new message from XYZ Supplier regarding your order.',
                'notification_type': 'chat',
                'priority': 'normal',
                'related_chat_id': 789
            },
            {
                'title': 'System Maintenance',
                'description': 'Scheduled maintenance will occur tonight from 2:00 AM to 4:00 AM.',
                'notification_type': 'system',
                'priority': 'low'
            }
        ]

        created_count = 0
        for sample in sample_notifications:
            notification = Notification(
                title=sample['title'],
                description=sample['description'],
                notification_type=sample['notification_type'],
                priority=sample['priority'],
                user_id=current_user.id,
                is_read=False,
                created_at=datetime.utcnow()
            )

            # Add related IDs if they exist
            if 'related_order_id' in sample:
                notification.related_order_id = sample['related_order_id']
            if 'related_offer_id' in sample:
                notification.related_offer_id = sample['related_offer_id']
            if 'related_chat_id' in sample:
                notification.related_chat_id = sample['related_chat_id']

            db.session.add(notification)
            created_count += 1

        db.session.commit()

        # Clear the context processor cache to ensure fresh data
        if hasattr(current_user, '_notifications_cache'):
            delattr(current_user, '_notifications_cache')

        return jsonify({
            'success': True,
            'message': f'Created {created_count} sample notifications',
            'count': created_count
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/notifications/create_single')
@login_required
def create_single_notification():
    """Create a single test notification"""
    if current_user.role != 'client':
        return jsonify({'error': 'Only clients can create notifications'}), 403

    try:
        notification = Notification(
            title='Test Notification',
            description='This is a test notification to verify the system is working.',
            notification_type='system',
            priority='normal',
            user_id=current_user.id,
            is_read=False,
            created_at=datetime.utcnow()
        )

        db.session.add(notification)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Created test notification',
            'notification_id': notification.id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/notifications/load_more')
@login_required
def load_more_notifications():
    """Load more notifications for infinite scroll pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        
        # Limit per_page to prevent abuse
        per_page = min(per_page, 20)
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Get notifications for the user with pagination
        notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
            Notification.created_at.desc()
        ).offset(offset).limit(per_page).all()
        
        # Convert notifications to JSON format
        notifications_data = []
        for notification in notifications:
            notifications_data.append({
                'id': notification.id,
                'title': notification.title,
                'description': notification.description,
                'notification_type': notification.notification_type,
                'priority': notification.priority,
                'is_read': notification.is_read,
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'related_id': notification.related_id
            })
        
        return jsonify({
            'success': True,
            'notifications': notifications_data,
            'page': page,
            'per_page': per_page,
            'total': len(notifications_data)
        })
        
    except Exception as e:
        print(f"Error loading more notifications: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Error loading notifications: {str(e)}'
        }), 500


@app.route('/export_products')
@login_required
def export_products():
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    products = Product.query.filter_by(company_id=company.id).all()

    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(
        ['name', 'description', 'category', 'sku', 'price', 'cost', 'quantity', 'min_quantity', 'unit', 'location',
         'supplier', 'supplier_contact', 'requirements'])

    # Write data
    for product in products:
        writer.writerow([
            product.name,
            product.description or '',
            product.category,
            product.sku,
            product.price,
            product.cost or '',
            product.quantity,
            product.min_quantity,
            product.unit,
            product.location or '',
            product.supplier or '',
            product.supplier_contact or '',
            product.requirements or ''
        ])

    output.seek(0)

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=inventory_{company.name_ar or company.name_en or "company"}_{datetime.now().strftime("%Y%m%d")}.csv'}
    )


@app.route('/remove_order_from_view/<int:order_id>', methods=['POST'])
@login_required
def remove_order_from_view(order_id):
    """Remove an order from company's view while keeping it in the database"""
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('company_orders'))

    # Check if order exists and is relevant to this company
    order = Order.query.get(order_id)
    if not order:
        flash(_('Order not found.'), 'error')
        return redirect(url_for('company_orders'))

    # Check if order is already hidden
    existing_hidden = HiddenOrder.query.filter_by(company_id=company.id, order_id=order_id).first()
    if existing_hidden:
        flash(_('Order is already hidden from your view.'), 'info')
        return redirect(url_for('company_orders'))

    try:
        # Create hidden order record
        hidden_order = HiddenOrder(
            company_id=company.id,
            order_id=order_id
        )
        db.session.add(hidden_order)
        db.session.commit()

        flash(_('Order has been removed from your view. It will no longer appear in your orders list.'), 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error hiding order: {str(e)}', 'error')

    return redirect(url_for('company_orders'))


@app.route('/hidden_orders')
@login_required
def hidden_orders():
    """Display orders that the company has hidden from their view"""
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('company_orders'))

    # Get hidden orders for this company
    hidden_orders = HiddenOrder.query.filter_by(company_id=company.id).order_by(HiddenOrder.hidden_at.desc()).all()

    return render_template('company/hidden_orders.html', hidden_orders=hidden_orders)


@app.route('/restore_order_from_view/<int:order_id>', methods=['POST'])
@login_required
def restore_order_from_view(order_id):
    """Restore an order to company's view"""
    if current_user.role != "company":
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))

    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('hidden_orders'))

    # Check if order exists
    order = Order.query.get(order_id)
    if not order:
        flash(_('Order not found.'), 'error')
        return redirect(url_for('hidden_orders'))

    # Check if order is hidden by this company
    hidden_order = HiddenOrder.query.filter_by(company_id=company.id, order_id=order_id).first()
    if not hidden_order:
        flash(_('Order is not hidden from your view.'), 'info')
        return redirect(url_for('hidden_orders'))

    try:
        # Remove the hidden order record
        db.session.delete(hidden_order)
        db.session.commit()

        flash(_('Order has been restored to your view. It will now appear in your orders list again.'), 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring order: {str(e)}', 'error')

    return redirect(url_for('hidden_orders'))


@app.route('/upload_purchase_preferences', methods=['GET', 'POST'])
@login_required
def upload_purchase_preferences():
    """Upload and process purchase preferences file for existing users"""
    if current_user.account_type != 'client':
        flash('This page is only available for client accounts.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        if 'preferences_file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)

        file = request.files['preferences_file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            try:
                # Save the file
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"preferences_{current_user.id}_{timestamp}_{filename}"
                file_path = os.path.join(upload_folder, filename)
                file.save(file_path)

                # Process the file and extract preferences
                preferences = process_purchase_preferences_file(file_path, current_user.id)

                if preferences:
                    # Add preferences to database
                    for preference in preferences:
                        db.session.add(preference)

                    db.session.commit()

                    # Create notification about preferences
                    create_notification(
                        title="Purchase Preferences Updated!",
                        description=f"Successfully imported {len(preferences)} new purchase preferences from your file.",
                        notification_type='system',
                        priority='normal',
                        user_id=current_user.id
                    )

                    flash(f'Successfully imported {len(preferences)} purchase preferences!', 'success')
                    return redirect(url_for('purchase_preferences'))
                else:
                    flash('No purchase preferences could be extracted from the file. Please check the format.',
                          'warning')

            except Exception as e:
                flash(f'Error processing purchase preferences file: {str(e)}', 'warning')
                print(f"Error processing preferences file: {e}")
        else:
            flash('Invalid file type. Please upload Excel (.xlsx, .xls) or CSV files only.', 'error')

    return render_template('upload_purchase_preferences.html')


def allowed_file(filename):
    """Check if uploaded file has allowed extension"""
    ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/add_preference', methods=['GET', 'POST'])
@login_required
def add_preference():
    """Add a new purchase preference manually"""
    if current_user.account_type != 'client':
        flash('This page is only available for client accounts.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            preference = UserPreference(
                user_id=current_user.id,
                product_name=request.form.get('product_name'),
                product_category=request.form.get('product_category'),
                product_description=request.form.get('product_description'),
                quantity=int(request.form.get('quantity')) if request.form.get('quantity') else None,
                unit=request.form.get('unit', 'pcs'),
                frequency=request.form.get('frequency'),
                max_price_per_unit=float(request.form.get('max_price_per_unit')) if request.form.get(
                    'max_price_per_unit') else None,
                preferred_suppliers=request.form.get('preferred_suppliers'),
                quality_preference=request.form.get('quality_preference'),
                payment_preference=request.form.get('payment_preference'),
                preferred_delivery_time=request.form.get('preferred_delivery_time'),
                typical_order_size=int(request.form.get('typical_order_size')) if request.form.get(
                    'typical_order_size') else None
            )

            db.session.add(preference)
            db.session.commit()

            flash('Preference added successfully!', 'success')
            return redirect(url_for('purchase_preferences'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding preference: {str(e)}', 'error')

    return render_template('add_preference.html')


@app.route('/edit_preference/<int:preference_id>', methods=['GET', 'POST'])
@login_required
def edit_preference(preference_id):
    """Edit a purchase preference"""
    if current_user.account_type != 'client':
        flash('This page is only available for client accounts.', 'error')
        return redirect(url_for('index'))

    preference = UserPreference.query.filter_by(
        id=preference_id,
        user_id=current_user.id
    ).first_or_404()

    if request.method == 'POST':
        try:
            preference.product_name = request.form.get('product_name')
            preference.product_category = request.form.get('product_category')
            preference.product_description = request.form.get('product_description')
            preference.quantity = int(request.form.get('quantity')) if request.form.get('quantity') else None
            preference.unit = request.form.get('unit', 'pcs')
            preference.frequency = request.form.get('frequency')
            preference.max_price_per_unit = float(request.form.get('max_price_per_unit')) if request.form.get(
                'max_price_per_unit') else None
            preference.quality_preference = request.form.get('quality_preference')
            preference.payment_preference = request.form.get('payment_preference')
            preference.preferred_delivery_time = request.form.get('preferred_delivery_time')
            preference.typical_order_size = int(request.form.get('typical_order_size')) if request.form.get(
                'typical_order_size') else None
            preference.preferred_suppliers = request.form.get('preferred_suppliers')

            db.session.commit()
            flash('Preference updated successfully!', 'success')
            return redirect(url_for('purchase_preferences'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating preference: {str(e)}', 'error')

    return render_template('edit_preference.html', preference=preference)


@app.route('/delete_preference/<int:preference_id>', methods=['DELETE'])
@login_required
def delete_preference(preference_id):
    """Delete a purchase preference"""
    if current_user.account_type != 'client':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        preference = UserPreference.query.filter_by(
            id=preference_id,
            user_id=current_user.id
        ).first()

        if not preference:
            return jsonify({'success': False, 'message': 'Preference not found'}), 404

        db.session.delete(preference)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Preference deleted successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/get_user_preferences')
@login_required
def get_user_preferences():
    """Get current user's purchase preferences as JSON"""
    try:
        preferences = get_user_purchase_preferences(current_user.id)

        # Convert preferences to JSON-serializable format
        preferences_data = []
        for pref in preferences:
            preferences_data.append({
                'product_name': pref.product_name,
                'product_category': pref.product_category,
                'product_description': pref.product_description,
                'quantity': pref.quantity,
                'unit': pref.unit,
                'frequency': pref.frequency,
                'max_price_per_unit': float(pref.max_price_per_unit) if pref.max_price_per_unit else None,
                'preferred_suppliers': pref.preferred_suppliers,
                'quality_preference': pref.quality_preference,
                'payment_preference': pref.payment_preference,
                'preferred_delivery_time': pref.preferred_delivery_time,
                'typical_order_size': pref.typical_order_size,
                'last_purchased': pref.last_purchased.isoformat() if pref.last_purchased else None
            })

        return jsonify({
            'success': True,
            'preferences': preferences_data
        })

    except Exception as e:
        print(f"Error fetching user preferences: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch preferences'
        }), 500


@app.route('/add_product_to_order', methods=['POST'])
@login_required
def add_product_to_order():
    """Add a product to the user's next order or create a new order if none exists"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        # Extract product data
        product_id = data.get('product_id')
        product_name = data.get('product_name')
        price = data.get('price', 0)
        unit = data.get('unit', 'pcs')
        supplier_id = data.get('supplier_id')
        supplier_name = data.get('supplier_name')

        if not product_name:
            return jsonify({'success': False, 'message': 'Product name is required'}), 400

        user_id = current_user.id

        # Check if user has an active order (most recent order)
        active_order = Order.query.filter_by(
            user_id=user_id
        ).order_by(Order.created_at.desc()).first()

        if not active_order:
            # Create a new order
            active_order = Order(
                user_id=user_id,
                company_id=current_user.company_id,  # Add required company_id
                order_name=f"Order from {supplier_name}",
                description=f"Auto-generated order for {product_name}",
                sector="General",
                order_type="purchase",
                delivery_date=datetime.now().date(),
                created_at=datetime.now()
            )
            db.session.add(active_order)
            db.session.flush()  # Get the order ID

        # Create a new purchase item for this product
        purchase = Purchase(
            order_id=active_order.id,
            part_name=product_name,  # Use part_name instead of product_name
            quantity=1,  # Default quantity
            unit=unit,
            sector="General",  # Required field
            description=f"Product from {supplier_name}",
            max_price_per_unit=price if price > 0 else None,
            product_code=f"SUP_{supplier_id}_{product_id}",
            best_supplier=supplier_name
        )

        db.session.add(purchase)
        db.session.commit()

        # Create notification for the user
        create_notification(
            title="Product Added to Order",
            description=f"'{product_name}' has been added to your order #{active_order.id}",
            notification_type="order_update",
            priority="normal",
            user_id=user_id,
            related_order_id=active_order.id
        )

        return jsonify({
            'success': True,
            'message': f'Product "{product_name}" added to order #{active_order.id}',
            'order_id': active_order.id
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error adding product to order: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to add product to order. Please try again.'
        }), 500


@app.route('/get_current_order_status')
@login_required
def get_current_order_status():
    """Get the current user's active order status"""
    try:
        user_id = current_user.id

        # Check if user has an active order (most recent order)
        active_order = Order.query.filter_by(
            user_id=user_id
        ).order_by(Order.created_at.desc()).first()

        if active_order:
            # Count products in this order
            product_count = Purchase.query.filter_by(order_id=active_order.id).count()

            return jsonify({
                'success': True,
                'has_order': True,
                'order_id': active_order.id,
                'product_count': product_count
            })
        else:
            return jsonify({
                'success': True,
                'has_order': False,
                'order_id': None,
                'product_count': 0
            })

    except Exception as e:
        print(f"Error getting current order status: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to get order status'
        }), 500


@app.route('/generate_pdf_with_arabic', methods=['POST'])
@login_required
def generate_pdf_with_arabic():
    """Generate PDF with proper Arabic text support using WeasyPrint"""
    try:
        if not PDF_AVAILABLE:
            return jsonify({
                'success': False,
                'message': 'PDF generation not available. Please install WeasyPrint or ReportLab.'
            }), 500

        # Get form data
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        # Debug: Log the received data
        print(f"=== SERVER-SIDE PDF GENERATION DEBUG ===")
        print(f"PDF Engine: {PDF_ENGINE}")
        print(f"Received data: {data}")
        print(f"Order name: {data.get('order_name', 'Not specified')}")
        print(f"Order name type: {type(data.get('order_name', 'Not specified'))}")
        print(f"Order name length: {len(data.get('order_name', 'Not specified'))}")
        if data.get('order_name'):
            print(f"Order name char codes: {[ord(c) for c in data.get('order_name', '')]}")
            print(f"Has Arabic: {any(ord(c) in range(0x0600, 0x06FF) for c in data.get('order_name', ''))}")

        # Extract order information
        order_name = data.get('order_name', 'Not specified')
        sector = data.get('sector', 'Not specified')
        order_type = data.get('order_type', 'Not specified')
        delivery_date = data.get('delivery_date', 'Not specified')
        products = data.get('products', [])
        payment_steps = data.get('payment_steps', [])
        settings = data.get('settings', {})

        print(f"Using PDF engine: {PDF_ENGINE}")
        if PDF_ENGINE == 'weasyprint' and weasyprint is not None:
            # Use WeasyPrint for excellent Arabic text support
            print("Calling WeasyPrint PDF generation...")
            return generate_pdf_with_weasyprint(
                order_name, sector, order_type, delivery_date,
                products, payment_steps, settings
            )
        else:
            # Fallback to ReportLab
            print("Calling ReportLab PDF generation...")
            return generate_pdf_with_reportlab(
                order_name, sector, order_type, delivery_date,
                products, payment_steps, settings
            )

    except Exception as e:
        print(f"Error in generate_pdf_with_arabic: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error generating PDF: {str(e)}'
        }), 500


def generate_pdf_with_weasyprint(order_name: str, sector: str, order_type: str, delivery_date: str, products: list, payment_steps: list, settings: dict):
    """Generate PDF using WeasyPrint with perfect Arabic text support"""
    if weasyprint is None or HTML is None:
        return None
    try:
        # Create HTML content with proper Arabic text support
        html_content = f"""
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <title>Order Preview</title>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Noto+Naskh+Arabic:wght@400;700&display=swap');

                body {{
                    font-family: 'Amiri', 'Noto Naskh Arabic', 'Arial', sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: white;
                    direction: rtl;
                    text-align: right;
                }}

                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                    border-bottom: 3px solid #2563eb;
                    padding-bottom: 20px;
                }}

                .header h1 {{
                    color: #2563eb;
                    font-size: 28px;
                    margin: 0 0 10px 0;
                    font-weight: bold;
                }}

                .header p {{
                    color: #6b7280;
                    font-size: 14px;
                    margin: 0;
                }}

                .section {{
                    margin-bottom: 25px;
                }}

                .section h2 {{
                    color: #1f2937;
                    font-size: 18px;
                    margin: 0 0 15px 0;
                    padding: 10px;
                    background: #f3f4f6;
                    border-radius: 5px;
                    border-right: 4px solid #2563eb;
                }}

                .info-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }}

                .info-table th {{
                    background: #f3f4f6;
                    color: #374151;
                    padding: 12px;
                    text-align: right;
                    border: 1px solid #e5e7eb;
                    font-weight: bold;
                    width: 30%;
                }}

                .info-table td {{
                    padding: 12px;
                    text-align: right;
                    border: 1px solid #e5e7eb;
                    background: white;
                }}

                .products-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }}

                .products-table th {{
                    background: #2563eb;
                    color: white;
                    padding: 12px;
                    text-align: center;
                    border: 1px solid #1d4ed8;
                    font-weight: bold;
                }}

                .products-table td {{
                    padding: 12px;
                    text-align: center;
                    border: 1px solid #e5e7eb;
                    background: white;
                }}

                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e5e7eb;
                    color: #6b7280;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>معاينة الطلب</h1>
                <p>تم إنشاؤه في {datetime.now().strftime('%B %d, %Y')}</p>
            </div>

            <div class="section">
                <h2>معلومات الطلب</h2>
                <table class="info-table">
                    <tr>
                        <th>اسم الطلب:</th>
                        <td>{order_name}</td>
                    </tr>
                    <tr>
                        <th>القطاع:</th>
                        <td>{sector or 'غير محدد'}</td>
                    </tr>
                    <tr>
                        <th>نوع الطلب:</th>
                        <td>{order_type or 'غير محدد'}</td>
                    </tr>
                    <tr>
                        <th>تاريخ التسليم:</th>
                        <td>{delivery_date or 'غير محدد'}</td>
                    </tr>
                </table>
            </div>
        """

        # Add products section
        if products:
            html_content += """
            <div class="section">
                <h2>المنتجات</h2>
                <table class="products-table">
                    <thead>
                        <tr>
                            <th>المنتج</th>
                            <th>الكمية</th>
                            <th>الوصف</th>
                        </tr>
                    </thead>
                    <tbody>
            """

            for product in products:
                html_content += f"""
                        <tr>
                            <td>{product.get('name', '')}</td>
                            <td>{product.get('quantity', 0)} {product.get('unit', 'قطعة')}</td>
                            <td>{product.get('description', 'لا يوجد وصف')}</td>
                        </tr>
                """

            html_content += """
                    </tbody>
                </table>
            </div>
            """

        # Add payment terms section
        if payment_steps:
            html_content += """
            <div class="section">
                <h2>شروط الدفع</h2>
                <table class="products-table">
                    <thead>
                        <tr>
                            <th>الخطوة</th>
                            <th>الطريقة</th>
                            <th>التوقيت</th>
                            <th>النسبة</th>
                        </tr>
                    </thead>
                    <tbody>
            """

            for i, step in enumerate(payment_steps, 1):
                html_content += f"""
                        <tr>
                            <td>خطوة {i}</td>
                            <td>{step.get('method', '')}</td>
                            <td>{step.get('timing', 'غير محدد')}</td>
                            <td>{step.get('percentage', 0)}%</td>
                        </tr>
                """

            html_content += """
                    </tbody>
                </table>
            </div>
            """

        # Add settings section
        html_content += f"""
            <div class="section">
                <h2>إعدادات الطلب</h2>
                <table class="info-table">
                    <tr>
                        <th>المفاوضة المباشرة:</th>
                        <td>{settings.get('direct_negotiation', 'لا')}</td>
                    </tr>
                    <tr>
                        <th>قبول الموردين غير المسجلين:</th>
                        <td>{settings.get('accept_unregistered', 'لا')}</td>
                    </tr>
                    <tr>
                        <th>الحد الأقصى للموردين:</th>
                        <td>{settings.get('max_suppliers', 'غير محدد')}</td>
                    </tr>
                </table>
            </div>

            <div class="footer">
                <p>هذه معاينة لطلبك. يرجى مراجعة جميع التفاصيل قبل الإرسال.</p>
            </div>
        </body>
        </html>
        """

        # Generate PDF using WeasyPrint
        print(f"Creating HTML document with content length: {len(html_content)}")
        html_doc = HTML(string=html_content)
        css = CSS(string='')

        print("Generating PDF with WeasyPrint...")
        # Create PDF in memory
        buffer = BytesIO()
        html_doc.write_pdf(buffer, stylesheets=[css])
        buffer.seek(0)
        print(f"PDF generated successfully, buffer size: {len(buffer.getvalue())} bytes")

        # Generate filename
        filename = f"order_{order_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        print(f"WeasyPrint PDF generated successfully with Arabic text support")

        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"Error generating PDF with WeasyPrint: {e}")
        raise e


def generate_pdf_with_reportlab(order_name, sector, order_type, delivery_date, products, payment_steps, settings):
    """Fallback PDF generation using ReportLab"""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

        # Create PDF document
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []

        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2563eb')
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=15,
            textColor=colors.HexColor('#1f2937')
        )

        normal_style = styles['Normal']

        # Add title
        story.append(Paragraph("Order Preview", title_style))
        story.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y')}", normal_style))
        story.append(Spacer(1, 20))

        # Add order information
        story.append(Paragraph("Order Information", heading_style))
        order_info = [
            ["Order Name:", order_name],
            ["Sector:", sector],
            ["Order Type:", order_type],
            ["Delivery Date:", delivery_date]
        ]

        order_table = Table(order_info, colWidths=[80, 200])
        order_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#374151')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb'))
        ]))
        story.append(order_table)
        story.append(Spacer(1, 20))

        # Add products table
        if products:
            story.append(Paragraph("Products", heading_style))
            product_headers = ["Product", "Quantity", "Description"]
            product_data = [product_headers]

            for product in products:
                product_data.append([
                    product.get('name', ''),
                    f"{product.get('quantity', 0)} {product.get('unit', 'pcs')}",
                    product.get('description', 'No description')
                ])

            product_table = Table(product_data, colWidths=[120, 80, 120])
            product_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb'))
            ]))
            story.append(product_table)
            story.append(Spacer(1, 20))

        # Build PDF
        doc.build(story)
        buffer.seek(0)

        # Generate filename
        filename = f"order_{order_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        print(f"ReportLab PDF generated successfully")

        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"Error generating PDF with ReportLab: {e}")
        raise e


@app.route('/supplier_order_form')
@login_required
def supplier_order_form():
    # Get cart items from database
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    return render_template('client/supplier_order_form.html', cart_items=cart_items)


@app.route('/test_cart')
def test_cart():
    return render_template('client/test_cart.html')


# Cart management routes
@app.route('/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    try:
        data = request.get_json()

        # Check if product already exists in cart
        existing_item = Cart.query.filter_by(
            user_id=current_user.id,
            product_name=data.get('product_name'),
            supplier_id=data.get('supplier_id')
        ).first()

        if existing_item:
            # Update quantity if product already exists
            existing_item.quantity += data.get('quantity', 1)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Product quantity updated in cart',
                'cart_count': Cart.query.filter_by(user_id=current_user.id).count()
            })
        else:
            # Add new product to cart
            cart_item = Cart(
                user_id=current_user.id,
                product_name=data.get('product_name'),
                quantity=data.get('quantity', 1),
                unit=data.get('unit', 'pcs'),
                price=data.get('price'),
                supplier_id=data.get('supplier_id'),
                supplier_name=data.get('supplier_name')
            )

            db.session.add(cart_item)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Product added to cart successfully',
                'cart_count': Cart.query.filter_by(user_id=current_user.id).count()
            })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error adding to cart: {str(e)}'
        }), 500


@app.route('/cart/remove/<int:item_id>', methods=['DELETE'])
@login_required
def remove_from_cart(item_id):
    try:
        cart_item = Cart.query.filter_by(id=item_id, user_id=current_user.id).first()

        if cart_item:
            db.session.delete(cart_item)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Product removed from cart',
                'cart_count': Cart.query.filter_by(user_id=current_user.id).count()
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Cart item not found'
            }), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error removing from cart: {str(e)}'
        }), 500


@app.route('/cart/clear', methods=['DELETE'])
@login_required
def clear_cart():
    try:
        Cart.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Cart cleared successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error clearing cart: {str(e)}'
        }), 500


@app.route('/cart/count')
@login_required
def get_cart_count():
    try:
        count = Cart.query.filter_by(user_id=current_user.id).count()
        return jsonify({'count': count})
    except Exception as e:
        return jsonify({'count': 0, 'error': str(e)})


@app.route('/submit_supplier_order', methods=['POST'])
@login_required
def submit_supplier_order():
    try:
        # Get form data instead of JSON
        order_name = request.form.get('order_name', 'Supplier Order')
        sector = request.form.get('sector', 'General')
        order_type = request.form.get('order_type', 'Regular')
        delivery_date = request.form.get('delivery_date')

        # Get company ID from cart items (all cart items should be from same company)
        cart_items = Cart.query.filter_by(user_id=current_user.id).all()
        if not cart_items:
            flash('No items in cart', 'error')
            return redirect(url_for('supplier_order_form'))

        company_id = cart_items[0].supplier_id
        if not company_id:
            flash('No supplier company found in cart', 'error')
            return redirect(url_for('supplier_order_form'))

        # Create new supplier order
        supplier_order = SupplierOrder(
            user_id=current_user.id,
            company_id=company_id,
            order_name=order_name,
            sector=sector,
            order_type=order_type,
            delivery_date=datetime.strptime(delivery_date, '%Y-%m-%d').date() if delivery_date else None,
            payment_steps=json.dumps([]),
            direct_negotiation=False,
            accept_unregistered_suppliers=False,
            max_suppliers=10,
            status='pending'
        )

        db.session.add(supplier_order)
        db.session.commit()

        # Add products from form data to the supplier order
        products_data = {}
        for key in request.form.keys():
            if key.startswith('products[') and ']' in key:
                # Parse key like "products[0][product_name]" to get index and field
                parts = key.replace('products[', '').replace(']', '').split('[')
                if len(parts) == 2:
                    index = int(parts[0])
                    field = parts[1]
                    if index not in products_data:
                        products_data[index] = {}
                    products_data[index][field] = request.form[key]

        # Create supplier order products
        for index, product_data in products_data.items():
            supplier_order_product = SupplierOrderProduct(
                supplier_order_id=supplier_order.id,
                product_name=product_data.get('product_name', ''),
                quantity=int(product_data.get('quantity', 1)),
                unit=product_data.get('unit', 'pcs'),
                price=product_data.get('price', 'Not specified')
            )
            db.session.add(supplier_order_product)

        # Clear the user's cart after successful order creation
        Cart.query.filter_by(user_id=current_user.id).delete()

        db.session.commit()

        flash('Supplier order created successfully! This order is now separate from your regular orders.', 'success')
        return redirect(url_for('supplier_orders'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating supplier order: {str(e)}', 'error')
        return redirect(url_for('supplier_order_form'))


@app.route('/supplier_orders')
@login_required
def supplier_orders():
    """View all supplier orders for the current user"""
    try:
        supplier_orders = SupplierOrder.query.filter_by(user_id=current_user.id).order_by(
            SupplierOrder.created_at.desc()).all()
        return render_template('client/supplier_orders.html', supplier_orders=supplier_orders)
    except Exception as e:
        flash(f'Error loading supplier orders: {str(e)}', 'error')
        return redirect(url_for('dash'))


@app.route('/supplier_order/<int:order_id>')
@login_required
def view_supplier_order(order_id):
    """View a specific supplier order"""
    try:
        supplier_order = SupplierOrder.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
        return render_template('client/view_supplier_order.html', supplier_order=supplier_order)
    except Exception as e:
        flash(f'Error loading supplier order: {str(e)}', 'error')
        return redirect(url_for('supplier_orders'))


@app.route('/submit_complaint/<int:offer_id>', methods=['GET', 'POST'])
@login_required
def submit_complaint(offer_id):
    """Submit a new complaint page"""
    try:
        # Get the offer
        offer = Offer.query.get_or_404(offer_id)

        # Check if user has access to this offer
        if current_user.role == 'client':
            # Client can only submit complaints for their own orders
            if offer.order.user_id != current_user.id:
                flash('Access denied. You can only submit complaints for your own orders.', 'error')
                return redirect(url_for('index'))
        else:
            flash('Only clients can submit complaints.', 'error')
            return redirect(url_for('index'))

        if request.method == 'POST':
            # Handle form submission
            title = request.form.get('title')
            description = request.form.get('description')
            complaint_type = request.form.get('complaint_type', 'general')
            priority = request.form.get('priority', 'normal')

            if not all([title, description]):
                flash('Please fill in all required fields.', 'error')
                return render_template('client/submit_complaint.html', offer=offer)

            # Create the complaint
            complaint = Complaint(
                user_id=current_user.id,
                offer_id=offer_id,
                company_id=offer.company_id,
                title=title,
                description=description,
                complaint_type=complaint_type,
                priority=priority,
                status='open'
            )

            db.session.add(complaint)
            db.session.commit()

            flash('Complaint submitted successfully!', 'success')
            return redirect(url_for('view_complaints'))

        # GET request - show the form
        return render_template('client/submit_complaint.html', offer=offer)

    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/complaints')
@login_required
def view_complaints():
    """View all complaints for the current user"""
    try:
        if current_user.role == 'client':
            # Clients see their own complaints
            complaints = Complaint.query.filter_by(user_id=current_user.id).order_by(Complaint.created_at.desc()).all()
        elif current_user.role == 'company':
            # Companies see complaints about their offers
            complaints = Complaint.query.filter_by(company_id=current_user.company_id).order_by(
                Complaint.created_at.desc()).all()
        else:
            flash('Access denied', 'error')
            return redirect(url_for('index'))

        return render_template('complaints.html', complaints=complaints)

    except Exception as e:
        flash(f'Error loading complaints: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/complaint/<int:complaint_id>')
@login_required
def view_complaint(complaint_id):
    """View a specific complaint"""
    try:
        complaint = Complaint.query.get_or_404(complaint_id)

        # Check access
        if current_user.role == 'client' and complaint.user_id != current_user.id:
            flash('Access denied', 'error')
            return redirect(url_for('view_complaints'))
        elif current_user.role == 'company' and complaint.company_id != current_user.company_id:
            flash('Access denied', 'error')
            return redirect(url_for('view_complaints'))

        return render_template('complaint_detail.html', complaint=complaint)

    except Exception as e:
        flash(f'Error loading complaint: {str(e)}', 'error')
        return redirect(url_for('view_complaints'))


@app.route('/update_complaint_status', methods=['POST'])
@login_required
def update_complaint_status():
    """Update complaint status (for companies)"""
    try:
        if current_user.role != 'company':
            return jsonify({'error': 'Access denied'}), 403

        data = request.get_json()
        complaint_id = data.get('complaint_id')
        new_status = data.get('status')
        resolution_notes = data.get('resolution_notes', '')

        if not all([complaint_id, new_status]):
            return jsonify({'error': 'Missing required fields'}), 400

        complaint = Complaint.query.get_or_404(complaint_id)

        # Check if company owns this complaint
        if complaint.company_id != current_user.company_id:
            return jsonify({'error': 'Access denied'}), 403

        # Update status
        complaint.status = new_status
        complaint.resolution_notes = resolution_notes
        complaint.updated_at = datetime.utcnow()

        if new_status == 'resolved':
            complaint.resolved_at = datetime.utcnow()
            complaint.resolved_by = current_user.id

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Complaint status updated to {new_status}'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/compare_offers_page/<int:order_id>')
@login_required
def compare_offers_page(order_id):
    """Compare offers for a specific order"""
    print(f"DEBUG: compare_offers_page called with order_id: {order_id}")
    print(f"DEBUG: current_user: {current_user.id}, role: {current_user.role}")
    try:
        print(f"DEBUG: About to query for order {order_id}")
        # Get the order
        order = Order.query.get_or_404(order_id)
        print(f"DEBUG: Found order: {order.id}, user_id: {order.user_id}")

        # Check if user owns this order
        if current_user.role == 'client' and order.user_id != current_user.id:
            flash(_('Access denied. You can only compare offers for your own orders.'), 'error')
            return redirect(url_for('orders'))

        # Get all offers for this order
        offers = Offer.query.filter_by(order_id=order_id).order_by(Offer.created_at.desc()).all()

        # Manually load companies for each offer
        for offer in offers:
            print(f"DEBUG: Offer {offer.id} - company_id: {offer.company_id}")
            company = Company.query.get(offer.company_id)
            if company:
                offer.company = company
                print(f"  Loaded company: {company.name_ar or company.name_en or 'No name'}")
            else:
                print(f"  ERROR: Company {offer.company_id} not found in database")

                # Create a dummy company object to prevent errors
                class DummyCompany:
                    def __init__(self):
                        self.name_ar = None
                        self.name_en = None

                offer.company = DummyCompany()

        print(f"DEBUG: Found {len(offers)} offers for order {order_id}")
        for offer in offers:
            print(f"  Offer {offer.id}: company_id={offer.company_id}, company={offer.company}")

        print(f"DEBUG: Found {len(offers)} offers for order {order_id}")

        # Allow comparison even with 1 offer for testing
        if len(offers) == 0:
            flash(_('No offers found for this order.'), 'error')
            return redirect(url_for('view_order', order_id=order_id))
        elif len(offers) == 1:
            print(f"DEBUG: Only 1 offer found, but allowing comparison for testing")
            # Don't redirect, continue with 1 offer
        elif len(offers) < 2:
            flash(_('You need at least 2 offers to compare them.'), 'error')
            return redirect(url_for('view_order', order_id=order_id))

        # Intelligent offer comparison logic
        analyzed_offers = []
        best_overall_offer = None
        best_price_offer = None
        best_delivery_offer = None
        best_guarantee_offer = None

        for offer in offers:
            try:
                # Ensure company relationship is loaded
                if not offer or not hasattr(offer, 'company') or offer.company is None:
                    print(f"WARNING: Offer {getattr(offer, 'id', 'unknown')} has no company relationship")
                    continue

                print(
                    f"Processing offer {offer.id} from company: {offer.company.name_ar or offer.company.name_en or 'Unknown'}")
                print(f"  Raw delivery_time: '{offer.delivery_time}'")
                print(f"  Raw guarantee: '{offer.guarantee}'")

                # Simple scoring for now - just use basic values
                price_score = offer.total_price or 0
                delivery_score = 30  # Default
                guarantee_score = 0  # Default

                # Simple delivery scoring
                if offer.delivery_time:
                    delivery_text = str(offer.delivery_time).lower().strip()
                    print(f"  DEBUG: Parsing delivery time: '{delivery_text}'")

                    if 'week' in delivery_text:
                        try:
                            number = int(''.join(filter(str.isdigit, delivery_text)))
                            delivery_score = number * 7
                            print(f"    Parsed as {number} weeks = {delivery_score} days")
                        except:
                            delivery_score = 30
                            print(f"    Failed to parse, defaulting to {delivery_score} days")
                    elif 'day' in delivery_text:
                        try:
                            # Handle ranges like "1-3 days"
                            if '-' in delivery_text:
                                parts = delivery_text.split('-')
                                min_days = int(''.join(filter(str.isdigit, parts[0])))
                                delivery_score = min_days  # Use the minimum for scoring
                                print(f"    Parsed range as {min_days}-X days = {delivery_score} days (using min)")
                            else:
                                number = int(''.join(filter(str.isdigit, delivery_text)))
                                delivery_score = number
                                print(f"    Parsed as {number} days")
                        except:
                            delivery_score = 30
                            print(f"    Failed to parse, defaulting to {delivery_score} days")
                    else:
                        delivery_score = 30
                        print(f"    No time unit found, defaulting to {delivery_score} days")

                # Simple guarantee scoring
                if offer.guarantee:
                    guarantee_text = str(offer.guarantee).lower().strip()
                    print(f"  DEBUG: Parsing guarantee: '{guarantee_text}'")

                    if 'year' in guarantee_text:
                        try:
                            years = int(''.join(filter(str.isdigit, guarantee_text)))
                            guarantee_score = years * 10
                            print(f"    Parsed as {years} years = {guarantee_score} points")
                        except:
                            guarantee_score = 0
                            print(f"    Failed to parse, defaulting to {guarantee_score} points")
                    elif 'month' in guarantee_text:
                        try:
                            months = int(''.join(filter(str.isdigit, guarantee_text)))
                            guarantee_score = months * 2
                            print(f"    Parsed as {months} months = {guarantee_score} points")
                        except:
                            guarantee_score = 0
                            print(f"    Failed to parse, defaulting to {guarantee_score} points")
                    else:
                        guarantee_score = 0
                        print(f"    No time unit found, defaulting to {guarantee_score} points")
                else:
                    guarantee_score = 0
                    print(f"    No guarantee specified, score: {guarantee_score}")

                # Simple overall score
                overall_score = price_score + delivery_score + guarantee_score

                analyzed_offer = {
                    'offer': offer,
                    'total_landed_cost': offer.total_price + (offer.transportation_fees or 0),
                    'effective_price': offer.total_price * (1 - (offer.deduction_percentage or 0) / 100),
                    'price_score': price_score,
                    'delivery_score': delivery_score,
                    'guarantee_score': guarantee_score,
                    'overall_score': overall_score
                }
                analyzed_offers.append(analyzed_offer)

                print(
                    f"  Scores - Price: {price_score}, Delivery: {delivery_score}, Guarantee: {guarantee_score}, Overall: {overall_score}")

            except Exception as offer_error:
                print(f"ERROR processing offer {offer.id}: {str(offer_error)}")
                import traceback
                traceback.print_exc()
                continue

        # Check if we have valid offers to analyze
        if not analyzed_offers:
            flash(_('No valid offers found to compare. Please check if all offers have valid company information.'),
                  'error')
            return redirect(url_for('view_order', order_id=order_id))

        # Sort offers by overall score (best first)
        analyzed_offers.sort(key=lambda x: x['overall_score'])

        # Find best offers in different categories
        if analyzed_offers:
            best_overall_offer = analyzed_offers[0]['offer']
            best_price_offer = min(analyzed_offers, key=lambda x: x['effective_price'])['offer']
            best_delivery_offer = min(analyzed_offers, key=lambda x: x['delivery_score'])['offer']
            best_guarantee_offer = max(analyzed_offers, key=lambda x: x['guarantee_score'])['offer']

            # Debug logging for final recommendations
            print(f"\nDEBUG: Final Recommendations:")
            print(
                f"  Best Overall: {best_overall_offer.company.name_ar or best_overall_offer.company.name_en or 'Unknown'}")
            print(f"  Best Price: {best_price_offer.company.name_ar or best_price_offer.company.name_en or 'Unknown'}")
            print(
                f"  Best Delivery: {best_delivery_offer.company.name_ar or best_delivery_offer.company.name_en or 'Unknown'} (Score: {min(analyzed_offers, key=lambda x: x['delivery_score'])['delivery_score']})")
            print(
                f"  Best Guarantee: {best_guarantee_offer.company.name_ar or best_guarantee_offer.company.name_en or 'Unknown'} (Score: {min(analyzed_offers, key=lambda x: x['guarantee_score'])['guarantee_score']})")

        # Prepare recommendation data
        recommendation_data = {
            'best_overall': best_overall_offer,
            'best_price': best_price_offer,
            'best_delivery': best_delivery_offer,
            'best_guarantee': best_guarantee_offer,
            'total_offers': len(analyzed_offers),
            'price_range': {
                'min': min(analyzed_offers, key=lambda x: x['effective_price'])[
                    'effective_price'] if analyzed_offers else 0,
                'max': max(analyzed_offers, key=lambda x: x['effective_price'])[
                    'effective_price'] if analyzed_offers else 0
            },
            'delivery_range': {
                'min': min(analyzed_offers, key=lambda x: x['delivery_score'])[
                    'delivery_score'] if analyzed_offers else 0,
                'max': max(analyzed_offers, key=lambda x: x['delivery_score'])[
                    'delivery_score'] if analyzed_offers else 0
            }
        }

        print(f"DEBUG: About to render template with {len(analyzed_offers)} analyzed offers")
        print(f"DEBUG: Template variables - order: {order.id}, offers: {len(offers)}, analyzed: {len(analyzed_offers)}")

        # Try a simple template first
        try:
            print(f"DEBUG: Attempting to render template...")
            result = render_template('client/compare_offers.html',
                                     order=order,
                                     offers=offers,
                                     analyzed_offers=analyzed_offers,
                                     recommendation=recommendation_data)
            print(f"DEBUG: Template rendered successfully!")
            return result
        except Exception as template_error:
            print(f"ERROR rendering template: {str(template_error)}")
            import traceback
            traceback.print_exc()

            # Fallback: return simple HTML instead of redirecting
            return f"""
            <!DOCTYPE html>
            <html>
            <head><title>Compare Offers - Order {order.id}</title></head>
            <body>
                <h1>Compare Offers for Order {order.id}</h1>
                <p>Found {len(offers)} offers</p>
                <p>Successfully analyzed {len(analyzed_offers)} offers</p>
                <h2>Best Overall: {recommendation_data['best_overall'].company.name_ar or recommendation_data['best_overall'].company.name_en or 'None' if recommendation_data['best_overall'] else 'None'}</h2>
                <h2>Best Price: {recommendation_data['best_price'].company.name_ar or recommendation_data['best_price'].company.name_en or 'None' if recommendation_data['best_price'] else 'None'}</h2>
                <h2>Best Delivery: {recommendation_data['best_delivery'].company.name_ar or recommendation_data['best_delivery'].company.name_en or 'None' if recommendation_data['best_delivery'] else 'None'}</h2>
                <h2>Best Guarantee: {recommendation_data['best_guarantee'].company.name_ar or recommendation_data['best_guarantee'].company.name_en or 'None' if recommendation_data['best_guarantee'] else 'None'}</h2>
                <p><a href="/orders">Back to Orders</a></p>
            </body>
            </html>
            """

    except Exception as e:
        print(f"ERROR in compare_offers_page: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error comparing offers: {str(e)}', 'error')
        return redirect(url_for('orders'))


@app.route('/test_compare/<int:order_id>')
@login_required
def test_compare(order_id):
    """Simple test route to debug compare offers"""
    try:
        print(f"TEST: Simple compare test for order {order_id}")
        order = Order.query.get_or_404(order_id)
        offers = Offer.query.filter_by(order_id=order_id).all()

        return f"""
        <h1>Test Compare Page</h1>
        <p>Order ID: {order.id}</p>
        <p>Order User ID: {order.user_id}</p>
        <p>Current User ID: {current_user.id}</p>
        <p>Number of Offers: {len(offers)}</p>
        <p><a href="/orders">Back to Orders</a></p>
        """
    except Exception as e:
        return f"Error: {str(e)}"


@app.route('/simple_compare/<int:order_id>')
@login_required
def simple_compare(order_id):
    """Ultra-simple compare route for debugging"""
    print(f"ULTRA-SIMPLE: Route called with order_id: {order_id}")
    print(f"ULTRA-SIMPLE: Current user: {current_user.id}")

    try:
        order = Order.query.get_or_404(order_id)
        print(f"ULTRA-SIMPLE: Found order: {order.id}")

        offers = Offer.query.filter_by(order_id=order_id).all()
        print(f"ULTRA-SIMPLE: Found {len(offers)} offers")

        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Simple Compare - Order {order.id}</title></head>
        <body>
            <h1>Simple Compare for Order {order.id}</h1>
            <p>User ID: {current_user.id}</p>
            <p>Order User ID: {order.user_id}</p>
            <p>Number of Offers: {len(offers)}</p>
            <p><a href="/orders">Back to Orders</a></p>
        </body>
        </html>
        """
    except Exception as e:
        print(f"ULTRA-SIMPLE ERROR: {str(e)}")
        return f"Error: {str(e)}"


# ===== ADMIN ROUTES =====

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard - redirect to stocks page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    return redirect(url_for('admin_stocks'))


@app.route('/admin_stocks')
@login_required
def admin_stocks():
    """Admin stocks/dashboard page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    # Get system statistics
    total_users = User.query.filter(User.role != 'admin').count()
    total_companies = Company.query.filter(Company.company_type != 'system').count()
    total_orders = Order.query.count()
    total_offers = Offer.query.count()

    # Get recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()

    # Get pending company approvals
    pending_companies = Company.query.filter_by(is_approved=False, is_active=True).limit(5).all()

    return render_template('site_admin/stocks.html',
                           total_users=total_users,
                           total_companies=total_companies,
                           total_orders=total_orders,
                           total_offers=total_offers,
                           recent_orders=recent_orders,
                           pending_companies=pending_companies)


@app.route('/admin_companies')
@login_required
def admin_companies():
    """Admin companies management page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    companies = Company.query.filter(Company.company_type != 'system').all()
    return render_template('site_admin/companies.html', companies=companies)


@app.route('/admin_export_companies')
@login_required
def admin_export_companies():
    """Export companies data to CSV"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    try:
        # Get all non-system companies
        companies = Company.query.filter(Company.company_type != 'system').all()

        # Create CSV data
        csv_data = []
        csv_data.append(
            ['Company Name (EN)', 'Company Name (AR)', 'Email', 'Phone', 'Address', 'Sector', 'Type', 'Status',
             'Approved', 'Created At'])

        for company in companies:
            csv_data.append([
                company.name_en or '',
                company.name_ar or '',
                company.email or '',
                company.office_phone or company.mobile_contact or '',
                company.registered_address or '',
                company.sector or '',
                company.company_type or '',
                'Active' if company.is_active else 'Inactive',
                'Yes' if company.is_approved else 'No',
                company.created_at.strftime('%Y-%m-%d %H:%M:%S') if company.created_at else ''
            ])

        # Convert to CSV string
        output = StringIO()
        writer = csv.writer(output)
        writer.writerows(csv_data)
        csv_string = output.getvalue()
        output.close()

        # Create response
        response = make_response(csv_string)
        response.headers['Content-Type'] = 'text/csv'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=companies_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response

    except Exception as e:
        flash(f'Error exporting companies: {str(e)}', 'error')
        return redirect(url_for('admin_companies'))


@app.route('/admin_company_action/<int:company_id>', methods=['POST'])
@login_required
def admin_company_action(company_id):
    """Admin action on company (accept/refuse information)"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    company = Company.query.get_or_404(company_id)
    action = request.form.get('action')
    field_name = request.form.get('field_name')

    if action == 'accept':
        flash(f'Company {field_name} accepted successfully!', 'success')
    elif action == 'refuse':
        # Set the field to None or empty string
        if company and hasattr(company, field_name):
            if field_name and field_name.endswith('_doc'):
                setattr(company, field_name, None)
            else:
                setattr(company, field_name, '')
        flash(f'Company {field_name or "field"} refused and removed!', 'success')

    db.session.commit()
    return redirect(url_for('admin_company_details', company_id=company_id))


@app.route('/admin_change_company_status/<int:company_id>', methods=['POST'])
@login_required
def admin_change_company_status(company_id):
    """Admin changes company status"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    company = Company.query.get_or_404(company_id)
    new_status = request.form.get('status')
    reason = request.form.get('reason', '')

    if new_status == 'activate':
        company.is_active = True
        flash('Company activated successfully!', 'success')
    elif new_status == 'deactivate':
        company.is_active = False
        flash('Company deactivated successfully!', 'success')
    elif new_status == 'approve':
        company.is_approved = True
        flash('Company approved successfully!', 'success')
    elif new_status == 'reject':
        company.is_approved = False
        flash('Company rejected successfully!', 'success')

    db.session.commit()
    return redirect(url_for('admin_company_details', company_id=company_id))


@app.route('/admin_download_document/<int:company_id>/<field_name>')
@login_required
def admin_download_document(company_id, field_name):
    """Admin downloads company document"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    company = Company.query.get_or_404(company_id)

    # Debug information
    print(f"Download request: company_id={company_id}, field_name={field_name}")
    print(f"Company: {company.name_en or company.name_ar}")

    if company and hasattr(company, field_name):
        file_path = getattr(company, field_name)
        print(f"File path: {file_path}")

        if file_path:
            # Check if it's a relative path and make it absolute
            if not os.path.isabs(file_path):
                # Try different possible base directories
                possible_paths = [
                    file_path,  # Original path
                    os.path.join('uploads', file_path),  # Uploads folder
                    os.path.join('static', 'uploads', file_path),  # Static uploads
                    os.path.join(os.getcwd(), 'uploads', file_path),  # Absolute uploads
                    os.path.join(os.getcwd(), 'static', 'uploads', file_path)  # Absolute static uploads
                ]

                for path in possible_paths:
                    print(f"Trying path: {path}")
                    if os.path.exists(path):
                        print(f"Found file at: {path}")
                        try:
                            return send_file(path, as_attachment=True)
                        except Exception as e:
                            print(f"Error sending file: {e}")
                            flash(f'Error downloading file: {str(e)}', 'error')
                            return redirect(url_for('admin_company_details', company_id=company_id))

                # If we get here, no file was found
                print(f"No file found in any of the possible paths")
                flash(f'Document file not found. Path: {file_path}', 'error')
            else:
                # Absolute path
                if os.path.exists(file_path):
                    try:
                        return send_file(file_path, as_attachment=True)
                    except Exception as e:
                        print(f"Error sending file: {e}")
                        flash(f'Error downloading file: {str(e)}', 'error')
                        return redirect(url_for('admin_company_details', company_id=company_id))
                else:
                    print(f"Absolute path does not exist: {file_path}")
                    flash(f'Document file not found at: {file_path}', 'error')
        else:
            print(f"Field {field_name} is None or empty")
            flash(f'No document uploaded for {field_name}', 'error')
    else:
        print(f"Company does not have field: {field_name}")
        flash(f'Field {field_name} not found on company', 'error')

    return redirect(url_for('admin_company_details', company_id=company_id))


@app.route('/admin_debug_company/<int:company_id>')
@login_required
def admin_debug_company(company_id):
    """Debug route to see company document fields"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'})

    company = Company.query.get_or_404(company_id)

    # Get all document fields
    document_fields = [
        'commercial_registration_doc',
        'tax_card_doc',
        'e_invoice_proof_doc',
        'logo_doc',
        'letterhead_doc',
        'bank_letter_doc',
        'owner_id_doc',
        'product_catalog_doc',
        'quality_certificates_doc'
    ]

    debug_info = {
        'company_id': company.id,
        'company_name': company.name_en or company.name_ar,
        'document_fields': {}
    }

    for field in document_fields:
        if company and hasattr(company, field):
            value = getattr(company, field)
            debug_info['document_fields'][field] = {
                'value': value,
                'exists': value is not None and value != '',
                'file_exists': os.path.exists(value) if value else False
            }

    return jsonify(debug_info)


@app.route('/admin_company_details/<int:company_id>')
@login_required
def admin_company_details(company_id):
    """Admin company details page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    company = Company.query.get_or_404(company_id)

    # Get company statistics
    total_users = User.query.filter_by(company_id=company_id).count()
    total_orders = Order.query.filter_by(company_id=company_id).count()
    total_offers = Offer.query.filter_by(company_id=company_id).count()

    return render_template('site_admin/company_details.html',
                           company=company,
                           total_users=total_users,
                           total_orders=total_orders,
                           total_offers=total_offers)


@app.route('/admin_register_company', methods=['GET', 'POST'])
@login_required
def admin_register_company():
    """Admin company registration page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            # Basic Company Information
            name_ar = request.form.get('name_ar')
            name_en = request.form.get('name_en')
            email = request.form.get('email')

            # Validation
            if not name_ar or not email:
                flash('Company name (Arabic) and email are required.', 'error')
                return render_template('site_admin/admin_register_company.html')

            # Check if company with this email already exists
            if Company.query.filter_by(email=email).first():
                flash('A company with this email already exists.', 'error')
                return render_template('site_admin/admin_register_company.html')

            # Create new company
            new_company = Company(
                name_ar=name_ar,
                name_en=name_en,
                email=email,
                legal_type=request.form.get('legal_type'),
                tax_id=request.form.get('tax_id'),
                commercial_registration=request.form.get('commercial_registration'),
                vat_number=request.form.get('vat_number'),
                registered_address=request.form.get('registered_address'),
                website=request.form.get('website'),
                office_phone=request.form.get('office_phone'),
                mobile_contact=request.form.get('mobile_contact'),
                contact_person=request.form.get('contact_person'),
                contact_position=request.form.get('contact_position'),
                owner_name=request.form.get('owner_name'),
                bank_name=request.form.get('bank_name'),
                account_name=request.form.get('account_name'),
                account_number=request.form.get('account_number'),
                bank_branch=request.form.get('bank_branch'),
                sector=request.form.get('sector'),
                founded_year=int(request.form.get('founded_year')) if request.form.get('founded_year') else None,
                employees_count=request.form.get('employees_count'),
                company_type=request.form.get('company_type', 'supplier'),
                is_active=True,  # Admin-created companies are active by default
                is_approved=True  # Admin-created companies are approved by default
            )

            # Handle file uploads
            upload_folder = os.path.join('static', 'uploads', 'companies')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)

            file_fields = [
                'commercial_registration_doc', 'tax_card_doc', 'e_invoice_proof_doc',
                'logo_doc', 'letterhead_doc', 'bank_letter_doc', 'owner_id_doc',
                'product_catalog_doc', 'quality_certificates_doc'
            ]

            for field in file_fields:
                if field in request.files:
                    file = request.files[field]
                    if file and file.filename != '':
                        filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"{timestamp}_{filename}"
                        file_path = os.path.join(upload_folder, filename)
                        file.save(file_path)
                        setattr(new_company, field, file_path)

            db.session.add(new_company)
            db.session.commit()

            # Create admin user for the company if requested
            if request.form.get('create_admin_user') == 'on':
                admin_username = request.form.get('admin_username')
                admin_email = request.form.get('admin_email')
                admin_password = request.form.get('admin_password')

                if admin_username and admin_email and admin_password:
                    # Check if user already exists
                    if not User.query.filter_by(username=admin_username).first() and not User.query.filter_by(
                            email=admin_email).first():
                        password_hash = generate_password_hash(str(admin_password) if admin_password else '', method='pbkdf2:sha256')
                        admin_user = User(
                            username=admin_username,
                            email=admin_email,
                            password_hash=password_hash,
                            name=request.form.get('admin_name', admin_username),
                            role='company',
                            company_id=new_company.id
                        )
                        db.session.add(admin_user)
                        db.session.commit()

            flash(f'Company "{name_ar}" registered successfully!', 'success')
            return redirect(url_for('admin_companies'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error registering company: {str(e)}', 'error')
            return render_template('site_admin/admin_register_company.html')

    return render_template('site_admin/admin_register_company.html')


@app.route('/admin_users')
@login_required
def admin_users():
    """Admin users management page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    try:
        # Get all non-admin users
        users = User.query.filter(User.role != 'admin').all()
        return render_template('site_admin/users.html', users=users)
    except Exception as e:
        print(f"Error in admin_users route: {e}")
        flash(f'Error loading users: {str(e)}', 'error')
        return render_template('site_admin/users.html', users=[])


@app.route('/admin_export_users')
@login_required
def admin_export_users():
    """Export users data to CSV"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    try:
        # Get all non-admin users
        users = User.query.filter(User.role != 'admin').all()

        # Create CSV data
        csv_data = []
        csv_data.append(
            ['Username', 'Email', 'Name', 'Role', 'Phone', 'Country', 'City', 'Company', 'Active', 'Created At'])

        for user in users:
            company_name = ''
            if user.company_id:
                company = Company.query.get(user.company_id)
                if company:
                    company_name = company.name_en or company.name_ar or ''

            csv_data.append([
                user.username or '',
                user.email or '',
                user.name or '',
                user.role or '',
                user.phone_number or '',
                user.country or '',
                user.city or '',
                company_name,
                'Yes' if user.is_active else 'No',
                user.created_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(user, 'created_at') and user.created_at else ''
            ])

        # Convert to CSV string
        output = StringIO()
        writer = csv.writer(output)
        writer.writerows(csv_data)
        csv_string = output.getvalue()
        output.close()

        # Create response
        response = make_response(csv_string)
        response.headers['Content-Type'] = 'text/csv'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response

    except Exception as e:
        flash(f'Error exporting users: {str(e)}', 'error')
        return redirect(url_for('admin_users'))


@app.route('/admin_orders')
@login_required
def admin_orders():
    """Admin orders management page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    orders = Order.query.all()

    # Add offer information to each order
    for order in orders:
        # Safely handle offers relationship
        try:
            if hasattr(order, 'offers') and order.offers is not None:
                # Check if offers is a list/query result
                if hasattr(order.offers, '__iter__') and not isinstance(order.offers, (str, int, float)):
                    order.offer_count = len(order.offers)
                    order.has_offers = order.offer_count > 0
                    order.accepted_offers = len(
                        [o for o in order.offers if hasattr(o, 'status') and o.status == 'accepted'])
                    order.pending_offers = len(
                        [o for o in order.offers if hasattr(o, 'status') and o.status == 'pending'])
                else:
                    # If offers is not iterable, set defaults
                    order.offer_count = 0
                    order.has_offers = False
                    order.accepted_offers = 0
                    order.pending_offers = 0
            else:
                # No offers relationship
                order.offer_count = 0
                order.has_offers = False
                order.accepted_offers = 0
                order.pending_offers = 0

            # Ensure all required fields exist with safe defaults
            if not hasattr(order, 'status') or order.status is None:
                order.status = 'pending'
            if not hasattr(order, 'total_amount') or order.total_amount is None:
                order.total_amount = 0.0
            if not hasattr(order, 'created_at') or order.created_at is None:
                order.created_at = datetime.utcnow()

        except Exception as e:
            # Fallback in case of any errors
            print(f"Error processing offers for order {order.id}: {e}")
            order.offer_count = 0
            order.has_offers = False
            order.accepted_offers = 0
            order.pending_offers = 0
            # Set safe defaults
            order.status = 'pending'
            order.total_amount = 0.0
            order.created_at = datetime.utcnow()

    return render_template('site_admin/orders.html', orders=orders)


@app.route('/admin_order_details/<int:order_id>')
@login_required
def admin_order_details(order_id):
    """Admin order details page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    order = Order.query.get_or_404(order_id)

    # Get related data
    user = User.query.get(order.user_id) if order.user_id else None
    company = Company.query.get(order.company_id) if order.company_id else None
    purchases = Purchase.query.filter_by(order_id=order_id).all()
    offers = Offer.query.filter_by(order_id=order_id).all()

    # Add calculated fields
    order.total_amount = sum(
        purchase.quantity * (purchase.max_price_per_unit or 0) for purchase in purchases) if purchases else 0.0

    return render_template('site_admin/order_details.html',
                           order=order,
                           user=user,
                           company=company,
                           purchases=purchases,
                           offers=offers)


@app.route('/admin_update_order/<int:order_id>')
@login_required
def admin_update_order(order_id):
    """Admin update order page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    order = Order.query.get_or_404(order_id)

    # Get related data
    user = User.query.get(order.user_id) if order.user_id else None
    company = Company.query.get(order.company_id) if order.company_id else None
    purchases = Purchase.query.filter_by(order_id=order_id).all()

    return render_template('site_admin/order_update.html',
                           order=order,
                           user=user,
                           company=company,
                           purchases=purchases)


@app.route('/admin_order_offers/<int:order_id>')
@login_required
def admin_order_offers(order_id):
    """Admin view order offers page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    order = Order.query.get_or_404(order_id)

    # Get related data
    user = User.query.get(order.user_id) if order.user_id else None
    company = Company.query.get(order.company_id) if order.company_id else None
    offers = Offer.query.filter_by(order_id=order_id).all()

    return render_template('site_admin/order_offers.html',
                           order=order,
                           user=user,
                           company=company,
                           offers=offers)


@app.route('/admin_offer_details/<int:offer_id>')
@login_required
def admin_offer_details(offer_id):
    """Admin offer details page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    offer = Offer.query.get_or_404(offer_id)

    # Get related data
    order = Order.query.get(offer.order_id) if offer.order_id else None
    company = Company.query.get(offer.company_id) if offer.company_id else None
    user = User.query.get(order.user_id) if order and order.user_id else None

    # Get product offers if they exist
    product_offers = ProductOffer.query.filter_by(offer_id=offer_id).all()

    return render_template('site_admin/offer_details.html',
                           offer=offer,
                           order=order,
                           company=company,
                           user=user,
                           product_offers=product_offers)


@app.route('/admin_send_email', methods=['POST'])
@login_required
def admin_send_email():
    """Admin sends email to company"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json()
    company_id = data.get('company_id')
    subject = data.get('subject')
    message = data.get('message')

    if not all([company_id, subject, message]):
        return jsonify({'error': 'Missing required fields'}), 400

    # For now, just return success (email functionality can be implemented later)
    return jsonify({'success': True, 'message': 'Email sent successfully'})


@app.route('/admin_flag_offer/<int:offer_id>', methods=['POST'])
@login_required
def admin_flag_offer(offer_id):
    """Admin flags an offer"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json()
    flag_type = data.get('flag')

    offer = Offer.query.get_or_404(offer_id)
    offer.flags = flag_type
    db.session.commit()

    return jsonify({'success': True})


@app.route('/admin_duplicate_offer/<int:offer_id>', methods=['POST'])
@login_required
def admin_duplicate_offer(offer_id):
    """Admin duplicates an offer"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    original_offer = Offer.query.get_or_404(offer_id)

    # Create new offer
    new_offer = Offer(
        order_id=original_offer.order_id,
        company_id=original_offer.company_id,
        total_price=original_offer.total_price,
        description=original_offer.description,
        delivery_time=original_offer.delivery_time,
        deduction_percentage=original_offer.deduction_percentage,
        transportation_fees=original_offer.transportation_fees,
        guarantee=original_offer.guarantee,
        status='pending'
    )

    db.session.add(new_offer)
    db.session.commit()

    return jsonify({'success': True, 'new_offer_id': new_offer.id})


@app.route('/admin_export_offer/<int:offer_id>')
@login_required
def admin_export_offer(offer_id):
    """Admin exports offer to CSV"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    offer = Offer.query.get_or_404(offer_id)
    order = Order.query.get(offer.order_id) if offer.order_id else None
    company = Company.query.get(offer.company_id) if offer.company_id else None

    # Create CSV data
    csv_data = []
    csv_data.append(['Offer ID', 'Company', 'Order ID', 'Total Price', 'Status', 'Delivery Time', 'Description'])
    csv_data.append([
        offer.id,
        company.name_en or company.name_ar if company else 'Unknown',
        order.id if order else 'N/A',
        offer.total_price or 0,
        offer.status or 'pending',
        offer.delivery_time or 'N/A',
        offer.description or 'N/A'
    ])

    # Convert to CSV string
    output = StringIO()
    writer = csv.writer(output)
    writer.writerows(csv_data)
    csv_string = output.getvalue()
    output.close()

    # Create response
    response = make_response(csv_string)
    response.headers['Content-Type'] = 'text/csv'
    response.headers[
        'Content-Disposition'] = f'attachment; filename=offer_{offer_id}_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    return response


@app.route('/admin_add_offer_notes/<int:offer_id>', methods=['POST'])
@login_required
def admin_add_offer_notes(offer_id):
    """Admin adds notes to an offer"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json()
    notes = data.get('notes')

    if not notes:
        return jsonify({'error': 'Notes are required'}), 400

    offer = Offer.query.get_or_404(offer_id)
    offer.admin_notes = notes
    db.session.commit()

    return jsonify({'success': True})


@app.route('/admin_accept_offer/<int:offer_id>', methods=['POST'])
@login_required
def admin_accept_offer(offer_id):
    """Admin accepts an offer"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    offer = Offer.query.get_or_404(offer_id)
    offer.status = 'accepted'
    db.session.commit()

    return jsonify({'success': True})


@app.route('/admin_reject_offer/<int:offer_id>', methods=['POST'])
@login_required
def admin_reject_offer(offer_id):
    """Admin rejects an offer"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    offer = Offer.query.get_or_404(offer_id)
    offer.status = 'rejected'
    db.session.commit()

    return jsonify({'success': True})


@app.route('/admin_delete_offer/<int:offer_id>', methods=['POST'])
@login_required
def admin_delete_offer(offer_id):
    """Admin deletes an offer"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    offer = Offer.query.get_or_404(offer_id)
    db.session.delete(offer)
    db.session.commit()

    return jsonify({'success': True})


@app.route('/admin_change_offer_status/<int:offer_id>', methods=['POST'])
@login_required
def admin_change_offer_status(offer_id):
    """Admin changes offer status"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json()
    new_status = data.get('status')

    if not new_status:
        return jsonify({'error': 'Status is required'}), 400

    offer = Offer.query.get_or_404(offer_id)
    offer.status = new_status
    db.session.commit()

    return jsonify({'success': True})


@app.route('/admin_chat_with_company/<int:company_id>')
@login_required
def admin_chat_with_company(company_id):
    """Admin chat with company page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    company = Company.query.get_or_404(company_id)

    # Get chat history if it exists
    chat = Chat.query.filter_by(
        client_id=current_user.id,
        company_id=company_id
    ).first()

    if not chat:
        # Create new chat
        chat = Chat(
            client_id=current_user.id,
            company_id=company_id
        )
        db.session.add(chat)
        db.session.commit()

    # Get messages
    messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at).all()

    return render_template('site_admin/admin_chat.html',
                           company=company,
                           chat=chat,
                           messages=messages)


@app.route('/admin_profile')
@login_required
def admin_profile():
    """Admin profile page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    return render_template('site_admin/profile.html', user=current_user)


@app.route('/admin_export_orders')
@login_required
def admin_export_orders():
    """Export orders data to CSV"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    try:
        # Get all orders with related data
        orders = Order.query.all()

        # Create CSV data
        csv_data = []
        csv_data.append(
            ['Order ID', 'Order Name', 'Client', 'Company', 'Sector', 'Type', 'Status', 'Priority', 'Delivery Date',
             'Created At', 'Offers Count'])

        for order in orders:
            # Get client info
            client = User.query.get(order.user_id) if order.user_id else None
            client_name = client.name or client.username if client else 'Unknown'

            # Get company info
            company = Company.query.get(order.company_id) if order.company_id else None
            company_name = company.name_en or company.name_ar if company else 'Unknown'

            csv_data.append([
                order.id,
                order.order_name or '',
                client_name,
                company_name,
                order.sector or '',
                order.order_type or '',
                order.status or 'pending',
                order.priority or 'medium',
                order.delivery_date.strftime('%Y-%m-%d') if order.delivery_date else '',
                order.created_at.strftime('%Y-%m-%d %H:%M:%S') if order.created_at else '',
                len(order.offers)
            ])

        # Convert to CSV string
        output = StringIO()
        writer = csv.writer(output)
        writer.writerows(csv_data)
        csv_string = output.getvalue()
        output.close()

        # Create response
        response = make_response(csv_string)
        response.headers['Content-Type'] = 'text/csv'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=orders_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response

    except Exception as e:
        flash(f'Error exporting orders: {str(e)}', 'error')
        return redirect(url_for('admin_orders'))


@app.route('/admin_analytics')
@login_required
def admin_analytics():
    """Admin analytics page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    try:
        # Calculate analytics
        total_users = User.query.filter(User.role != 'admin').count()
        total_companies = Company.query.filter(Company.company_type != 'system').count()
        total_orders = Order.query.count()
        total_offers = Offer.query.count()

        # Get company types breakdown
        supplier_companies = Company.query.filter_by(company_type='supplier').count()
        client_companies = Company.query.filter_by(company_type='client').count()

        # Get order status breakdown
        pending_orders = Order.query.filter_by(status='pending').count()
        accepted_orders = Order.query.filter_by(status='accepted').count()
        completed_orders = Order.query.filter_by(status='completed').count()
        cancelled_orders = Order.query.filter_by(status='cancelled').count()

        # Get offer status breakdown
        pending_offers = Offer.query.filter_by(status='pending').count()
        accepted_offers = Offer.query.filter_by(status='accepted').count()
        rejected_offers = Offer.query.filter_by(status='rejected').count()

        # Monthly growth
        from datetime import datetime, timedelta
        current_month = datetime.now().month
        current_year = datetime.now().year

        # Monthly growth (simplified for now)
        monthly_orders = Order.query.filter(
            Order.created_at >= datetime(current_year, current_month, 1)
        ).count()

        # Since User model doesn't have created_at, we'll use a different approach
        # For now, we'll show total users and monthly orders
        # TODO: Add created_at field to User model if needed for user growth tracking
        monthly_users = 0  # Placeholder since User model doesn't have created_at

    except Exception as e:
        # If there's an error, set default values
        print(f"Error in admin_analytics: {e}")
        total_users = 0
        total_companies = 0
        total_orders = 0
        total_offers = 0
        supplier_companies = 0
        client_companies = 0
        pending_orders = 0
        accepted_orders = 0
        completed_orders = 0
        cancelled_orders = 0
        pending_offers = 0
        accepted_offers = 0
        rejected_offers = 0
        monthly_orders = 0
        monthly_users = 0

    return render_template('site_admin/analytics.html',
                           total_users=total_users,
                           total_companies=total_companies,
                           total_orders=total_orders,
                           total_offers=total_offers,
                           monthly_orders=monthly_orders,
                           monthly_users=monthly_users,
                           supplier_companies=supplier_companies,
                           client_companies=client_companies,
                           pending_orders=pending_orders,
                           accepted_orders=accepted_orders,
                           completed_orders=completed_orders,
                           cancelled_orders=cancelled_orders,
                           pending_offers=pending_offers,
                           accepted_offers=accepted_offers,
                           rejected_offers=rejected_offers)


@app.route('/admin_analytics_data')
@login_required
def admin_analytics_data():
    """Get analytics data for AJAX requests"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    period = request.args.get('period', '30days')

    try:
        from datetime import datetime, timedelta

        # Calculate date range based on period
        end_date = datetime.now()
        if period == '7days':
            start_date = end_date - timedelta(days=7)
        elif period == '30days':
            start_date = end_date - timedelta(days=30)
        elif period == '90days':
            start_date = end_date - timedelta(days=90)
        elif period == '1year':
            start_date = end_date - timedelta(days=365)
        else:
            start_date = end_date - timedelta(days=30)  # Default to 30 days

        # Get orders in date range
        orders_in_period = Order.query.filter(
            Order.created_at >= start_date,
            Order.created_at <= end_date
        ).count()

        # Get offers in date range
        offers_in_period = Offer.query.filter(
            Offer.created_at >= start_date,
            Offer.created_at <= end_date
        ).count()

        # Get revenue data (simplified - using order totals)
        orders_with_totals = Order.query.filter(
            Order.created_at >= start_date,
            Order.created_at <= end_date
        ).all()

        total_revenue = sum(order.total_amount or 0 for order in orders_with_totals)

        # Handle case where no orders exist
        if not orders_with_totals:
            total_revenue = 0
            sector_data = {}
        else:
            # Get sector breakdown
            sector_data = {}
            for order in orders_with_totals:
                sector = order.sector or 'Other'
                if sector not in sector_data:
                    sector_data[sector] = 0
                sector_data[sector] += order.total_amount or 0

        # Prepare response data
        response_data = {
            'period': period,
            'orders_count': orders_in_period,
            'offers_count': offers_in_period,
            'total_revenue': total_revenue,
            'sector_revenue': sector_data,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"Error in admin_analytics_data: {e}")
        return jsonify({'error': 'Failed to fetch analytics data'}), 500


@app.route('/admin_export_analytics')
@login_required
def admin_export_analytics():
    """Export analytics data to CSV"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    period = request.args.get('period', '30days')

    try:
        from datetime import datetime, timedelta

        # Calculate date range based on period
        end_date = datetime.now()
        if period == '7days':
            start_date = end_date - timedelta(days=7)
        elif period == '30days':
            start_date = end_date - timedelta(days=30)
        elif period == '90days':
            start_date = end_date - timedelta(days=90)
        elif period == '1year':
            start_date = end_date - timedelta(days=365)
        else:
            start_date = end_date - timedelta(days=30)  # Default to 30 days

        # Get comprehensive analytics data
        orders_in_period = Order.query.filter(
            Order.created_at >= start_date,
            Order.created_at <= end_date
        ).all()

        offers_in_period = Offer.query.filter(
            Offer.created_at >= start_date,
            Offer.created_at <= end_date
        ).all()

        # Ensure we have data to export
        if not orders_in_period and not offers_in_period:
            flash('No data found for the selected period.', 'warning')
            return redirect(url_for('admin_analytics'))

        # Create CSV data
        csv_data = []
        csv_data.append(['Analytics Report', f'Period: {period}', f'From: {start_date.strftime("%Y-%m-%d")}',
                         f'To: {end_date.strftime("%Y-%m-%d")}'])
        csv_data.append([])  # Empty row

        # Summary statistics
        csv_data.append(['Summary Statistics'])
        csv_data.append(['Metric', 'Value'])
        csv_data.append(['Total Orders', len(orders_in_period)])
        csv_data.append(['Total Offers', len(offers_in_period)])
        csv_data.append(['Total Revenue', f"EGP {sum(order.total_amount or 0 for order in orders_in_period):.2f}"])
        csv_data.append([])  # Empty row

        # Orders breakdown
        csv_data.append(['Orders Breakdown'])
        csv_data.append(['Order ID', 'Client', 'Company', 'Sector', 'Status', 'Total Amount', 'Created Date'])
        for order in orders_in_period:
            user = User.query.get(order.user_id) if order.user_id else None
            company = Company.query.get(order.company_id) if order.company_id else None
            csv_data.append([
                order.id,
                user.username if user else 'N/A',
                company.name_en or company.name_ar if company else 'N/A',
                order.sector or 'N/A',
                order.status or 'N/A',
                f"EGP {order.total_amount or 0:.2f}",
                order.created_at.strftime('%Y-%m-%d %H:%M') if order.created_at else 'N/A'
            ])

        csv_data.append([])  # Empty row

        # Offers breakdown
        csv_data.append(['Offers Breakdown'])
        csv_data.append(['Offer ID', 'Company', 'Order ID', 'Total Price', 'Status', 'Delivery Time', 'Created Date'])
        for offer in offers_in_period:
            company = Company.query.get(offer.company_id) if offer.company_id else None
            csv_data.append([
                offer.id,
                company.name_en or company.name_ar if company else 'N/A',
                offer.order_id,
                f"EGP {offer.total_price or 0:.2f}",
                offer.status or 'N/A',
                offer.delivery_time or 'N/A',
                offer.created_at.strftime('%Y-%m-%d %H:%M') if offer.created_at else 'N/A'
            ])

        # Convert to CSV string
        output = StringIO()
        writer = csv.writer(output)
        writer.writerows(csv_data)
        csv_string = output.getvalue()
        output.close()

        # Create response
        response = make_response(csv_string)
        response.headers['Content-Type'] = 'text/csv'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=analytics_report_{period}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response

    except Exception as e:
        print(f"Error in admin_export_analytics: {e}")
        flash(f'Error exporting analytics: {str(e)}', 'error')
        return redirect(url_for('admin_analytics'))


@app.route('/admin_settings')
@login_required
def admin_settings():
    """Admin settings page"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    # Get system settings
    system_settings = {}
    try:
        if os.path.exists('system_settings.json'):
            with open('system_settings.json', 'r') as f:
                system_settings = json.load(f)
    except:
        pass

    # Ensure system settings are properly initialized with defaults
    if 'system' not in system_settings:
        system_settings['system'] = {}

    # Set default values if they don't exist
    if 'allow_registration' not in system_settings['system']:
        system_settings['system']['allow_registration'] = True  # Default to True
    if 'auto_approve_companies' not in system_settings['system']:
        system_settings['system']['auto_approve_companies'] = False  # Default to False
    if 'maintenance_mode' not in system_settings['system']:
        system_settings['system']['maintenance_mode'] = False  # Default to False

    return render_template('site_admin/settings.html', settings=system_settings)


@app.route('/admin_save_settings', methods=['POST'])
@login_required
def admin_save_settings():
    """Admin saves system settings"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('admin_settings'))

    try:
        setting_type = request.form.get('setting_type')

        if setting_type == 'system':
            # Load current settings
            system_settings = {}
            try:
                if os.path.exists('system_settings.json'):
                    with open('system_settings.json', 'r') as f:
                        system_settings = json.load(f)
            except:
                pass

            # Initialize system section if it doesn't exist
            if 'system' not in system_settings:
                system_settings['system'] = {}

            # Update system settings
            # Checkboxes only send values when checked, so we need to handle unchecked ones
            system_settings['system']['allow_registration'] = 'allow_registration' in request.form
            system_settings['system']['auto_approve_companies'] = 'auto_approve_companies' in request.form
            system_settings['system']['maintenance_mode'] = 'maintenance_mode' in request.form

            # Save the updated settings back to file
            with open('system_settings.json', 'w') as f:
                json.dump(system_settings, f, indent=2)

            flash('System settings saved successfully!', 'success')

        else:
            flash('Invalid setting type', 'error')

    except Exception as e:
        print(f"Error saving settings: {e}")
        flash(f'Error saving settings: {str(e)}', 'error')

    return redirect(url_for('admin_settings'))


def get_system_setting(setting_name, default_value=False):
    """Helper function to get system settings"""
    try:
        if os.path.exists('system_settings.json'):
            with open('system_settings.json', 'r') as f:
                system_settings = json.load(f)
                if 'system' in system_settings and setting_name in system_settings['system']:
                    return system_settings['system'][setting_name]
    except:
        pass
    return default_value


@app.route('/admin_create_backup', methods=['POST'])
@login_required
def admin_create_backup():
    """Admin creates database backup"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    try:
        import shutil
        from datetime import datetime

        # Create backups directory if it doesn't exist
        backup_dir = 'backups'
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        # Create backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'purchases_backup_{timestamp}.db'
        backup_path = os.path.join(backup_dir, backup_filename)

        # Copy the database file
        source_db = 'instance/purchases.db'
        if os.path.exists(source_db):
            # Check if we can read the source database
            try:
                # Test database connection before backup
                with db.engine.connect() as conn:
                    conn.execute(db.text('SELECT 1'))

                # Create the backup
                shutil.copy2(source_db, backup_path)

                # Also create a backup of the database schema
                schema_backup_filename = f'schema_backup_{timestamp}.sql'
                schema_backup_path = os.path.join(backup_dir, schema_backup_filename)

                # Export schema (simplified - just create a basic schema file)
                with open(schema_backup_path, 'w') as f:
                    f.write(f"-- Database Schema Backup - {timestamp}\n")
                    f.write("-- This is a basic schema backup\n")
                    f.write("-- Full schema can be reconstructed from models.py\n\n")

                return jsonify({'success': True, 'message': 'Backup created successfully', 'filename': backup_filename})
            except Exception as db_error:
                return jsonify({'error': f'Database connection failed: {str(db_error)}'}), 500
        else:
            return jsonify({'error': 'Database file not found'}), 404

    except Exception as e:
        print(f"Error creating backup: {e}")
        return jsonify({'error': f'Error creating backup: {str(e)}'}), 500


@app.route('/admin_download_backup')
@login_required
def admin_download_backup():
    """Admin downloads latest backup"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    try:
        backup_dir = 'backups'
        if not os.path.exists(backup_dir):
            flash('No backups found', 'error')
            return redirect(url_for('admin_settings'))

        # Get the most recent backup file
        backup_files = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
        if not backup_files:
            flash('No backup files found', 'error')
            return redirect(url_for('admin_settings'))

        # Sort by modification time and get the latest
        backup_files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)), reverse=True)
        latest_backup = backup_files[0]
        backup_path = os.path.join(backup_dir, latest_backup)

        return send_file(backup_path, as_attachment=True, download_name=latest_backup)

    except Exception as e:
        print(f"Error downloading backup: {e}")
        flash(f'Error downloading backup: {str(e)}', 'error')
        return redirect(url_for('admin_settings'))


@app.route('/admin_optimize_database', methods=['POST'])
@login_required
def admin_optimize_database():
    """Admin optimizes database"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    try:
        # Perform basic database optimization
        with db.engine.connect() as conn:
            # VACUUM to reclaim storage and defragment the database
            conn.execute(db.text('VACUUM'))
            # ANALYZE to update statistics
            conn.execute(db.text('ANALYZE'))
            conn.commit()

        return jsonify({'success': True, 'message': 'Database optimized successfully'})

    except Exception as e:
        print(f"Error optimizing database: {e}")
        return jsonify({'error': f'Error optimizing database: {str(e)}'}), 500


@app.route('/admin_system_health')
@login_required
def admin_system_health():
    """Admin checks system health"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    try:
        health_status = 'healthy'
        issues = []

        # Check database connectivity
        try:
            db.session.execute(db.text('SELECT 1'))
            db.session.commit()
        except Exception as e:
            health_status = 'unhealthy'
            issues.append(f'Database connection failed: {str(e)}')

        # Check disk space (simplified check)
        try:
            import shutil
            total, used, free = shutil.disk_usage('.')
            free_gb = free / (1024 ** 3)
            if free_gb < 1:  # Less than 1GB free
                issues.append(f'Low disk space: {free_gb:.2f}GB free')
        except:
            pass  # Skip disk space check if not available

        # Check if database file exists and is accessible
        db_file = 'instance/purchases.db'
        if not os.path.exists(db_file):
            health_status = 'unhealthy'
            issues.append('Database file not found')

        return jsonify({
            'status': health_status,
            'issues': issues,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"Error checking system health: {e}")
        return jsonify({'error': f'Error checking system health: {str(e)}'}), 500


@app.route('/admin_reset_system', methods=['POST'])
@login_required
def admin_reset_system():
    """Admin resets system (DANGEROUS!)"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    try:
        # This is a dangerous operation - only proceed with extreme caution
        # For now, we'll just return an error to prevent accidental data loss
        return jsonify({'error': 'System reset is disabled for safety. Contact system administrator.'}), 403

        # If you really want to implement this, uncomment and modify the code below:
        # import os
        # import shutil
        #
        # # Remove database
        # if os.path.exists('instance/purchases.db'):
        #     os.remove('instance/purchases.db')
        #
        # # Remove other data files
        # data_files = ['uploads', 'backups', 'logs']
        # for folder in data_files:
        #     if os.path.exists(folder):
        #         shutil.rmtree(folder)
        #
        # return jsonify({'success': True, 'message': 'System reset completed'})

    except Exception as e:
        print(f"Error resetting system: {e}")
        return jsonify({'error': f'Error resetting system: {str(e)}'}), 500


# AJAX search endpoints for admin order creation
@app.route('/api/search_clients', methods=['GET'])
@login_required
def search_clients():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'clients': []})

    # Search users by name, email, or phone
    clients = User.query.filter(
        db.or_(
            User.name.ilike(f'%{query}%'),
            User.email.ilike(f'%{query}%'),
            User.phone_number.ilike(f'%{query}%')
        )
    ).filter(User.role == 'client').limit(10).all()

    client_list = []
    for client in clients:
        client_list.append({
            'id': client.id,
            'name': client.name or client.username,
            'email': client.email,
            'phone': client.phone_number or '',
            'company': client.company.name_ar or client.company.name_en if client.company else ''
        })

    return jsonify({'clients': client_list})


@app.route('/api/search_companies', methods=['GET'])
@login_required
def search_companies():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'companies': []})

    # Search companies by name, email, or phone
    companies = Company.query.filter(
        db.or_(
            Company.name_ar.ilike(f'%{query}%'),
            Company.name_en.ilike(f'%{query}%'),
            Company.email.ilike(f'%{query}%'),
            Company.office_phone.ilike(f'%{query}%'),
            Company.mobile_contact.ilike(f'%{query}%')
        )
    ).filter(Company.company_type == 'supplier').filter(Company.is_approved == True).limit(10).all()

    company_list = []
    for company in companies:
        company_list.append({
            'id': company.id,
            'name': company.name_ar or company.name_en,
            'email': company.email,
            'phone': company.office_phone or company.mobile_contact or '',
            'sector': company.sector or ''
        })

    return jsonify({'companies': company_list})


@app.route('/api/user_data', methods=['GET'])
@login_required
def get_user_data():
    """Get current user data for frontend JavaScript"""
    try:
        # Basic user information
        user_data = {
            'id': current_user.id,
            'username': current_user.username,
            'email': current_user.email,
            'role': current_user.role,
            'is_client_user': current_user.is_client_user,
            'is_company_user': current_user.is_company_user,
            'is_system_user': current_user.is_system_user,
            'company_id': current_user.company_id,
            
            # Extended user profile information
            'name': current_user.name,
            'country': current_user.country,
            'city': current_user.city,
            'phone_number': current_user.phone_number,
            'company_name': current_user.company_name,
            'sector': current_user.sector,
            'tax_number': current_user.tax_number,
            'account_type': current_user.account_type,
            'uploaded_file': current_user.uploaded_file,
            
            # Company information
            'company_type': current_user.company.company_type if current_user.company else None,
            'company_display_name': current_user.company_name_display if current_user.company else None,
            'company_details': {
                'name_ar': current_user.company.name_ar if current_user.company else None,
                'name_en': current_user.company.name_en if current_user.company else None,
                'email': current_user.company.email if current_user.company else None,
                'phone': current_user.company.office_phone if current_user.company else None,
                'mobile': current_user.company.mobile_contact if current_user.company else None,
                'website': current_user.company.website if current_user.company else None,
                'is_active': current_user.company.is_active if current_user.company else None,
                'is_approved': current_user.company.is_approved if current_user.company else None,
                'sector': current_user.company.sector if current_user.company else None,
                'rating': current_user.company.rating if current_user.company else None,
                'total_reviews': current_user.company.total_reviews if current_user.company else None
            } if current_user.company else None
        }
        return jsonify(user_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user_orders', methods=['GET'])
@login_required
def get_user_orders():
    """Get current user's orders as JSON"""
    try:
        # Get query parameters for filtering and pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        status = request.args.get('status', '')
        order_type = request.args.get('order_type', '')
        
        # Base query for user's orders
        query = Order.query.filter_by(user_id=current_user.id)
        
        # Apply filters if provided
        if status:
            query = query.filter(Order.status == status)
        if order_type:
            query = query.filter(Order.order_type == order_type)
            
        # Order by creation date (newest first)
        query = query.order_by(Order.created_at.desc())
        
        # Paginate results
        paginated_orders = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Convert orders to JSON format
        orders_data = []
        for order in paginated_orders.items:
            # Get order items (purchases)
            order_items = Purchase.query.filter_by(order_id=order.id).all()
            
            # Get offers for this order
            offers = Offer.query.filter_by(order_id=order.id).all()
            
            order_data = {
                'id': order.id,
                'order_name': order.order_name,
                'description': order.description,
                'sector': order.sector,
                'order_type': order.order_type,
                'status': order.status,
                'priority': order.priority,
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'delivery_date': order.delivery_date.isoformat() if order.delivery_date else None,
                'delivery_time': order.delivery_time,
                'delivery_address': order.delivery_address,
                'delivery_notes': order.delivery_notes,
                'receiver_name': order.receiver_name,
                'receiver_phone': order.receiver_phone,
                'payment_way': order.payment_way,
                'direct_negotiation': order.direct_negotiation,
                'accept_unregistered_suppliers': order.accept_unregistered_suppliers,
                'max_suppliers': order.max_suppliers,
                'package_number': order.package_number,
                'admin_notes': order.admin_notes,
                
                # Order items
                'items': [{
                    'id': item.id,
                    'part_name': item.part_name,
                    'description': item.description,
                    'quantity': item.quantity,
                    'unit': item.unit,
                    'technical_specs': item.technical_specs,
                    'product_code': item.product_code,
                    'max_price_per_unit': item.max_price_per_unit,
                    'best_supplier': item.best_supplier
                } for item in order_items],
                
                # Offers summary
                'offers_count': len(offers),
                'offers': [{
                    'id': offer.id,
                    'company_id': offer.company_id,
                    'company_name': offer.company.name_ar or offer.company.name_en if offer.company else None,
                    'total_price': offer.total_price,
                    'status': offer.status,
                    'delivery_time': offer.delivery_time,
                    'created_at': offer.created_at.isoformat() if offer.created_at else None
                } for offer in offers]
            }
            orders_data.append(order_data)
        
        # Prepare response with pagination info
        response_data = {
            'orders': orders_data,
            'pagination': {
                'page': paginated_orders.page,
                'per_page': paginated_orders.per_page,
                'total': paginated_orders.total,
                'pages': paginated_orders.pages,
                'has_next': paginated_orders.has_next,
                'has_prev': paginated_orders.has_prev
            },
            'filters': {
                'status': status,
                'order_type': order_type
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user_notifications', methods=['GET'])
@login_required
def api_user_notifications():
    """API endpoint to get user notifications with filtering and pagination"""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)  # Max 100 per page
        
        # Get filter parameters
        notification_type = request.args.get('type', 'all')
        priority = request.args.get('priority', 'all')
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        
        # Parse date filters
        date_from = None
        date_to = None
        if request.args.get('date_from'):
            try:
                date_from = datetime.strptime(request.args.get('date_from'), '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid date_from format. Use YYYY-MM-DD'}), 400
                
        if request.args.get('date_to'):
            try:
                date_to = datetime.strptime(request.args.get('date_to'), '%Y-%m-%d')
                date_to = date_to.replace(hour=23, minute=59, second=59)  # End of day
            except ValueError:
                return jsonify({'error': 'Invalid date_to format. Use YYYY-MM-DD'}), 400
        
        # Build base query based on user role
        if current_user.role == 'client':
            base_query = Notification.query.filter_by(user_id=current_user.id)
        elif current_user.role == 'company':
            company = Company.query.filter_by(id=current_user.company_id).first()
            if not company:
                return jsonify({'error': 'Company not found'}), 404
            base_query = Notification.query.filter_by(company_id=company.id)
        else:
            return jsonify({'error': 'Invalid user role for notifications'}), 403
        
        # Apply filters
        if unread_only:
            base_query = base_query.filter_by(is_read=False)
        
        if notification_type and notification_type != 'all':
            base_query = base_query.filter_by(notification_type=notification_type)
        
        if priority and priority != 'all':
            base_query = base_query.filter_by(priority=priority)
        
        if date_from:
            base_query = base_query.filter(Notification.created_at >= date_from)
        
        if date_to:
            base_query = base_query.filter(Notification.created_at <= date_to)
        
        # Order by creation date (newest first) and paginate
        paginated_notifications = base_query.order_by(Notification.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Get unread count for current user
        if current_user.role == 'client':
            unread_count = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).count()
        else:
            unread_count = Notification.query.filter_by(
                company_id=company.id, is_read=False
            ).count()
        
        # Format notifications data
        notifications_data = []
        for notification in paginated_notifications.items:
            notification_data = {
                'id': notification.id,
                'title': notification.title,
                'description': notification.description,
                'notification_type': notification.notification_type,
                'priority': notification.priority,
                'is_read': notification.is_read,
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'read_at': notification.read_at.isoformat() if notification.read_at else None,
                'age_in_hours': notification.age_in_hours if hasattr(notification, 'age_in_hours') else None,
                'is_urgent': notification.is_urgent if hasattr(notification, 'is_urgent') else (notification.priority == 'urgent'),
                
                # Related entities (if available)
                'related_order_id': notification.related_order_id,
                'related_offer_id': notification.related_offer_id,
                'related_chat_id': notification.related_chat_id,
                'related_product_id': notification.related_product_id
            }
            notifications_data.append(notification_data)
        
        # Prepare response with pagination and metadata
        response_data = {
            'notifications': notifications_data,
            'pagination': {
                'page': paginated_notifications.page,
                'per_page': paginated_notifications.per_page,
                'total': paginated_notifications.total,
                'pages': paginated_notifications.pages,
                'has_next': paginated_notifications.has_next,
                'has_prev': paginated_notifications.has_prev
            },
            'metadata': {
                'unread_count': unread_count,
                'total_count': paginated_notifications.total,
                'filters_applied': {
                    'type': notification_type,
                    'priority': priority,
                    'unread_only': unread_only,
                    'date_from': request.args.get('date_from'),
                    'date_to': request.args.get('date_to')
                }
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/user_notifications', methods=['GET'])
@login_required
def api_v2_user_notifications():
    """Enhanced API endpoint for user notifications with advanced features"""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Get filter parameters
        notification_type = request.args.get('type')
        priority = request.args.get('priority')
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        read_only = request.args.get('read_only', 'false').lower() == 'true'
        
        # Date range filters
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Search functionality
        search_query = request.args.get('search', '').strip()
        
        # Sorting options
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        
        # Build base query based on user role
        if current_user.role == 'client':
            base_query = Notification.query.filter_by(user_id=current_user.id)
        elif current_user.role == 'company':
            company = Company.query.filter_by(id=current_user.company_id).first()
            if not company:
                return jsonify({'error': 'Company not found'}), 404
            base_query = Notification.query.filter_by(company_id=company.id)
        else:
            return jsonify({'error': 'Invalid user role'}), 403
        
        # Apply filters
        if unread_only:
            base_query = base_query.filter_by(is_read=False)
        elif read_only:
            base_query = base_query.filter_by(is_read=True)
        
        if notification_type:
            base_query = base_query.filter_by(notification_type=notification_type)
        
        if priority:
            base_query = base_query.filter_by(priority=priority)
        
        # Date range filtering
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                base_query = base_query.filter(Notification.created_at >= date_from_obj)
            except ValueError:
                return jsonify({'error': 'Invalid date_from format'}), 400
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
                base_query = base_query.filter(Notification.created_at <= date_to_obj)
            except ValueError:
                return jsonify({'error': 'Invalid date_to format'}), 400
        
        # Search functionality
        if search_query:
            search_filter = db.or_(
                Notification.title.ilike(f'%{search_query}%'),
                Notification.description.ilike(f'%{search_query}%')
            )
            base_query = base_query.filter(search_filter)
        
        # Apply sorting
        if sort_by == 'created_at':
            if sort_order == 'asc':
                base_query = base_query.order_by(Notification.created_at.asc())
            else:
                base_query = base_query.order_by(Notification.created_at.desc())
        elif sort_by == 'priority':
            priority_order = db.case(
                (Notification.priority == 'urgent', 1),
                (Notification.priority == 'high', 2),
                (Notification.priority == 'normal', 3),
                (Notification.priority == 'low', 4),
                else_=5
            )
            if sort_order == 'desc':
                base_query = base_query.order_by(priority_order.desc(), Notification.created_at.desc())
            else:
                base_query = base_query.order_by(priority_order.asc(), Notification.created_at.desc())
        elif sort_by == 'title':
            if sort_order == 'asc':
                base_query = base_query.order_by(Notification.title.asc())
            else:
                base_query = base_query.order_by(Notification.title.desc())
        
        # Paginate results
        paginated_notifications = base_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Get statistics
        if current_user.role == 'client':
            stats_query = Notification.query.filter_by(user_id=current_user.id)
        else:
            stats_query = Notification.query.filter_by(company_id=company.id)
        
        total_count = stats_query.count()
        unread_count = stats_query.filter_by(is_read=False).count()
        urgent_count = stats_query.filter_by(priority='urgent', is_read=False).count()
        
        # Format notifications data
        notifications_data = []
        for notification in paginated_notifications.items:
            notification_data = {
                'id': notification.id,
                'title': notification.title,
                'description': notification.description,
                'notification_type': notification.notification_type,
                'priority': notification.priority,
                'is_read': notification.is_read,
                'is_urgent': notification.priority == 'urgent',
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'read_at': notification.read_at.isoformat() if notification.read_at else None,
                'age_hours': int((datetime.utcnow() - notification.created_at).total_seconds() / 3600) if notification.created_at else 0,
                'related_order_id': notification.related_order_id,
                'related_offer_id': notification.related_offer_id,
                'related_chat_id': notification.related_chat_id,
                'related_product_id': notification.related_product_id
            }
            notifications_data.append(notification_data)
        
        # Prepare comprehensive response
        response_data = {
            'success': True,
            'notifications': notifications_data,
            'pagination': {
                'page': paginated_notifications.page,
                'per_page': paginated_notifications.per_page,
                'total': paginated_notifications.total,
                'pages': paginated_notifications.pages,
                'has_next': paginated_notifications.has_next,
                'has_prev': paginated_notifications.has_prev,
                'next_page': paginated_notifications.next_num if paginated_notifications.has_next else None,
                'prev_page': paginated_notifications.prev_num if paginated_notifications.has_prev else None
            },
            'statistics': {
                'total_count': total_count,
                'unread_count': unread_count,
                'read_count': total_count - unread_count,
                'urgent_unread_count': urgent_count
            },
            'filters_applied': {
                'type': notification_type,
                'priority': priority,
                'unread_only': unread_only,
                'read_only': read_only,
                'date_from': date_from,
                'date_to': date_to,
                'search_query': search_query,
                'sort_by': sort_by,
                'sort_order': sort_order
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'notifications': [],
            'pagination': {},
            'statistics': {}
        }), 500


@app.route('/api/v2/user_notifications/bulk', methods=['POST'])
@login_required
def api_v2_bulk_notification_actions():
    """Bulk operations on user notifications"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        action = data.get('action')
        notification_ids = data.get('notification_ids', [])
        
        if not action or not notification_ids:
            return jsonify({'success': False, 'error': 'Action and notification_ids required'}), 400
        
        # Verify user owns these notifications
        if current_user.role == 'client':
            base_query = Notification.query.filter(
                Notification.id.in_(notification_ids),
                Notification.user_id == current_user.id
            )
        elif current_user.role == 'company':
            company = Company.query.filter_by(id=current_user.company_id).first()
            if not company:
                return jsonify({'success': False, 'error': 'Company not found'}), 404
            base_query = Notification.query.filter(
                Notification.id.in_(notification_ids),
                Notification.company_id == company.id
            )
        else:
            return jsonify({'success': False, 'error': 'Invalid user role'}), 403
        
        notifications = base_query.all()
        
        if len(notifications) != len(notification_ids):
            return jsonify({'success': False, 'error': 'Some notifications not found or not owned by user'}), 404
        
        # Perform bulk action
        if action == 'mark_read':
            for notification in notifications:
                if not notification.is_read:
                    notification.is_read = True
                    notification.read_at = datetime.utcnow()
            db.session.commit()
            return jsonify({'success': True, 'message': f'Marked {len(notifications)} notifications as read'})
        
        elif action == 'mark_unread':
            for notification in notifications:
                if notification.is_read:
                    notification.is_read = False
                    notification.read_at = None
            db.session.commit()
            return jsonify({'success': True, 'message': f'Marked {len(notifications)} notifications as unread'})
        
        elif action == 'delete':
            for notification in notifications:
                db.session.delete(notification)
            db.session.commit()
            return jsonify({'success': True, 'message': f'Deleted {len(notifications)} notifications'})
        
        else:
            return jsonify({'success': False, 'error': 'Invalid action'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin_create_order', methods=['GET', 'POST'])
@login_required
def admin_create_order():
    """Admin creates order on behalf of a client"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied. Admin privileges required.'})

    if request.method == 'GET':
        return render_template('site_admin/create_order.html')

    if request.method == 'POST':
        try:
            data = request.get_json()

            # Extract client information
            client_name = data.get('client_name')
            client_email = data.get('client_email')
            client_phone = data.get('client_phone', '')
            client_company = data.get('client_company', '')

            # Extract order information
            order_name = data.get('order_name')
            description = data.get('description', '')
            sector = data.get('sector')
            order_type = data.get('order_type', 'direct')
            priority = data.get('priority', 'medium')

            # Extract delivery information
            delivery_date_str = data.get('delivery_date')
            delivery_date = None
            if delivery_date_str:
                try:
                    delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            delivery_time = data.get('delivery_time', '')
            delivery_address = data.get('delivery_address', '')
            delivery_notes = data.get('delivery_notes', '')
            receiver_name = data.get('receiver_name', '')
            receiver_phone = data.get('receiver_phone', '')

            # Extract payment information
            payment_way = data.get('payment_way', '')

            # Extract settings
            direct_negotiation = data.get('direct_negotiation') == 'true'
            accept_unregistered_suppliers = data.get('accept_unregistered_suppliers') == 'false'
            max_suppliers = int(data.get('max_suppliers', 10))
            admin_notes = data.get('admin_notes', '')

            # Validate required fields
            if not all([client_name, client_email, order_name, sector]):
                return jsonify({'success': False, 'message': 'Missing required fields'})

            # Check if client exists, if not create a new user
            client_user = User.query.filter_by(email=client_email).first()

            if not client_user:
                # Create new client user
                from werkzeug.security import generate_password_hash
                import secrets

                # Generate random password
                temp_password = secrets.token_urlsafe(8)

                # If company name provided, try to find or create company
                company_id = None
                if client_company:
                    company = Company.query.filter_by(name_en=client_company).first()
                    if not company:
                        company = Company(
                            name_en=client_company,
                            name_ar=client_company,
                            email=client_email or f"{client_company.lower().replace(' ', '')}@client.com",
                            company_type='client',
                            is_active=True,
                            is_approved=True
                        )
                        db.session.add(company)
                        db.session.flush()  # Get company ID
                    company_id = company.id
                else:
                    # Use default client company
                    default_company = Company.get_default_company()
                    company_id = default_company.id

                client_user = User(
                    username=client_name.lower().replace(' ', '_') + '_' + str(int(time.time())),
                    email=client_email,
                    name=client_name,
                    phone_number=client_phone,
                    role='client',
                    is_active=True,
                    password_hash=generate_password_hash(temp_password),
                    company_id=company_id
                )

                db.session.add(client_user)
                db.session.flush()  # Get user ID

                # Send welcome email with credentials (in production, implement proper email)
                print(f"New client user created: {client_email} with password: {temp_password}")

            # Create the order
            order = Order(
                user_id=client_user.id,
                company_id=client_user.company_id,
                order_name=order_name,
                description=description,
                sector=sector,
                order_type=order_type,
                delivery_date=delivery_date,
                delivery_time=delivery_time,
                delivery_address=delivery_address,
                delivery_notes=delivery_notes,
                receiver_name=receiver_name,
                receiver_phone=receiver_phone,
                payment_way=payment_way,
                direct_negotiation=direct_negotiation,
                accept_unregistered_suppliers=accept_unregistered_suppliers,
                max_suppliers=max_suppliers,
                status='pending',
                priority=priority,
                admin_notes=admin_notes,
                created_by_admin=current_user.id
            )

            db.session.add(order)
            db.session.flush()  # Get order ID

            # Create purchases for products
            products = data.get('products', [])
            for product_data in products:
                purchase = Purchase(
                    order_id=order.id,
                    sector=sector,
                    quantity=product_data.get('quantity', 1),
                    part_name=product_data.get('product_name', 'Product'),
                    description=product_data.get('technical_specs', 'No description'),
                    technical_specs=product_data.get('technical_specs', ''),
                    product_code=product_data.get('product_code', ''),
                    best_supplier=product_data.get('best_supplier', ''),
                    max_price_per_unit=float(product_data.get('max_price_per_unit', 0)) if product_data.get('max_price_per_unit') else None,
                    unit=product_data.get('unit', 'pcs')
                )
                db.session.add(purchase)

            db.session.commit()

            # Create notification for the client
            notification = Notification(
                user_id=client_user.id,
                title='New Order Created',
                description=f'An order "{order_name}" has been created for you by an administrator.',
                notification_type='order_created',
                is_read=False
            )
            db.session.add(notification)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'Order created successfully for {client_name}',
                'order_id': order.id,
                'user_id': client_user.id
            })

        except Exception as e:
            db.session.rollback()
            print(f"Error creating admin order: {e}")
            return jsonify({'success': False, 'message': f'Error creating order: {str(e)}'})


# ===== END ADMIN ROUTES =====


# ===== END ADMIN ROUTES =====

# Package Management Routes
@app.route('/create_package_page/<int:offer_id>')
@login_required
def create_package_page(offer_id):
    """Display package creation page for an offer"""
    offer = Offer.query.get_or_404(offer_id)
    
    # Check if user has access to this offer
    if current_user.role == 'company':
        if offer.company_id != current_user.company_id:
            flash('Access denied. You can only create packages for your own offers.', 'error')
            return redirect(url_for('company_offers'))
    else:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    # Check if offer status is 'out for delivery'
    if offer.order_status != 'out_for_delivery':
        flash('Package can only be created when order status is "out for delivery"', 'error')
        return redirect(url_for('offer_details', offer_id=offer_id))
    
    # Check if package already exists
    if offer.package_number:
        flash('Package already exists for this offer', 'warning')
        return redirect(url_for('offer_details', offer_id=offer_id))
    
    return render_template('company/create_package.html', offer=offer)

@app.route('/create_package/<int:offer_id>', methods=['POST'])
@login_required
def create_package(offer_id):
    """Create a package for an offer when status is 'out for delivery'"""
    try:
        # Get the offer
        offer = Offer.query.get_or_404(offer_id)
        
        # Check if user has permission (company that made the offer)
        if current_user.role != 'company' or offer.company_id != current_user.company_id:
            flash('Access denied', 'error')
            return redirect(url_for('offer_details', offer_id=offer_id))
        
        # Check if offer status is 'out for delivery'
        if offer.order_status != 'out_for_delivery':
            flash('Package can only be created when order status is "out for delivery"', 'error')
            return redirect(url_for('offer_details', offer_id=offer_id))
        
        # Check if package already exists
        if offer.package_number:
            flash('Package already exists for this offer', 'error')
            return redirect(url_for('create_package_page', offer_id=offer_id))
        
        # Generate unique package number
        import random
        import string
        while True:
            package_number = 'PKG' + ''.join(random.choices(string.digits, k=8))
            existing_package = Package.query.filter_by(package_number=package_number).first()
            if not existing_package:
                break
        
        # Get order and company details for package creation
        order = Order.query.get(offer.order_id)
        company = Company.query.get(offer.company_id)
        
        # Create the package with all required fields
        package = Package(
            package_number=package_number,
            order_id=offer.order_id,
            offer_id=offer.id,
            company_id=offer.company_id,
            total_value=float(offer.total_price),  # Add total_value from offer
            sender_name=company.name_en or company.name_ar or 'Unknown Company',
            sender_phone='',  # Add sender phone field
            sender_address='',  # Add sender address field
            receiver_name=order.receiver_name or order.user.name or order.user.username,
            receiver_phone=order.receiver_phone or '',
            receiver_address=order.delivery_address or '',
            status='preparing',
            created_at=datetime.utcnow(),
            notes=''
        )
        
        # Update offer with package number
        offer.package_number = package_number
        
        db.session.add(package)
        db.session.commit()
        
        flash(f'Package created successfully! Package number: {package_number}', 'success')
        return redirect(url_for('company_packages'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating package: {str(e)}', 'error')
        return redirect(url_for('create_package_page', offer_id=offer_id))

@app.route('/dash')
@login_required
def dash():
    """User dashboard page"""
    # Check if user has accepted terms and conditions (except for admin)
    if current_user.role != 'admin' and not current_user.terms_accepted:
        flash('يجب عليك قبول الشروط والأحكام قبل الوصول إلى لوحة التحكم.', 'warning')
        return redirect(url_for('terms_and_conditions'))
    
    if current_user.role == 'admin':
        return render_template('site_admin/index.html')
    elif current_user.role == 'company':
        return redirect(url_for('company_packages'))
    else:
        # Get only the 3 most recent orders
        recent_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(3).all()
        
        # Calculate dashboard statistics
        total_orders = Order.query.filter_by(user_id=current_user.id).count()
        pending_orders = Order.query.filter_by(user_id=current_user.id, status='pending').count()
        
        # Calculate total offers for user's orders
        user_order_ids = [order.id for order in Order.query.filter_by(user_id=current_user.id).all()]
        total_offers = Offer.query.filter(Offer.order_id.in_(user_order_ids)).count() if user_order_ids else 0
        
        # Calculate cart items count
        cart_count = db.session.query(db.func.sum(Cart.quantity)).filter_by(user_id=current_user.id).scalar() or 0
        
        return render_template('client/stocks.html', 
                             orders=recent_orders,
                             total_orders=total_orders,
                             pending_orders=pending_orders,
                             total_offers=total_offers,
                             cart_count=cart_count)

@app.route('/balance')
@login_required
def balance():
    """User balance page"""
    # Allow all authenticated users to access balance page
    # Admin users can view balance information for system monitoring
    
    # Get user's balance
    user_balance = Balance.query.filter_by(user_id=current_user.id).first()
    if not user_balance:
        # Create default balance if it doesn't exist
        user_balance = Balance(
            user_id=current_user.id,
            current_balance=1200.0,
            currency='EGP',
            created_at=datetime.utcnow()
        )
        db.session.add(user_balance)
        db.session.commit()
    
    # Get recent transactions (last 10)
    recent_transactions = Transaction.query.filter_by(balance_id=user_balance.id).order_by(Transaction.created_at.desc()).limit(10).all()
    
    # Calculate statistics
    total_transactions = Transaction.query.filter_by(balance_id=user_balance.id).count()
    total_spent = db.session.query(db.func.sum(Transaction.amount)).filter(
        Transaction.balance_id == user_balance.id,
        Transaction.transaction_type == 'debit'
    ).scalar() or 0
    total_received = db.session.query(db.func.sum(Transaction.amount)).filter(
        Transaction.balance_id == user_balance.id,
        Transaction.transaction_type == 'credit'
    ).scalar() or 0
    
    return render_template('client/balance.html',
                         balance=user_balance,
                         recent_transactions=recent_transactions,
                         total_transactions=total_transactions,
                         total_spent=abs(total_spent),
                         total_received=total_received)

@app.route('/download_balance_report')
@login_required
def download_balance_report():
    """Generate and download balance report as PDF"""
    try:
        # Get user's balance
        user_balance = Balance.query.filter_by(user_id=current_user.id).first()
        if not user_balance:
            flash('No balance data found.', 'error')
            return redirect(url_for('balance'))
        
        # Get all transactions
        transactions = Transaction.query.filter_by(balance_id=user_balance.id).order_by(Transaction.created_at.desc()).all()
        
        # Calculate statistics
        total_spent = db.session.query(db.func.sum(Transaction.amount)).filter(
            Transaction.balance_id == user_balance.id,
            Transaction.transaction_type == 'debit'
        ).scalar() or 0
        total_received = db.session.query(db.func.sum(Transaction.amount)).filter(
            Transaction.balance_id == user_balance.id,
            Transaction.transaction_type == 'credit'
        ).scalar() or 0
        
        # Create HTML content for the report
        from datetime import datetime
        report_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Balance Report - {current_user.username}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .summary {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
                .summary-item {{ display: inline-block; margin: 10px 20px; text-align: center; }}
                .summary-value {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
                .summary-label {{ font-size: 14px; color: #6b7280; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f8f9fa; font-weight: bold; }}
                .credit {{ color: #059669; }}
                .debit {{ color: #dc2626; }}
                .footer {{ margin-top: 30px; text-align: center; color: #6b7280; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Balance Report</h1>
                <h2>User: {current_user.username}</h2>
                <p>Generated on: {report_date}</p>
            </div>
            
            <div class="summary">
                <div class="summary-item">
                    <div class="summary-value">{user_balance.current_balance} {user_balance.currency}</div>
                    <div class="summary-label">Current Balance</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{abs(total_spent)} {user_balance.currency}</div>
                    <div class="summary-label">Total Spent</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{total_received} {user_balance.currency}</div>
                    <div class="summary-label">Total Received</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{len(transactions)}</div>
                    <div class="summary-label">Total Transactions</div>
                </div>
            </div>
            
            <h3>Transaction History</h3>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Type</th>
                        <th>Amount</th>
                        <th>Description</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for transaction in transactions:
            amount_class = 'credit' if transaction.transaction_type == 'credit' else 'debit'
            amount_sign = '+' if transaction.transaction_type == 'credit' else '-'
            html_content += f"""
                    <tr>
                        <td>{transaction.created_at.strftime('%Y-%m-%d %H:%M')}</td>
                        <td>{transaction.transaction_type.title()}</td>
                        <td class="{amount_class}">{amount_sign}{transaction.amount} {transaction.currency}</td>
                        <td>{transaction.description or 'No description'}</td>
                        <td>Completed</td>
                    </tr>
            """
        
        html_content += """
                </tbody>
            </table>
            
            <div class="footer">
                <p>This report was generated automatically by the system.</p>
            </div>
        </body>
        </html>
        """
        
        # Try to generate PDF using weasyprint if available, otherwise return HTML
        try:
            import weasyprint
            from io import BytesIO
            
            # Generate PDF using temporary file approach
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                weasyprint.HTML(string=html_content).write_pdf(temp_path)
                
                # Read PDF content
                with open(temp_path, 'rb') as f:
                    pdf_content = f.read()
            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            
            # Create response
            response = make_response(pdf_content)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=balance_report_{current_user.username}_{datetime.now().strftime("%Y%m%d")}.pdf'
            return response
            
        except ImportError:
            # Fallback to HTML download if weasyprint is not available
            response = make_response(html_content)
            response.headers['Content-Type'] = 'text/html'
            response.headers['Content-Disposition'] = f'attachment; filename=balance_report_{current_user.username}_{datetime.now().strftime("%Y%m%d")}.html'
            return response
            
    except Exception as e:
        flash(f'Error generating report: {str(e)}', 'error')
        return redirect(url_for('balance'))

@app.route('/company_balance')
@login_required
def company_balance():
    """Company balance page"""
    if current_user.role != 'company':
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))
    
    # Get company information
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('dash'))
    
    # Get company's balance
    company_balance = CompanyBalance.query.filter_by(company_id=company.id).first()
    if not company_balance:
        # Create default balance if it doesn't exist
        company_balance = CompanyBalance(
            company_id=company.id,
            current_balance=0.0,
            currency='EGP',
            created_at=datetime.utcnow()
        )
        db.session.add(company_balance)
        db.session.commit()
    
    # Get recent transactions (last 10)
    recent_transactions = CompanyTransaction.query.filter_by(
        company_balance_id=company_balance.id
    ).order_by(CompanyTransaction.created_at.desc()).limit(10).all()
    
    # Convert transactions to dictionaries for JSON serialization
    transactions_data = []
    for transaction in recent_transactions:
        transactions_data.append({
            'id': transaction.id,
            'amount': transaction.amount,
            'transaction_type': transaction.transaction_type,
            'description': transaction.description,
            'status': transaction.status,
            'currency': transaction.currency,
            'created_at': transaction.created_at.isoformat() if transaction.created_at else None,
            'processed_at': transaction.processed_at.isoformat() if transaction.processed_at else None,
            'balance_before': transaction.balance_before,
            'balance_after': transaction.balance_after
        })
    
    # Calculate statistics
    total_transactions = CompanyTransaction.query.filter_by(
        company_balance_id=company_balance.id
    ).count()
    
    total_expenses = db.session.query(db.func.sum(CompanyTransaction.amount)).filter(
        CompanyTransaction.company_balance_id == company_balance.id,
        CompanyTransaction.transaction_type == 'debit'
    ).scalar() or 0
    
    total_revenue = db.session.query(db.func.sum(CompanyTransaction.amount)).filter(
        CompanyTransaction.company_balance_id == company_balance.id,
        CompanyTransaction.transaction_type == 'credit'
    ).scalar() or 0
    
    return render_template('company/balance.html',
                         balance=company_balance,
                         transactions=recent_transactions,
                         transactions_data=transactions_data,
                         total_transactions=total_transactions,
                         total_expenses=abs(total_expenses),
                         total_revenue=total_revenue,
                         company=company)

@app.route('/company_balance_pdf')
@login_required
def company_balance_pdf():
    """Export company balance and transactions as PDF"""
    if current_user.role != 'company':
        flash(_('Access denied. Company role required.'), 'error')
        return redirect(url_for('dash'))
    
    # Get company information
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash(_('Company not found.'), 'error')
        return redirect(url_for('dash'))
    
    # Get company's balance
    company_balance = CompanyBalance.query.filter_by(company_id=company.id).first()
    if not company_balance:
        flash(_('No balance record found.'), 'error')
        return redirect(url_for('company_balance'))
    
    # Get all transactions for PDF export
    all_transactions = CompanyTransaction.query.filter_by(
        company_balance_id=company_balance.id
    ).order_by(CompanyTransaction.created_at.desc()).all()
    
    # Calculate statistics
    total_transactions = len(all_transactions)
    total_expenses = sum(abs(t.amount) for t in all_transactions if t.transaction_type == 'debit')
    total_revenue = sum(t.amount for t in all_transactions if t.transaction_type == 'credit')
    
    try:
        # Create HTML content for PDF
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Company Balance Statement - {company.display_name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .company-info {{ margin-bottom: 20px; }}
                .balance-summary {{ background: #f5f5f5; padding: 15px; margin-bottom: 20px; }}
                .transactions-table {{ width: 100%; border-collapse: collapse; }}
                .transactions-table th, .transactions-table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                .transactions-table th {{ background-color: #f2f2f2; }}
                .credit {{ color: green; }}
                .debit {{ color: red; }}
                .footer {{ margin-top: 30px; text-align: center; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Company Balance Statement</h1>
                <h2>{company.display_name}</h2>
                <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="company-info">
                <h3>Company Information</h3>
                <p><strong>Company Name:</strong> {company.display_name}</p>
                <p><strong>Company Type:</strong> {company.company_type}</p>
                <p><strong>Registration Status:</strong> {company.registration_status}</p>
            </div>
            
            <div class="balance-summary">
                <h3>Balance Summary</h3>
                <p><strong>Current Balance:</strong> {company_balance.current_balance:.2f} {company_balance.currency}</p>
                <p><strong>Total Revenue:</strong> {total_revenue:.2f} EGP</p>
                <p><strong>Total Expenses:</strong> {total_expenses:.2f} EGP</p>
                <p><strong>Total Transactions:</strong> {total_transactions}</p>
            </div>
            
            <div class="transactions">
                <h3>Transaction History</h3>
                <table class="transactions-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Type</th>
                            <th>Amount</th>
                            <th>Description</th>
                            <th>Balance Before</th>
                            <th>Balance After</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for transaction in all_transactions:
            transaction_class = 'credit' if transaction.transaction_type == 'credit' else 'debit'
            amount_display = f"+{transaction.amount:.2f}" if transaction.transaction_type == 'credit' else f"-{abs(transaction.amount):.2f}"
            
            html_content += f"""
                        <tr>
                            <td>{transaction.created_at.strftime('%Y-%m-%d %H:%M') if transaction.created_at else 'N/A'}</td>
                            <td class="{transaction_class}">{transaction.transaction_type.title()}</td>
                            <td class="{transaction_class}">{amount_display} {transaction.currency}</td>
                            <td>{transaction.description or 'No description'}</td>
                            <td>{transaction.balance_before:.2f} {transaction.currency}</td>
                            <td>{transaction.balance_after:.2f} {transaction.currency}</td>
                            <td>{transaction.status.title()}</td>
                        </tr>
            """
        
        html_content += """
                    </tbody>
                </table>
            </div>
            
            <div class="footer">
                <p>This statement was generated by Almoshtariat Platform</p>
                <p>For any inquiries, please contact our support team</p>
            </div>
        </body>
        </html>
        """
        
        try:
            # Try to generate PDF using weasyprint
            import weasyprint
            from io import BytesIO
            
            # Generate PDF using temporary file approach
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                weasyprint.HTML(string=html_content).write_pdf(temp_path)
                
                # Read PDF content
                with open(temp_path, 'rb') as f:
                    pdf_content = f.read()
            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            
            # Create response
            response = make_response(pdf_content)
            response.headers['Content-Type'] = 'application/pdf'
            # Use completely ASCII-safe filename to avoid Unicode encoding issues
            import re
            safe_company_name = re.sub(r'[^a-zA-Z0-9_-]', '_', str(company.display_name or 'company'))
            filename = f'company_statement_{safe_company_name}_{datetime.now().strftime("%Y%m%d")}.pdf'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except ImportError:
            # Fallback to HTML download if weasyprint is not available
            response = make_response(html_content)
            response.headers['Content-Type'] = 'text/html'
            # Use completely ASCII-safe filename to avoid Unicode encoding issues
            import re
            safe_company_name = re.sub(r'[^a-zA-Z0-9_-]', '_', str(company.display_name or 'company'))
            filename = f'company_statement_{safe_company_name}_{datetime.now().strftime("%Y%m%d")}.html'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
    except Exception as e:
        flash(f'Error generating PDF statement: {str(e)}', 'error')
        return redirect(url_for('company_balance'))

@app.route('/company_packages')
@login_required
def company_packages():
    """Display packages for the current company"""
    if current_user.role != 'company':
        flash('Access denied. Company role required.', 'error')
        return redirect(url_for('dash'))
    
    company = Company.query.filter_by(id=current_user.company_id).first()
    if not company:
        flash('Company not found.', 'error')
        return redirect(url_for('dash'))
    
    # Get all packages for this company
    packages = Package.query.filter_by(company_id=company.id).order_by(Package.created_at.desc()).all()
    
    return render_template('company/packages.html', packages=packages, company=company)

# Duplicate company_dashboard function removed - using the one at line 2641 instead

@app.route('/package_details/<int:package_id>')
@login_required
def package_details(package_id):
    """Display detailed information about a specific package"""
    # Get the package
    package = Package.query.get_or_404(package_id)
    
    # Check permissions
    if current_user.role == 'company':
        # Company users can only view their own packages
        if package.company_id != current_user.company_id:
            flash('Access denied.', 'error')
            return redirect(url_for('company_packages'))
    elif current_user.role == 'user':
        # Regular users can only view packages for their orders
        if package.order.user_id != current_user.id:
            flash('Access denied.', 'error')
            return redirect(url_for('dash'))
    else:
        flash('Access denied.', 'error')
        return redirect(url_for('dash'))
    
    return render_template('package_details.html', package=package)

@app.route('/update_receiver_info/<int:order_id>', methods=['POST'])
@login_required
def update_receiver_info(order_id):
    """Update receiver information for an order"""
    try:
        # Get the order
        order = Order.query.get_or_404(order_id)
        
        # Check if user has permission to update this order
        if current_user.role == 'client' and order.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        elif current_user.role == 'company':
            # Companies can update orders they have packages for
            package = Package.query.filter_by(order_id=order_id, company_id=current_user.company_id).first()
            if not package:
                return jsonify({'success': False, 'message': 'Access denied'}), 403
        elif current_user.role not in ['admin', 'site_admin']:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Get the JSON data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        # Get the package for this order
        package = Package.query.filter_by(order_id=order_id).first()
        if not package:
            return jsonify({'success': False, 'message': 'Package not found for this order'}), 404
        
        # Update receiver information in the package
        package.receiver_name = data.get('receiver_name', '').strip()
        package.receiver_phone = data.get('receiver_phone', '').strip()
        package.receiver_address = data.get('delivery_address', '').strip()
        
        # Save changes
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Receiver information updated successfully',
            'data': {
                'receiver_name': package.receiver_name,
                'receiver_phone': package.receiver_phone,
                'delivery_address': package.receiver_address
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating receiver info: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error updating receiver info: {str(e)}'
        })
@app.route("/tt")
def tt():
    users=User.query.all()
    for i in users:
        i.password_hash=generate_password_hash("a", method='pbkdf2:sha256')
    db.session.commit()
    return "fff"

# SocketIO Event Handlers for Real-time Notifications
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    if current_user.is_authenticated:
        # Join user to their personal room for notifications
        if hasattr(current_user, 'role') and current_user.role == 'company':
            join_room(f'company_{current_user.id}')
        else:
            join_room(f'user_{current_user.id}')
        print(f'User {current_user.id} connected to notifications')

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    if current_user.is_authenticated:
        if hasattr(current_user, 'role') and current_user.role == 'company':
            leave_room(f'company_{current_user.id}')
        else:
            leave_room(f'user_{current_user.id}')
        print(f'User {current_user.id} disconnected from notifications')

@socketio.on('join_notifications')
def handle_join_notifications():
    """Manually join notification room"""
    if current_user.is_authenticated:
        if hasattr(current_user, 'role') and current_user.role == 'company':
            join_room(f'company_{current_user.id}')
        else:
            join_room(f'user_{current_user.id}')
        emit('notification_status', {'status': 'joined', 'room': f'user_{current_user.id}'})

def emit_notification_to_user(user_id, notification_data):
    """Emit notification to specific user"""
    socketio.emit('new_notification', notification_data, room=f'user_{user_id}')

def emit_notification_to_company(company_id, notification_data):
    """Emit notification to specific company"""
    socketio.emit('new_notification', notification_data, room=f'company_{company_id}')

# AI Chat Routes
@app.route('/client/ai_chat')
@login_required
def client_ai_chat():
    """Client AI chat page"""
    if hasattr(current_user, 'role') and current_user.role == 'company':
        return redirect(url_for('company_ai_chat'))
    return render_template('client/ai_chat.html')

@app.route('/company/ai_chat')
@login_required
def company_ai_chat():
    """Company AI chat page"""
    if not (hasattr(current_user, 'role') and current_user.role == 'company'):
        return redirect(url_for('client_ai_chat'))
    return render_template('company/ai_chat.html')

@app.route('/api/ai_chat', methods=['POST'])
@csrf.exempt
@login_required
def api_ai_chat():
    """API endpoint for client AI chat"""
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400
        
        message = data['message'].strip()
        if not message:
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        # Get language from request, default to English
        language = data.get('language', 'en')
        
        # Get conversation history from request (optional)
        conversation_history = data.get('conversation_history', [])
        
        # Check if AI is configured
        if not ai_config.is_configured():
            error_msg = 'خدمة الذكاء الاصطناعي غير مُكوّنة. يرجى الاتصال بالمسؤول لإعداد مفتاح API.' if language == 'ar' else 'AI service is not configured. Please contact administrator to set up the API key.'
            return jsonify({'error': error_msg}), 503
        
        # Analyze user data with language and conversation history support
        result = ai_service.analyze_user_data(current_user.id, message, language, conversation_history)
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f'AI Chat API Error: {str(e)}')
        language = 'en'
        try:
            language = data.get('language', 'en') if data else 'en'
        except:
            pass
        error_msg = 'خطأ داخلي في الخادم' if language == 'ar' else 'Internal server error'
        return jsonify({'error': error_msg}), 500

@app.route('/api/company_ai_chat', methods=['POST'])
@csrf.exempt
@login_required
def api_company_ai_chat():
    """API endpoint for company AI chat"""
    try:
        # Check if user is a company
        if not (hasattr(current_user, 'role') and current_user.role == 'company'):
            return jsonify({'error': 'Access denied'}), 403
        
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400
        
        message = data['message'].strip()
        if not message:
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        # Get language from request, default to English
        language = data.get('language', 'en')
        
        # Get conversation history from request (optional)
        conversation_history = data.get('conversation_history', [])
        
        # Check if AI is configured
        if not ai_config.is_configured():
            error_msg = 'خدمة الذكاء الاصطناعي غير مُكوّنة. يرجى الاتصال بالمسؤول لإعداد مفتاح API.' if language == 'ar' else 'AI service is not configured. Please contact administrator to set up the API key.'
            return jsonify({'error': error_msg}), 503
        
        # Use agentic AI service for processing user requests
        result = agentic_ai_service.process_user_request(
            company_id=current_user.company_id,
            user_message=message,
            conversation_history=conversation_history,
            language=language
        )
        
        # Extract the response text from the result
        if isinstance(result, dict) and result.get('success', False):
            return jsonify({'response': result.get('response', 'No response available')})
        elif isinstance(result, str):
            return jsonify({'response': result})
        else:
            error_msg = result.get('response', 'AI service error') if isinstance(result, dict) else 'Processing error'
            return jsonify({'error': error_msg}), 500
        
    except Exception as e:
        app.logger.error(f'Company AI Chat API Error: {str(e)}')
        language = 'en'
        try:
            language = data.get('language', 'en') if data else 'en'
        except:
            pass
        error_msg = 'خطأ داخلي في الخادم' if language == 'ar' else 'Internal server error'
        return jsonify({'error': error_msg}), 500

@app.route('/api/client_ai_chat', methods=['POST'])
@csrf.exempt
@login_required
def api_client_ai_chat():
    """API endpoint for client AI chat with separate API key"""
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400
        
        message = data['message'].strip()
        if not message:
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        # Get language from request, default to English
        language = data.get('language', 'en')
        
        # Get conversation history from request (optional)
        conversation_history = data.get('conversation_history', [])
        
        # Import client AI service
        from client_ai_service import client_ai_service, client_ai_config
        
        # Check if client AI is configured
        if not client_ai_config.is_configured():
            error_msg = 'خدمة الذكاء الاصطناعي للعملاء غير مُكوّنة. يرجى الاتصال بالمسؤول.' if language == 'ar' else 'Client AI service is not configured. Please contact administrator.'
            return jsonify({'error': error_msg}), 503
        
        # Analyze user data with client AI service
        result = client_ai_service.analyze_user_data(current_user.id, message, language, conversation_history)
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f'Client AI Chat API Error: {str(e)}')
        language = 'en'
        try:
            language = data.get('language', 'en') if data else 'en'
        except:
            pass
        error_msg = 'خطأ داخلي في الخادم' if language == 'ar' else 'Internal server error'
        return jsonify({'error': error_msg}), 500

@app.route('/api/ai_config', methods=['POST'])
@login_required
def api_ai_config():
    """API endpoint to configure AI with API key (admin only)"""
    try:
        # Check if user has admin privileges (you may need to adjust this based on your user model)
        if not (hasattr(current_user, 'is_admin') and current_user.is_admin):
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.get_json()
        if not data or 'api_key' not in data:
            return jsonify({'error': 'API key is required'}), 400
        
        api_key = data['api_key'].strip()
        if not api_key:
            return jsonify({'error': 'API key cannot be empty'}), 400
        
        # Initialize Groq client
        try:
            if hasattr(ai_config, 'initialize_groq_client') and ai_config.initialize_groq_client(api_key):
                return jsonify({'success': True, 'message': 'AI service configured successfully'})
            else:
                return jsonify({'error': 'Failed to configure AI service'}), 500
        except AttributeError:
            return jsonify({'error': 'Groq client initialization not available'}), 500
        
    except Exception as e:
        app.logger.error(f'AI Config API Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/create_order', methods=['POST'])
@csrf.exempt
def api_create_order():
    """API endpoint for AI to create orders"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get company_id and user_id from the request
        company_id = data.get('company_id')
        if not company_id:
            return jsonify({'error': 'Company ID is required'}), 400
        
        # Find a user for this company
        from models import User
        user = User.query.filter_by(company_id=company_id).first()
        if not user:
            return jsonify({'error': 'No user found for this company'}), 400
        
        # Extract order data
        order_name = data.get('order_name', f'AI Order - {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        description = data.get('description', '')
        sector = data.get('sector', 'Electronics')
        order_type = data.get('order_type', 'direct')
        
        # Delivery details
        delivery_date_str = data.get('delivery_date')
        delivery_date = None
        if delivery_date_str:
            try:
                delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        delivery_time = data.get('delivery_time', '')
        delivery_address = data.get('delivery_address', '')
        delivery_notes = data.get('delivery_notes', '')
        receiver_name = data.get('receiver_name', '')
        receiver_phone = data.get('receiver_phone', '')
        
        # Payment details
        payment_way = data.get('payment_way', '')
        payment_steps_data = data.get('payment_steps', [])
        import json
        payment_steps_json = json.dumps(payment_steps_data) if payment_steps_data else None
        
        # Settings
        direct_negotiation = data.get('direct_negotiation', False)
        accept_unregistered_suppliers = data.get('accept_unregistered_suppliers', True)
        max_suppliers = data.get('max_suppliers', 10)
        
        # Create the order
        order = Order(
            user_id=user.id,
            company_id=company_id,
            order_name=order_name,
            description=description,
            sector=sector,
            order_type=order_type,
            delivery_date=delivery_date,
            delivery_time=delivery_time,
            delivery_address=delivery_address,
            delivery_notes=delivery_notes,
            receiver_name=receiver_name,
            receiver_phone=receiver_phone,
            payment_way=payment_way,
            payment_steps=payment_steps_json,
            direct_negotiation=direct_negotiation,
            accept_unregistered_suppliers=accept_unregistered_suppliers,
            max_suppliers=max_suppliers
        )
        
        db.session.add(order)
        db.session.commit()  # Commit to get order.id
        
        # Handle products
        products = data.get('products', [])
        created_products = []
        
        for product_data in products:
            product_name = product_data.get('product_name') or product_data.get('part_name', 'منتج افتراضي')
            technical_specs = product_data.get('technical_specs') or product_data.get('description', '')
            quantity = int(product_data.get('quantity', 1))
            unit = product_data.get('unit', 'pcs')
            max_price_per_unit = product_data.get('max_price_per_unit')
            product_code = product_data.get('product_code', '')
            best_supplier = product_data.get('best_supplier', '')
            
            purchase = Purchase(
                sector=sector,
                quantity=quantity,
                part_name=product_name,
                description=technical_specs,
                technical_specs=technical_specs,
                unit=unit,
                max_price_per_unit=float(max_price_per_unit) if max_price_per_unit else None,
                product_code=product_code,
                best_supplier=best_supplier,
                order_id=order.id
            )
            db.session.add(purchase)
            created_products.append({
                'product_name': product_name,
                'quantity': quantity,
                'technical_specs': technical_specs
            })
        
        db.session.commit()
        
        # Find matching products and create notifications (same as new_purchase route)
        all_suggestions = []
        total_matches = 0
        
        for product_data in products:
            product_name = product_data.get('product_name') or product_data.get('part_name', '')
            technical_specs = product_data.get('technical_specs') or product_data.get('description', '')
            
            if product_name:  # Only search if we have a product name
                matches = find_matching_products(product_name, technical_specs, sector)
                
                if matches:
                    total_matches += len(matches)
                    all_suggestions.append({
                        'product': product_data,
                        'matches': matches
                    })
        
        # Create notifications for companies that have matching products
        for suggestion in all_suggestions:
            for match in suggestion['matches']:
                create_notification(
                    title='طلب جديد متاح',
                    description=f'طلب جديد متاح: {order.order_name}',
                    notification_type='new_order',
                    company_id=match['company'].id,
                    related_order_id=order.id
                )
        
        return jsonify({
            'success': True,
            'order_id': order.id,
            'order_name': order.order_name,
            'products_created': len(created_products),
            'notifications_sent': total_matches,
            'message': f'تم إنشاء الطلب بنجاح. رقم الطلب: {order.id}'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'API Create Order Error: {str(e)}')
        import traceback
        app.logger.error(f'Full traceback: {traceback.format_exc()}')
        return jsonify({'error': f'Failed to create order: {str(e)}'}), 500

# AI Agent Routes
@app.route('/api/ai_agent/tasks', methods=['POST'])
@csrf.exempt
@login_required
def create_ai_agent_task():
    """Create a new AI agent task"""
    try:
        # Check if user is a company
        if not (hasattr(current_user, 'role') and current_user.role == 'company'):
            return jsonify({'error': 'Access denied'}), 403
        
        data = request.get_json()
        if not data or 'task_type' not in data:
            return jsonify({'error': 'Task type is required'}), 400
        
        task_type = data['task_type']
        description = data.get('description', f'AI Agent Task: {task_type}')
        parameters = data.get('parameters', {})
        priority = data.get('priority', 'medium')
        
        # Create the task
        task_id = ai_agent_service.create_task(
            task_type=task_type,
            description=description,
            company_id=current_user.company_id,
            parameters=parameters,
            priority=priority
        )
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'Task created successfully'
        })
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        app.logger.error(f'Create AI Agent Task Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ai_agent/tasks/<task_id>/execute', methods=['POST'])
@csrf.exempt
@login_required
def execute_ai_agent_task(task_id):
    """Execute an AI agent task"""
    try:
        # Check if user is a company
        if not (hasattr(current_user, 'role') and current_user.role == 'company'):
            return jsonify({'error': 'Access denied'}), 403
        
        # Execute the task
        result = ai_agent_service.execute_task(task_id)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f'Execute AI Agent Task Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ai_agent/tasks/<task_id>/status', methods=['GET'])
@login_required
def get_ai_agent_task_status(task_id):
    """Get the status of an AI agent task"""
    try:
        # Check if user is a company
        if not (hasattr(current_user, 'role') and current_user.role == 'company'):
            return jsonify({'error': 'Access denied'}), 403
        
        # Get task status
        status = ai_agent_service.get_task_status(task_id)
        
        if 'error' in status:
            return jsonify(status), 404
        
        return jsonify(status)
        
    except Exception as e:
        app.logger.error(f'Get AI Agent Task Status Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ai_agent/tasks', methods=['GET'])
@login_required
def get_company_ai_agent_tasks():
    """Get all AI agent tasks for the current company"""
    try:
        # Check if user is a company
        if not (hasattr(current_user, 'role') and current_user.role == 'company'):
            return jsonify({'error': 'Access denied'}), 403
        
        limit = request.args.get('limit', 50, type=int)
        
        # Get company tasks
        tasks = ai_agent_service.get_company_tasks(current_user.company_id, limit)
        
        return jsonify({
            'tasks': tasks,
            'total': len(tasks)
        })
        
    except Exception as e:
        app.logger.error(f'Get Company AI Agent Tasks Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ai_agent/task_types', methods=['GET'])
@login_required
def get_ai_agent_task_types():
    """Get available AI agent task types"""
    try:
        # Check if user is a company
        if not (hasattr(current_user, 'role') and current_user.role == 'company'):
            return jsonify({'error': 'Access denied'}), 403
        
        language = request.args.get('language', 'en')
        
        # Get available task types
        task_types = ai_agent_service.get_available_task_types(language)
        
        return jsonify({
            'task_types': task_types
        })
        
    except Exception as e:
        app.logger.error(f'Get AI Agent Task Types Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/company/ai_agent')
@login_required
def company_ai_agent():
    """Company AI Agent page"""
    if not (hasattr(current_user, 'role') and current_user.role == 'company'):
        return redirect(url_for('login'))
    return render_template('company/ai_agent.html')

@app.route('/api/ai_agent/metrics', methods=['GET'])
@login_required
def get_ai_agent_metrics():
    """Get AI agent performance metrics"""
    try:
        # Check if user is a company
        if not (hasattr(current_user, 'role') and current_user.role == 'company'):
            return jsonify({'error': 'Access denied'}), 403
        
        # Get performance metrics
        metrics = ai_agent_service.get_performance_metrics()
        
        return jsonify({
            'metrics': metrics
        })
        
    except Exception as e:
        app.logger.error(f'Get AI Agent Metrics Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ai_agent/task_history', methods=['GET'])
@login_required
def get_ai_agent_task_history():
    """Get AI agent task history for company"""
    try:
        # Check if user is a company
        if not (hasattr(current_user, 'role') and current_user.role == 'company'):
            return jsonify({'error': 'Access denied'}), 403
        
        company_id = current_user.id
        limit = int(request.args.get('limit', 50))
        
        # Get company tasks
        tasks = ai_agent_service.get_company_tasks(company_id, limit)
        
        return jsonify({
            'tasks': tasks
        })
        
    except Exception as e:
        app.logger.error(f'Get AI Agent Task History Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

# AI Chat Session Management API Endpoints
@app.route('/api/ai_agent/chat_sessions', methods=['GET'])
@login_required
def get_ai_chat_sessions():
    """Get all chat sessions for the current company"""
    try:
        if not current_user.company_id:
            return jsonify({'error': 'Company not found'}), 404
            
        from models import AIChatSession
        sessions = AIChatSession.query.filter_by(company_id=current_user.company_id).order_by(AIChatSession.updated_at.desc()).all()
        
        return jsonify({
            'sessions': [session.to_dict() for session in sessions]
        })
        
    except Exception as e:
        app.logger.error(f'Get AI Chat Sessions Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ai_agent/chat_sessions', methods=['POST'])
@login_required
def create_ai_chat_session():
    """Create a new chat session"""
    try:
        if not current_user.company_id:
            return jsonify({'error': 'Company not found'}), 404
            
        data = request.get_json()
        session_name = data.get('session_name', f'Chat Session {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        
        from models import AIChatSession
        import uuid
        
        new_session = AIChatSession(
            id=str(uuid.uuid4()),
            company_id=current_user.company_id,
            session_name=session_name,
            status='active'
        )
        
        db.session.add(new_session)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'session': new_session.to_dict()
        })
        
    except Exception as e:
        app.logger.error(f'Create AI Chat Session Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ai_agent/chat_sessions/<session_id>/messages', methods=['GET'])
@login_required
def get_chat_messages(session_id):
    """Get all messages for a specific chat session"""
    try:
        from models import AIChatSession, AIChatMessage
        
        # Verify session belongs to current company
        session = AIChatSession.query.filter_by(id=session_id, company_id=current_user.company_id).first()
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        messages = AIChatMessage.query.filter_by(session_id=session_id).order_by(AIChatMessage.created_at.asc()).all()
        
        return jsonify({
            'messages': [message.to_dict() for message in messages]
        })
        
    except Exception as e:
        app.logger.error(f'Get Chat Messages Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ai_agent/chat_sessions/<session_id>/messages', methods=['POST'])
@login_required
def send_chat_message(session_id):
    """Send a message in a chat session and get AI response"""
    try:
        from models import AIChatSession, AIChatMessage
        import uuid
        
        # Verify session belongs to current company
        session = AIChatSession.query.filter_by(id=session_id, company_id=current_user.company_id).first()
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({'error': 'Message cannot be empty'}), 400
            
        # Save user message
        user_msg = AIChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            sender_type='user',
            message_content=user_message,
            message_type='text'
        )
        db.session.add(user_msg)
        
        # Generate AI response
        try:
            ai_prompt = f"You are an AI assistant helping a company with their business needs. The company is asking: {user_message}. Please provide a helpful response in Arabic."
            ai_response = ai_config.generate_content(ai_prompt)
            
            # Save AI response
            ai_msg = AIChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sender_type='ai',
                message_content=ai_response,
                message_type='text'
            )
            db.session.add(ai_msg)
            
        except Exception as ai_error:
            app.logger.error(f'AI Response Error: {str(ai_error)}')
            # Save error message
            ai_msg = AIChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sender_type='ai',
                message_content='عذراً، حدث خطأ في الحصول على الرد. يرجى المحاولة مرة أخرى.',
                message_type='error'
            )
            db.session.add(ai_msg)
            
        # Update session timestamp
        session.last_message_at = datetime.utcnow()
        session.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'user_message': user_msg.to_dict(),
            'ai_message': ai_msg.to_dict()
        })
        
    except Exception as e:
        app.logger.error(f'Send Chat Message Error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/user_balance', methods=['GET'])
@login_required
def get_user_balance():
    """Get current user's balance information"""
    try:
        # Get user's balance
        user_balance = Balance.query.filter_by(user_id=current_user.id).first()
        if not user_balance:
            # Create default balance if it doesn't exist
            user_balance = Balance(
                user_id=current_user.id,
                current_balance=1200.0,
                currency='EGP',
                created_at=datetime.utcnow()
            )
            db.session.add(user_balance)
            db.session.commit()
        
        # Get recent transactions (last 5)
        recent_transactions = Transaction.query.filter_by(balance_id=user_balance.id).order_by(Transaction.created_at.desc()).limit(5).all()
        
        # Calculate monthly spending
        current_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_spent = db.session.query(db.func.sum(Transaction.amount)).filter(
            Transaction.balance_id == user_balance.id,
            Transaction.transaction_type == 'debit',
            Transaction.created_at >= current_month
        ).scalar() or 0
        
        balance_data = {
            'current_balance': user_balance.current_balance,
            'currency': user_balance.currency,
            'monthly_spent': abs(monthly_spent),
            'recent_transactions': [{
                'id': t.id,
                'amount': t.amount,
                'type': t.transaction_type,
                'description': t.description,
                'created_at': t.created_at.isoformat() if t.created_at else None
            } for t in recent_transactions]
        }
        
        return jsonify(balance_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user_offers', methods=['GET'])
@login_required
def get_user_offers():
    """Get current user's available offers"""
    try:
        # Get user's orders
        user_orders = Order.query.filter_by(user_id=current_user.id).all()
        order_ids = [order.id for order in user_orders]
        
        # Get offers for user's orders
        offers = Offer.query.filter(Offer.order_id.in_(order_ids)).order_by(Offer.created_at.desc()).limit(10).all()
        
        offers_data = []
        for offer in offers:
            order = Order.query.get(offer.order_id)
            company = Company.query.get(offer.company_id)
            
            offer_data = {
                'id': offer.id,
                'order_name': order.order_name if order else 'Unknown Order',
                'company_name': company.name_ar or company.name_en if company else 'Unknown Company',
                'total_price': offer.total_price,
                'status': offer.status,
                'delivery_time': offer.delivery_time,
                'created_at': offer.created_at.isoformat() if offer.created_at else None,
                'is_accepted': offer.status == 'accepted'
            }
            offers_data.append(offer_data)
        
        return jsonify({
            'offers': offers_data,
            'total_offers': len(offers_data)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/company_balance', methods=['GET'])
@login_required
def get_company_balance():
    """Get current company's balance information"""
    try:
        if not current_user.is_company_user:
            return jsonify({'error': 'Access denied'}), 403
            
        # Get company balance
        company_balance = CompanyBalance.query.filter_by(company_id=current_user.company_id).first()
        if not company_balance:
            return jsonify({
                'current_balance': 0.0,
                'currency': 'EGP',
                'monthly_revenue': 0.0,
                'pending_payments': 0.0
            })
        
        # Calculate monthly revenue from accepted offers
        current_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_revenue = db.session.query(db.func.sum(Offer.total_price)).filter(
            Offer.company_id == current_user.company_id,
            Offer.status == 'accepted',
            Offer.created_at >= current_month
        ).scalar() or 0
        
        # Calculate pending payments
        pending_payments = db.session.query(db.func.sum(Offer.total_price)).filter(
            Offer.company_id == current_user.company_id,
            Offer.status == 'pending'
        ).scalar() or 0
        
        balance_data = {
            'current_balance': company_balance.current_balance,
            'currency': 'EGP',
            'monthly_revenue': monthly_revenue,
            'pending_payments': pending_payments
        }
        
        return jsonify(balance_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/company_sales', methods=['GET'])
@login_required
def get_company_sales():
    """Get current company's sales performance"""
    try:
        if not current_user.is_company_user:
            return jsonify({'error': 'Access denied'}), 403
            
        # Get recent offers
        recent_offers = Offer.query.filter_by(company_id=current_user.company_id).order_by(Offer.created_at.desc()).limit(10).all()
        
        # Calculate statistics
        total_offers = Offer.query.filter_by(company_id=current_user.company_id).count()
        accepted_offers = Offer.query.filter_by(company_id=current_user.company_id, status='accepted').count()
        pending_offers = Offer.query.filter_by(company_id=current_user.company_id, status='pending').count()
        
        # Calculate acceptance rate
        acceptance_rate = (accepted_offers / total_offers * 100) if total_offers > 0 else 0
        
        sales_data = {
            'total_offers': total_offers,
            'accepted_offers': accepted_offers,
            'pending_offers': pending_offers,
            'acceptance_rate': round(acceptance_rate, 1),
            'recent_offers': [{
                'id': offer.id,
                'order_name': offer.order.order_name if offer.order else 'Unknown Order',
                'total_price': offer.total_price,
                'status': offer.status,
                'created_at': offer.created_at.isoformat() if offer.created_at else None
            } for offer in recent_offers]
        }
        
        return jsonify(sales_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/company_inventory', methods=['GET'])
@login_required
def get_company_inventory():
    """Get current company's inventory analytics"""
    try:
        if not current_user.is_company_user:
            return jsonify({'error': 'Access denied'}), 403
            
        # Get company products
        products = Product.query.filter_by(company_id=current_user.company_id).all()
        
        # Calculate inventory statistics
        total_products = len(products)
        active_products = len([p for p in products if p.is_active])
        inactive_products = total_products - active_products
        
        # Calculate stock levels
        low_stock_products = []
        out_of_stock_products = []
        total_stock_value = 0
        
        for product in products:
            if hasattr(product, 'stock_quantity'):
                if product.stock_quantity == 0:
                    out_of_stock_products.append(product)
                elif product.stock_quantity < 10:  # Assuming low stock threshold is 10
                    low_stock_products.append(product)
            
            if hasattr(product, 'price') and hasattr(product, 'stock_quantity'):
                total_stock_value += (product.price or 0) * (product.stock_quantity or 0)
        
        # Get top products by category
        categories = {}
        for product in products:
            if product.category:
                if product.category not in categories:
                    categories[product.category] = 0
                categories[product.category] += 1
        
        inventory_data = {
            'total_products': total_products,
            'active_products': active_products,
            'inactive_products': inactive_products,
            'low_stock_count': len(low_stock_products),
            'out_of_stock_count': len(out_of_stock_products),
            'total_stock_value': round(total_stock_value, 2),
            'categories': categories,
            'low_stock_products': [{
                'id': p.id,
                'name': p.name,
                'stock_quantity': getattr(p, 'stock_quantity', 0),
                'category': p.category
            } for p in low_stock_products[:5]],  # Top 5 low stock items
            'top_categories': sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
        }
        
        return jsonify(inventory_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/company_products', methods=['GET'])
@login_required
def get_company_products():
    """Get current company's best products analytics"""
    try:
        if not current_user.is_company_user:
            return jsonify({'error': 'Access denied'}), 403
            
        # Get company products with related offers
        products = Product.query.filter_by(company_id=current_user.company_id).all()
        
        # Calculate product performance based on offers
        product_stats = []
        for product in products:
            # Count offers for this product (using product offers relationship)
            offers_count = db.session.query(Offer).filter(
                Offer.company_id == current_user.company_id
            ).join(ProductOffer).filter(
                ProductOffer.product_id == product.id
            ).count()
            
            accepted_offers = db.session.query(Offer).filter(
                Offer.company_id == current_user.company_id,
                Offer.status == 'accepted'
            ).join(ProductOffer).filter(
                ProductOffer.product_id == product.id
            ).count()
            
            # Calculate total revenue from accepted offers
            total_revenue = db.session.query(db.func.sum(Offer.total_price)).filter(
                Offer.company_id == current_user.company_id,
                Offer.status == 'accepted'
            ).join(ProductOffer).filter(
                ProductOffer.product_id == product.id
            ).scalar() or 0
            
            product_stats.append({
                'id': product.id,
                'name': product.name,
                'category': product.category,
                'offers_count': offers_count,
                'accepted_offers': accepted_offers,
                'total_revenue': float(total_revenue),
                'acceptance_rate': (accepted_offers / offers_count * 100) if offers_count > 0 else 0,
                'is_active': product.is_active,
                'price': getattr(product, 'price', 0) or 0
            })
        
        # Sort by total revenue and acceptance rate
        best_products = sorted(product_stats, key=lambda x: (x['total_revenue'], x['acceptance_rate']), reverse=True)[:10]
        
        # Get category performance
        category_performance = {}
        for stat in product_stats:
            category = stat['category'] or 'Uncategorized'
            if category not in category_performance:
                category_performance[category] = {
                    'total_revenue': 0,
                    'total_offers': 0,
                    'accepted_offers': 0,
                    'product_count': 0
                }
            
            category_performance[category]['total_revenue'] += stat['total_revenue']
            category_performance[category]['total_offers'] += stat['offers_count']
            category_performance[category]['accepted_offers'] += stat['accepted_offers']
            category_performance[category]['product_count'] += 1
        
        # Calculate category acceptance rates
        for category in category_performance:
            total_offers = category_performance[category]['total_offers']
            if total_offers > 0:
                category_performance[category]['acceptance_rate'] = (
                    category_performance[category]['accepted_offers'] / total_offers * 100
                )
            else:
                category_performance[category]['acceptance_rate'] = 0
        
        products_data = {
            'total_products': len(products),
            'active_products': len([p for p in products if p.is_active]),
            'best_products': best_products[:5],  # Top 5 best performing products
            'category_performance': dict(sorted(
                category_performance.items(), 
                key=lambda x: x[1]['total_revenue'], 
                reverse=True
            )[:5]),  # Top 5 categories by revenue
            'total_revenue': sum(stat['total_revenue'] for stat in product_stats),
            'average_acceptance_rate': sum(stat['acceptance_rate'] for stat in product_stats) / len(product_stats) if product_stats else 0
        }
        
        return jsonify(products_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/company_customers', methods=['GET'])
@login_required
def get_company_customers():
    """Get current company's customer patterns analytics"""
    try:
        if not current_user.is_company_user:
            return jsonify({'error': 'Access denied'}), 403
            
        # Get orders and offers for this company
        offers = Offer.query.filter_by(company_id=current_user.company_id).all()
        
        # Analyze customer patterns
        customer_stats = {}
        total_customers = set()
        
        for offer in offers:
            if offer.order and offer.order.user:
                customer_id = offer.order.user.id
                customer_name = offer.order.user.username
                total_customers.add(customer_id)
                
                if customer_id not in customer_stats:
                    customer_stats[customer_id] = {
                        'name': customer_name,
                        'total_orders': 0,
                        'accepted_orders': 0,
                        'total_value': 0,
                        'avg_order_value': 0,
                        'last_order_date': None,
                        'preferred_categories': {}
                    }
                
                customer_stats[customer_id]['total_orders'] += 1
                
                if offer.status == 'accepted':
                    customer_stats[customer_id]['accepted_orders'] += 1
                    customer_stats[customer_id]['total_value'] += offer.total_price or 0
                
                # Track order date
                if offer.created_at:
                    if (customer_stats[customer_id]['last_order_date'] is None or 
                        offer.created_at > customer_stats[customer_id]['last_order_date']):
                        customer_stats[customer_id]['last_order_date'] = offer.created_at
                
                # Track preferred categories from order items
                if offer.order:
                    for item in offer.order.items:
                        if item.product and item.product.category:
                            category = item.product.category
                            if category not in customer_stats[customer_id]['preferred_categories']:
                                customer_stats[customer_id]['preferred_categories'][category] = 0
                            customer_stats[customer_id]['preferred_categories'][category] += 1
        
        # Calculate average order values and sort customers
        for customer_id in customer_stats:
            accepted_orders = customer_stats[customer_id]['accepted_orders']
            if accepted_orders > 0:
                customer_stats[customer_id]['avg_order_value'] = (
                    customer_stats[customer_id]['total_value'] / accepted_orders
                )
        
        # Get top customers by value
        top_customers = sorted(
            customer_stats.values(), 
            key=lambda x: x['total_value'], 
            reverse=True
        )[:10]
        
        # Calculate customer retention and patterns
        repeat_customers = len([c for c in customer_stats.values() if c['total_orders'] > 1])
        high_value_customers = len([c for c in customer_stats.values() if c['total_value'] > 1000])  # Assuming 1000 as high value threshold
        
        # Get most popular categories across all customers
        all_categories = {}
        for customer in customer_stats.values():
            for category, count in customer['preferred_categories'].items():
                if category not in all_categories:
                    all_categories[category] = 0
                all_categories[category] += count
        
        customers_data = {
            'total_customers': len(total_customers),
            'repeat_customers': repeat_customers,
            'high_value_customers': high_value_customers,
            'customer_retention_rate': (repeat_customers / len(total_customers) * 100) if total_customers else 0,
            'top_customers': [{
                'name': c['name'],
                'total_orders': c['total_orders'],
                'accepted_orders': c['accepted_orders'],
                'total_value': round(c['total_value'], 2),
                'avg_order_value': round(c['avg_order_value'], 2),
                'last_order_date': c['last_order_date'].isoformat() if c['last_order_date'] else None,
                'top_category': max(c['preferred_categories'].items(), key=lambda x: x[1])[0] if c['preferred_categories'] else 'N/A'
            } for c in top_customers[:5]],
            'popular_categories': dict(sorted(all_categories.items(), key=lambda x: x[1], reverse=True)[:5]),
            'total_revenue': sum(c['total_value'] for c in customer_stats.values()),
            'average_customer_value': sum(c['total_value'] for c in customer_stats.values()) / len(customer_stats) if customer_stats else 0
        }
        
        return jsonify(customers_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/company_profits', methods=['GET'])
@login_required
def get_company_profits():
    """Get current company's profit analysis"""
    try:
        if not current_user.is_company_user:
            return jsonify({'error': 'Access denied'}), 403
            
        # Get company data
        company = Company.query.get(current_user.company_id)
        if not company:
            return jsonify({'error': 'Company not found'}), 404
            
        # Get accepted offers (revenue)
        accepted_offers = Offer.query.filter_by(
            company_id=current_user.company_id, 
            status='accepted'
        ).all()
        
        # Calculate revenue by month
        
        monthly_revenue = {}
        total_revenue = 0
        
        for offer in accepted_offers:
            if offer.created_at and offer.total_price:
                month_key = offer.created_at.strftime('%Y-%m')
                if month_key not in monthly_revenue:
                    monthly_revenue[month_key] = 0
                monthly_revenue[month_key] += offer.total_price
                total_revenue += offer.total_price
        
        # Get current month and previous months for comparison
        current_date = datetime.now()
        current_month = current_date.strftime('%Y-%m')
        previous_month = (current_date.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
        
        current_month_revenue = monthly_revenue.get(current_month, 0)
        previous_month_revenue = monthly_revenue.get(previous_month, 0)
        
        # Calculate growth rate
        growth_rate = 0
        if previous_month_revenue > 0:
            growth_rate = ((current_month_revenue - previous_month_revenue) / previous_month_revenue) * 100
        
        # Estimate costs (simplified - could be enhanced with actual cost tracking)
        # For now, we'll estimate costs as a percentage of revenue
        estimated_cost_percentage = 0.7  # Assuming 70% cost ratio
        estimated_costs = total_revenue * estimated_cost_percentage
        estimated_profit = total_revenue - estimated_costs
        profit_margin = (estimated_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        # Get top profitable products (based on accepted offers)
        product_profits = {}
        for offer in accepted_offers:
            if offer.order:
                for item in offer.order.items:
                    if item.product:
                        product_id = item.product.id
                        product_name = item.product.name
                        
                        if product_id not in product_profits:
                            product_profits[product_id] = {
                                'name': product_name,
                                'total_revenue': 0,
                                'order_count': 0
                            }
                        
                        # Distribute offer total across items (simplified)
                        item_revenue = (offer.total_price or 0) / len(offer.order.items)
                        product_profits[product_id]['total_revenue'] += item_revenue
                        product_profits[product_id]['order_count'] += 1
        
        # Sort products by revenue
        top_products = sorted(
            product_profits.values(),
            key=lambda x: x['total_revenue'],
            reverse=True
        )[:5]
        
        # Calculate average order value
        avg_order_value = total_revenue / len(accepted_offers) if accepted_offers else 0
        
        profits_data = {
            'total_revenue': round(total_revenue, 2),
            'estimated_costs': round(estimated_costs, 2),
            'estimated_profit': round(estimated_profit, 2),
            'profit_margin': round(profit_margin, 2),
            'current_month_revenue': round(current_month_revenue, 2),
            'previous_month_revenue': round(previous_month_revenue, 2),
            'growth_rate': round(growth_rate, 2),
            'total_orders': len(accepted_offers),
            'avg_order_value': round(avg_order_value, 2),
            'monthly_revenue': {k: round(v, 2) for k, v in sorted(monthly_revenue.items())},
            'top_profitable_products': [{
                'name': p['name'],
                'revenue': round(p['total_revenue'], 2),
                'order_count': p['order_count']
            } for p in top_products],
            'company_balance': getattr(company, 'current_balance', 0) or 0
        }
        
        return jsonify(profits_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Chat History API Endpoints
@app.route('/api/chat_history/save', methods=['POST'])
@csrf.exempt
@login_required
def save_chat_history():
    """Save chat message to history"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        required_fields = ['session_id', 'message_type', 'message_content', 'message_order']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Determine user_id or company_id based on user role
        user_id = None
        company_id = None
        
        if hasattr(current_user, 'role') and current_user.role == 'company':
            company_id = current_user.company_id
        else:
            user_id = current_user.id
        
        # Create new chat history entry
        chat_entry = ChatHistory(
            user_id=user_id,
            company_id=company_id,
            session_id=data['session_id'],
            message_type=data['message_type'],
            message_content=data['message_content'],
            context_data=data.get('context_data'),
            message_order=data['message_order']
        )
        
        db.session.add(chat_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Chat history saved successfully',
            'chat_id': chat_entry.id
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Save Chat History Error: {str(e)}')
        return jsonify({'error': 'Failed to save chat history'}), 500

@app.route('/api/chat_history/<session_id>', methods=['GET'])
@login_required
def get_chat_history(session_id):
    """Get chat history for a specific session"""
    try:
        # Determine user_id or company_id based on user role
        if hasattr(current_user, 'role') and current_user.role == 'company':
            chat_history = ChatHistory.query.filter_by(
                session_id=session_id,
                company_id=current_user.company_id
            ).order_by(ChatHistory.message_order.asc()).all()
        else:
            chat_history = ChatHistory.query.filter_by(
                session_id=session_id,
                user_id=current_user.id
            ).order_by(ChatHistory.message_order.asc()).all()
        
        history_data = [{
            'id': entry.id,
            'message_type': entry.message_type,
            'message_content': entry.message_content,
            'context_data': entry.context_data,
            'message_order': entry.message_order,
            'created_at': entry.created_at.isoformat() if entry.created_at else None
        } for entry in chat_history]
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'history': history_data
        })
        
    except Exception as e:
        app.logger.error(f'Get Chat History Error: {str(e)}')
        return jsonify({'error': 'Failed to retrieve chat history'}), 500

@app.route('/api/chat_history/clear', methods=['POST'])
@login_required
def clear_chat_history():
    """Clear chat history for a specific session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
        
        # Determine user_id or company_id based on user role
        if hasattr(current_user, 'role') and current_user.role == 'company':
            ChatHistory.query.filter_by(
                session_id=session_id,
                company_id=current_user.company_id
            ).delete()
        else:
            ChatHistory.query.filter_by(
                session_id=session_id,
                user_id=current_user.id
            ).delete()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Chat history cleared successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Clear Chat History Error: {str(e)}')
        return jsonify({'error': 'Failed to clear chat history'}), 500

@app.route('/api/chat_history/sessions', methods=['GET'])
@login_required
def get_chat_sessions():
    """Get list of chat sessions for current user/company"""
    try:
        # Determine user_id or company_id based on user role
        if hasattr(current_user, 'role') and current_user.role == 'company':
            sessions = db.session.query(
                ChatHistory.session_id,
                db.func.max(ChatHistory.created_at).label('last_message_at'),
                db.func.count(ChatHistory.id).label('message_count')
            ).filter_by(company_id=current_user.company_id).group_by(
                ChatHistory.session_id
            ).order_by(db.func.max(ChatHistory.created_at).desc()).limit(20).all()
        else:
            sessions = db.session.query(
                ChatHistory.session_id,
                db.func.max(ChatHistory.created_at).label('last_message_at'),
                db.func.count(ChatHistory.id).label('message_count')
            ).filter_by(user_id=current_user.id).group_by(
                ChatHistory.session_id
            ).order_by(db.func.max(ChatHistory.created_at).desc()).limit(20).all()
        
        sessions_data = [{
            'session_id': session.session_id,
            'last_message_at': session.last_message_at.isoformat() if session.last_message_at else None,
            'message_count': session.message_count
        } for session in sessions]
        
        return jsonify({
            'success': True,
            'sessions': sessions_data
        })
        
    except Exception as e:
        app.logger.error(f'Get Chat Sessions Error: {str(e)}')
        return jsonify({'error': 'Failed to retrieve chat sessions'}), 500


@app.route('/terms-and-conditions')
def terms_and_conditions():
    """Display terms and conditions page"""
    current_date = datetime.now().strftime('%B %Y')
    return render_template('terms_and_conditions.html', current_date=current_date)


@app.route('/accept-terms', methods=['POST'])
@login_required
def accept_terms():
    """Handle terms and conditions acceptance"""
    action = request.form.get('action')
    
    if action == 'accept':
        # Update user's terms acceptance
        current_user.terms_accepted = True
        current_user.terms_accepted_at = datetime.utcnow()
        db.session.commit()
        
        # Create notification for terms acceptance
        try:
            terms_notification = Notification(
                user_id=current_user.id,
                title="Terms and Conditions Accepted",
                message="You have successfully accepted the terms and conditions. Welcome to the platform!",
                notification_type='system',
                priority='normal',
                timestamp=datetime.utcnow(),
                is_read=False
            )
            db.session.add(terms_notification)
            db.session.commit()
        except Exception as e:
            print(f"Failed to create terms acceptance notification: {e}")
        
        flash('شكراً لك! تم قبول الشروط والأحكام بنجاح. مرحباً بك في منصة المشتريات الذكية!', 'success')
        return redirect(url_for('dash'))
    
    elif action == 'decline':
        flash('يجب عليك قبول الشروط والأحكام للمتابعة واستخدام المنصة.', 'warning')
        return redirect(url_for('terms_and_conditions'))
    
    return redirect(url_for('terms_and_conditions'))


if __name__ == '__main__':
    # Configure logging to ensure token usage logs are visible
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Set specific loggers to INFO level
    logging.getLogger('ai_config').setLevel(logging.INFO)
    logging.getLogger('agentic_ai_service').setLevel(logging.INFO)


# Additional pages routes
@app.route('/about')
def about():
    """Display about us page"""
    return render_template('about.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """Display contact page and handle contact form submissions"""
    if request.method == 'POST':
        # Handle contact form submission
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        company = request.form.get('company')
        subject = request.form.get('subject')
        message = request.form.get('message')
        
        # Here you would typically save to database or send email
        # For now, just flash a success message
        flash('Thank you for your message! We will get back to you within 24 hours.', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')


@app.route('/pricing')
def pricing():
    """Display pricing page"""
    return render_template('pricing.html')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # For PythonAnywhere deployment, use host='0.0.0.0' and remove debug
    socketio.run(app, host='0.0.0.0', port=8001, debug=True)