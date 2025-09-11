from flask import redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, current_user
from datetime import datetime
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView as AdminModelView
from wtforms import SelectField

# Import db from app_init
try:
    from app_init import db
except ImportError:
    # Fallback for when app_init is not available
    db = SQLAlchemy()

# Create a temporary admin instance
admin = None

def init_admin(app):
    """Initialize admin with the app instance"""
    global admin
    admin = Admin(app, name='Admin Panel', template_mode='bootstrap4')
    return admin

class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Basic Company Information - Arabic
    name_ar = db.Column(db.String(200), nullable=False)  # اسم الشركة (بالعربي)
    
    # Basic Company Information - English
    name_en = db.Column(db.String(200), nullable=True)  # اسم الشركة (بالإنجليزي)
    
    # Legal Information
    legal_type = db.Column(db.String(100), nullable=True)  # النوع القانوني (شركة مساهمة / ذات مسؤولية محدودة / فردي)
    tax_id = db.Column(db.String(50), nullable=True)  # الرقم الضريبي / VAT
    commercial_registration = db.Column(db.String(50), nullable=True)  # رقم السجل التجاري
    vat_number = db.Column(db.String(50), nullable=True)  # VAT Number
    
    # Contact Information
    registered_address = db.Column(db.Text, nullable=True)  # العنوان المسجل
    website = db.Column(db.String(200), nullable=True)  # الموقع الإلكتروني
    office_phone = db.Column(db.String(20), nullable=True)  # هاتف المكتب
    mobile_contact = db.Column(db.String(20), nullable=True)  # موبايل جهة التواصل
    email = db.Column(db.String(120), unique=True, nullable=False)  # البريد الإلكتروني
    
    # Contact Person Information
    contact_person = db.Column(db.String(100), nullable=True)  # الشخص المسؤول / اسم جهة التواصل
    contact_position = db.Column(db.String(100), nullable=True)  # المنصب
    owner_name = db.Column(db.String(100), nullable=True)  # اسم صاحب المنشأة أو المفوض
    
    # Banking Information
    bank_name = db.Column(db.String(200), nullable=True)  # اسم البنك
    account_name = db.Column(db.String(200), nullable=True)  # اسم الحساب
    account_number = db.Column(db.String(100), nullable=True)  # رقم الحساب / IBAN
    bank_branch = db.Column(db.String(200), nullable=True)  # فرع البنك
    
    # Document Attachments
    commercial_registration_doc = db.Column(db.String(255), nullable=True)  # السجل التجاري (PDF)
    tax_card_doc = db.Column(db.String(255), nullable=True)  # البطاقة الضريبية (PDF)
    e_invoice_proof_doc = db.Column(db.String(255), nullable=True)  # إثبات الفاتورة الإلكترونية (PDF)
    logo_doc = db.Column(db.String(255), nullable=True)  # شعار (PNG/SVG)
    letterhead_doc = db.Column(db.String(255), nullable=True)  # ليتر هيد (PDF/DOCX)
    bank_letter_doc = db.Column(db.String(255), nullable=True)  # خطاب البنك (PDF)
    owner_id_doc = db.Column(db.String(255), nullable=True)  # صورة هوية المفوض (JPG/PDF)
    product_catalog_doc = db.Column(db.String(255), nullable=True)  # نماذج/كتالوج منتجات
    quality_certificates_doc = db.Column(db.String(255), nullable=True)  # شهادات جودة / تراخيص
    
    # Status and Approval
    is_active = db.Column(db.Boolean, default=False, nullable=False)  # Status active or not, default is not
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    
    # Company Type and Classification
    company_type = db.Column(db.String(50), default='supplier', nullable=False)  # 'supplier', 'client', 'system'
    sector = db.Column(db.String(100), nullable=True)  # Business sector
    
    # Additional Company Information
    founded_year = db.Column(db.Integer, nullable=True)  # Year company was founded
    employees_count = db.Column(db.String(20), nullable=True)  # e.g., "1-10", "11-50", "51-200", "200+"
    certifications = db.Column(db.Text, nullable=True)  # ISO certifications, etc.
    operating_countries = db.Column(db.Text, nullable=True)  # Countries where they operate
    company_logo = db.Column(db.String(255), nullable=True)  # Path to company logo
    rating = db.Column(db.Float, nullable=True, default=0.0)  # Average rating from clients
    total_reviews = db.Column(db.Integer, nullable=True, default=0)  # Total number of reviews
    
    # Company Preferences
    email_notifications = db.Column(db.Boolean, default=True, nullable=False)  # Enable email notifications
    app_notifications = db.Column(db.Boolean, default=True, nullable=False)  # Enable in-app notifications
    preferred_language = db.Column(db.String(10), default='ar', nullable=False)  # 'ar' for Arabic, 'en' for English
    email_marketing = db.Column(db.Boolean, default=False, nullable=False)  # Enable marketing emails
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    users = db.relationship('User', lazy=True, cascade='all, delete-orphan')
    orders = db.relationship('Order', lazy=True)
    offers = db.relationship('Offer', lazy=True)

    def __repr__(self):
        return f'<Company {self.name_ar or self.name_en}>'
    
    @property
    def display_name(self):
        """Get company name for display (Arabic preferred, fallback to English)"""
        return self.name_ar or self.name_en or 'Unknown Company'
    
    @property
    def is_fully_registered(self):
        """Check if company has all required documents"""
        required_docs = [
            self.commercial_registration_doc,
            self.tax_card_doc,
            self.owner_id_doc
        ]
        return all(doc for doc in required_docs)
    
    @property
    def registration_status(self):
        """Get registration status based on documents and approval"""
        if not self.is_approved:
            return 'pending_approval'
        elif not self.is_active:
            return 'inactive'
        elif not self.is_fully_registered:
            return 'incomplete_documents'
        else:
            return 'fully_registered'
    
    @classmethod
    def get_default_company(cls):
        """Get or create the default system company for users without specific company"""
        default_company = cls.query.filter_by(company_type='system', name_ar='النظام الافتراضي').first()
        if not default_company:
            default_company = cls(
                name_ar='النظام الافتراضي',
                name_en='System Default',
                email='system@almoshtariat.com',
                company_type='system',
                is_approved=True,
                is_active=True
            )
            db.session.add(default_company)
            db.session.commit()
        return default_company

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='client', nullable=False)  # 'client', 'company', 'employee', or 'admin'
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)  # Now required!
    
    # Email verification fields
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_code = db.Column(db.String(6), nullable=True)
    verification_sent_at = db.Column(db.DateTime, nullable=True)
    
    # New fields for enhanced user registration
    name = db.Column(db.String(100), nullable=True)  # Made nullable for existing users
    country = db.Column(db.String(100), nullable=True)  # Made nullable for existing users
    city = db.Column(db.String(100), nullable=True)  # Made nullable for existing users
    phone_number = db.Column(db.String(20), nullable=True)  # Made nullable for existing users
    company_name = db.Column(db.String(200), nullable=True)  # Optional company name
    sector = db.Column(db.String(100), nullable=True)  # Business sector
    tax_number = db.Column(db.String(50), nullable=True)  # Tax identification number
    account_type = db.Column(db.String(20), default='client', nullable=True)  # Made nullable for existing users
    uploaded_file = db.Column(db.String(255), nullable=True)  # File path for uploaded documents
    
    orders = db.relationship('Order', foreign_keys='Order.user_id', lazy=True, overlaps="admin_created_orders")
    admin_created_orders = db.relationship('Order', foreign_keys='Order.created_by_admin', lazy=True, overlaps="orders")
    preferences = db.relationship('UserPreference', lazy=True)
    
    # Add missing relationship without backref to avoid conflicts
    company = db.relationship('Company')

    def __repr__(self):
        return f'<User {self.username}>'
    
    @property
    def company_name_display(self):
        """Get company name for display purposes"""
        return self.company.name_ar or self.company.name_en or 'Unknown Company' if self.company else 'Unknown Company'
    
    @property
    def is_company_user(self):
        """Check if user belongs to a supplier company"""
        return self.company and self.company.company_type == 'supplier'
    
    @property
    def is_client_user(self):
        """Check if user belongs to a client company"""
        return self.company and self.company.company_type == 'client'
    
    @property
    def is_system_user(self):
        """Check if user belongs to the system company"""
        return self.company and self.company.company_type == 'system'

class UserPreference(db.Model):
    """Model to store user purchase preferences and patterns extracted from Excel files"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Product information
    product_name = db.Column(db.String(200), nullable=False)
    product_category = db.Column(db.String(100), nullable=True)
    product_description = db.Column(db.Text, nullable=True)
    
    # Purchase pattern information
    quantity = db.Column(db.Integer, nullable=True)
    unit = db.Column(db.String(20), default='pcs', nullable=True)
    frequency = db.Column(db.String(50), nullable=True)  # 'monthly', 'quarterly', 'yearly', 'as_needed'
    last_purchased = db.Column(db.Date, nullable=True)
    typical_order_size = db.Column(db.Integer, nullable=True)
    preferred_suppliers = db.Column(db.Text, nullable=True)  # JSON string for multiple suppliers
    max_price_per_unit = db.Column(db.Float, nullable=True)
    
    # Metadata
    source_file = db.Column(db.String(255), nullable=True)  # Original Excel file path
    extracted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    confidence_score = db.Column(db.Float, default=1.0, nullable=False)  # How confident we are in this preference
    
    # Additional preferences
    preferred_delivery_time = db.Column(db.String(50), nullable=True)  # 'urgent', 'standard', 'flexible'
    quality_preference = db.Column(db.String(50), nullable=True)  # 'premium', 'standard', 'budget'
    payment_preference = db.Column(db.String(50), nullable=True)  # 'cash', 'credit', 'net30', 'net60'
    
    # Add missing relationship without backref to avoid conflicts
    user = db.relationship('User')
    
    def __repr__(self):
        return f'<UserPreference {self.product_name} for User {self.user_id}>'

class Cart(db.Model):
    """Model to store user's shopping cart items"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Product information
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    unit = db.Column(db.String(20), default='pcs', nullable=False)
    price = db.Column(db.String(50), nullable=True)  # Store as string to handle various formats
    
    # Supplier information
    supplier_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
    supplier_name = db.Column(db.String(200), nullable=True)
    
    # Metadata
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    user = db.relationship('User')
    supplier = db.relationship('Company')
    
    def __repr__(self):
        return f'<Cart {self.product_name} x{self.quantity} for User {self.user_id}>'
    
    def to_dict(self):
        """Convert cart item to dictionary for easy processing"""
        return {
            'id': self.id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'unit': self.unit,
            'price': self.price,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier_name,
            'notes': self.notes,
            'added_at': self.added_at.isoformat() if self.added_at else None
        }

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)  # Now required!
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Panel 1: Order Details
    order_name = db.Column(db.String(200), nullable=False, default='New Order')
    description = db.Column(db.Text, nullable=True)
    sector = db.Column(db.String(100), nullable=False, default='Other')
    order_type = db.Column(db.String(50), nullable=False, default='direct')  # direct, مناقصة, طلب تسعير
    
    # Panel 3: Delivery
    delivery_date = db.Column(db.Date, nullable=True)
    delivery_time = db.Column(db.String(10), nullable=True)  # HH:MM format
    delivery_address = db.Column(db.Text, nullable=True)
    delivery_notes = db.Column(db.Text, nullable=True)
    
    # Panel 3: Delivery - Receiver Information
    receiver_name = db.Column(db.String(100), nullable=True)
    receiver_phone = db.Column(db.String(20), nullable=True)
    
    # Panel 4: Payment
    payment_way = db.Column(db.String(50), nullable=True)  # cash, bank_transfer, waiting
    payment_steps = db.Column(db.Text, nullable=True)  # JSON string for payment steps data
    
    # Panel 5: Order Settings
    direct_negotiation = db.Column(db.Boolean, default=False)
    accept_unregistered_suppliers = db.Column(db.Boolean, default=False)
    max_suppliers = db.Column(db.Integer, default=10)
    
    # Admin fields
    status = db.Column(db.String(20), default='pending', nullable=False)  # 'pending', 'accepted', 'rejected', 'completed', 'cancelled'
    priority = db.Column(db.String(20), default='medium', nullable=False)  # 'low', 'medium', 'high', 'urgent'
    admin_notes = db.Column(db.Text, nullable=True)  # Admin-only notes
    created_by_admin = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Admin who created this order
    package_number = db.Column(db.String(50), nullable=True)  # Package tracking number
    total_amount = db.Column(db.Float, nullable=True)  # Total order amount
    
    purchases = db.relationship('Purchase', lazy=True)
    offers = db.relationship('Offer', lazy=True)
    
    # Add missing relationships without backrefs to avoid conflicts
    user = db.relationship('User', foreign_keys=[user_id])
    admin_user = db.relationship('User', foreign_keys=[created_by_admin])
    company = db.relationship('Company')

    def __repr__(self):
        return f'<Order {self.id} for User {self.user_id}>'
    
    @property
    def client_company(self):
        """Get the client company (company that placed the order)"""
        return self.user.company if self.user else None
    
    @property
    def supplier_companies(self):
        """Get all supplier companies that made offers on this order"""
        return [offer.company for offer in self.offers if offer.company]
    
    def set_company_from_user(self):
        """Automatically set company_id based on the user's company"""
        if self.user and self.user.company:
            self.company_id = self.user.company.id
        else:
            # Fallback to default company if user has no company
            default_company = Company.get_default_company()
            self.company_id = default_company.id

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sector = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    part_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    
    # Panel 2: Products - Additional fields
    technical_specs = db.Column(db.Text, nullable=True)
    unit = db.Column(db.String(20), default='pcs', nullable=False)  # kilo, piece, meter, liter
    max_price_per_unit = db.Column(db.Float, nullable=True)
    product_code = db.Column(db.String(100), nullable=True)
    best_supplier = db.Column(db.String(200), nullable=True)
    uploaded_file = db.Column(db.String(255), nullable=True)  # File path for uploaded files
    
    # Add missing relationship without backref to avoid conflicts
    order = db.relationship('Order')

    def __repr__(self):
        return f'<Purchase {self.part_name} ({self.sector})>'

class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    total_price = db.Column(db.Float, nullable=False)  # Total price in EGP
    description = db.Column(db.Text, nullable=False)
    delivery_time = db.Column(db.String(50), nullable=True)  # New field for delivery time
    deduction_percentage = db.Column(db.Float, nullable=True, default=0.0)  # Deduction percentage (e.g., 5.0 for 5%)
    transportation_fees = db.Column(db.Float, nullable=True, default=0.0)  # Transportation fees in EGP
    guarantee = db.Column(db.String(200), nullable=True)  # Guarantee terms (e.g., "1 year warranty")
    status = db.Column(db.String(20), default='pending', nullable=False)  # 'pending', 'accepted', 'rejected'
    order_status = db.Column(db.String(50), default='offer_accepted', nullable=False)  # 'offer_accepted', 'preparing', 'quality_check', 'out_for_delivery', 'delivered'
    package_number = db.Column(db.String(50), nullable=True)  # Package tracking number
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Admin control fields
    admin_notes = db.Column(db.Text, nullable=True)  # Admin-only notes
    priority = db.Column(db.String(20), default='normal', nullable=False)  # 'normal', 'high', 'urgent'
    flags = db.Column(db.Text, nullable=True)  # JSON string for flags
    last_modified_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Admin who last modified
    last_modified_at = db.Column(db.DateTime, nullable=True)  # Last modification time
    
    # Relationships
    order = db.relationship('Order')
    company = db.relationship('Company')
    product_offers = db.relationship('ProductOffer', backref='offer', cascade='all, delete-orphan')
    last_modified_admin = db.relationship('User', foreign_keys=[last_modified_by])

    def __repr__(self):
        return f'<Offer {self.id} for Order {self.order_id}>'

class ProductOffer(db.Model):
    """Individual product pricing within an offer"""
    id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.Integer, db.ForeignKey('offer.id'), nullable=False)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False)
    unit_price = db.Column(db.Float, nullable=False)  # Price per unit in EGP
    total_price = db.Column(db.Float, nullable=False)  # Total price for this product (unit_price * quantity)
    notes = db.Column(db.Text, nullable=True)  # Product-specific notes
    
    # Relationships
    purchase = db.relationship('Purchase')
    
    def __repr__(self):
        return f'<ProductOffer {self.id} for Purchase {self.purchase_id}>'

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = db.relationship('Message', backref='chat', lazy=True, order_by='Message.created_at')
    
    # Relationships
    client = db.relationship('User', foreign_keys=[client_id])
    company = db.relationship('Company', foreign_keys=[company_id])

    def __repr__(self):
        return f'<Chat {self.id} between Client {self.client_id} and Company {self.company_id}>'

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    sender_id = db.Column(db.Integer, nullable=False)  # Can be user.id or company.id
    sender_type = db.Column(db.String(20), nullable=False)  # 'client' or 'company'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationships - dynamic based on sender_type
    @property
    def sender(self):
        if self.sender_type == 'client':
            return User.query.get(self.sender_id)
        elif self.sender_type == 'company':
            return Company.query.get(self.sender_id)
        return None

    def __repr__(self):
        return f'<Message {self.id} in Chat {self.chat_id}>'

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), nullable=False)
    sku = db.Column(db.String(100), unique=True, nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=True)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    min_quantity = db.Column(db.Integer, default=0, nullable=False)  # Minimum stock level
    unit = db.Column(db.String(50), default='pcs', nullable=False)  # pieces, kg, liters, etc.
    location = db.Column(db.String(100), nullable=True)  # Warehouse location
    supplier = db.Column(db.String(200), nullable=True)
    supplier_contact = db.Column(db.String(200), nullable=True)
    requirements = db.Column(db.Text, nullable=True)  # Special requirements or specifications
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign key to company
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company')

    def __repr__(self):
        return f'<Product {self.name} ({self.sku})>'
    
    @property
    def stock_status(self):
        """Returns stock status based on quantity"""
        if self.quantity <= 0:
            return 'out_of_stock'
        elif self.quantity <= self.min_quantity:
            return 'low_stock'
        else:
            return 'in_stock'
    
    @property
    def total_value(self):
        """Returns total inventory value"""
        return self.quantity * self.price

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # 'order', 'offer', 'chat', 'inventory', 'system'
    priority = db.Column(db.String(20), default='normal', nullable=False)  # 'low', 'normal', 'high', 'urgent'
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    is_sent = db.Column(db.Boolean, default=False, nullable=False)  # For email notifications
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Foreign keys - can be null for system-wide notifications
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
    
    # Additional data for specific notification types
    related_order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    related_offer_id = db.Column(db.Integer, db.ForeignKey('offer.id'), nullable=True)
    related_chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=True)
    related_product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id])
    company = db.relationship('Company', foreign_keys=[company_id])
    related_order = db.relationship('Order', foreign_keys=[related_order_id])
    related_offer = db.relationship('Offer', foreign_keys=[related_offer_id])
    related_chat = db.relationship('Chat', foreign_keys=[related_chat_id])
    related_product = db.relationship('Product', foreign_keys=[related_product_id])
    
    def __repr__(self):
        return f'<Notification {self.id}: {self.title}>'
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.read_at = datetime.utcnow()
    
    @property
    def is_urgent(self):
        """Check if notification is urgent priority"""
        return self.priority == 'urgent'
    
    @property
    def age_in_hours(self):
        """Get notification age in hours"""
        return (datetime.utcnow() - self.created_at).total_seconds() / 3600


class HiddenOrder(db.Model):
    """Model to track orders that companies have hidden from their view"""
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    hidden_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    company = db.relationship('Company', foreign_keys=[company_id])
    order = db.relationship('Order', foreign_keys=[order_id])
    
    # Ensure unique combination of company and order
    __table_args__ = (db.UniqueConstraint('company_id', 'order_id', name='_company_order_uc'),)
    
    def __repr__(self):
        return f'<HiddenOrder {self.company_id} -> {self.order_id}>'

class Package(db.Model):
    """Model for basic package information"""
    id = db.Column(db.Integer, primary_key=True)
    package_number = db.Column(db.String(50), unique=True, nullable=False)
    
    # Relationships
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    offer_id = db.Column(db.Integer, db.ForeignKey('offer.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    # Package value
    total_value = db.Column(db.Float, nullable=False)  # Total package value from offer
    
    # Sender information
    sender_name = db.Column(db.String(200), nullable=False)
    sender_phone = db.Column(db.String(20), nullable=False)
    sender_address = db.Column(db.Text, nullable=False)
    
    # Receiver information
    receiver_name = db.Column(db.String(200), nullable=False)
    receiver_phone = db.Column(db.String(20), nullable=False)
    receiver_address = db.Column(db.Text, nullable=False)
    
    # Package status and tracking
    status = db.Column(db.String(50), nullable=False)
    
    # Delivery confirmation
    delivery_code = db.Column(db.String(10), nullable=True)  # Client-generated confirmation code
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False)
    shipped_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    
    # Additional information
    notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    order = db.relationship('Order', foreign_keys=[order_id])
    offer = db.relationship('Offer', foreign_keys=[offer_id])
    company = db.relationship('Company', foreign_keys=[company_id])
    
    def __repr__(self):
        return f'<Package {self.package_number} for Order {self.order_id}>'

class SupplierOrder(db.Model):
    """Model for supplier orders (from cart) - separate from regular orders"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    # Order details
    order_name = db.Column(db.String(200), nullable=False)
    sector = db.Column(db.String(100), nullable=True)
    order_type = db.Column(db.String(50), nullable=True)
    delivery_date = db.Column(db.Date, nullable=True)
    
    # Payment and settings
    payment_steps = db.Column(db.Text, nullable=True)  # JSON string
    direct_negotiation = db.Column(db.Boolean, default=False)
    accept_unregistered_suppliers = db.Column(db.Boolean, default=False)
    max_suppliers = db.Column(db.Integer, default=10)
    
    # Status and metadata
    status = db.Column(db.String(50), default='pending', nullable=False)  # pending, accepted, rejected, completed
    total_amount = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User')
    company = db.relationship('Company')
    products = db.relationship('SupplierOrderProduct', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<SupplierOrder {self.order_name} for User {self.user_id} Company {self.company_id}>'

class SupplierOrderProduct(db.Model):
    """Model for products in supplier orders"""
    id = db.Column(db.Integer, primary_key=True)
    supplier_order_id = db.Column(db.Integer, db.ForeignKey('supplier_order.id'), nullable=False)
    
    # Product details
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    unit = db.Column(db.String(20), default='pcs', nullable=False)
    price = db.Column(db.String(50), nullable=True)
    
    # Additional details
    technical_specs = db.Column(db.Text, nullable=True)
    supplier_notes = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Add missing relationship without backref to avoid conflicts
    supplier_order = db.relationship('SupplierOrder')
    
    def __repr__(self):
        return f'<SupplierOrderProduct {self.product_name} x{self.quantity} {self.unit}>'


# Custom Admin View with access control and form customization
class CustomAdminView(AdminModelView):
    def is_accessible(self):
        return True

    def inaccessible_callback(self, name, **kwargs):
        flash('You do not have permission to access the admin panel.', 'error')
        return redirect(url_for('index'))

class UserAdmin(CustomAdminView):
    column_list = ['id', 'username', 'email', 'name', 'role', 'account_type', 'country', 'city', 'company_id']
    form_excluded_columns = ['password_hash', 'orders']  # Exclude sensitive or complex fields
    form_args = {
        'role': {
            'choices': [('client', 'Client'), ('company', 'Company'), ('employee', 'Employee'), ('admin', 'Admin')],
            'widget': SelectField()
        },
        'account_type': {
            'choices': [('client', 'Client'), ('supplier', 'Supplier')],
            'widget': SelectField()
        },
        'sector': {
            'choices': [
                ('', 'None'),
                ('Technology', 'Technology'),
                ('Manufacturing', 'Manufacturing'),
                ('Healthcare', 'Healthcare'),
                ('Finance', 'Finance'),
                ('Retail', 'Retail'),
                ('Construction', 'Construction'),
                ('Automotive', 'Automotive'),
                ('Food & Beverage', 'Food & Beverage'),
                ('Energy', 'Energy'),
                ('Transportation', 'Transportation'),
                ('Education', 'Education'),
                ('Real Estate', 'Real Estate'),
                ('Entertainment', 'Entertainment'),
                ('Other', 'Other')
            ],
            'widget': SelectField()
        }
    }

# Chat History Model for AI conversations
class ChatHistory(db.Model):
    """Model to store AI chat conversation history"""
    __tablename__ = 'chat_history'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # User/Company identification
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # For individual users
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)  # For company chats
    
    # Session identification
    session_id = db.Column(db.String(100), nullable=False)  # Unique session identifier
    
    # Message content
    message_type = db.Column(db.String(20), nullable=False)  # 'user' or 'ai'
    message_content = db.Column(db.Text, nullable=False)  # The actual message
    
    # Context and metadata
    context_data = db.Column(db.Text, nullable=True)  # JSON string for additional context (user data, etc.)
    message_order = db.Column(db.Integer, nullable=False)  # Order of message in conversation
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='chat_history')
    company = db.relationship('Company', backref='chat_history')
    
    def __repr__(self):
        return f'<ChatHistory {self.id}: {self.message_type} - {self.session_id}>'
    
    def to_dict(self):
        """Convert chat history to dictionary for API responses"""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'message_type': self.message_type,
            'message_content': self.message_content,
            'context_data': self.context_data,
            'message_order': self.message_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user_id': self.user_id,
            'company_id': self.company_id
        }

class ChatHistoryAdmin(CustomAdminView):
    """Admin interface for chat history"""
    column_list = ['id', 'session_id', 'user_id', 'company_id', 'message_type', 'message_order', 'created_at']
    column_searchable_list = ['session_id', 'message_content', 'user_id', 'company_id']
    column_filters = ['message_type', 'created_at', 'user_id', 'company_id']
    form_excluded_columns = ['created_at']
    column_default_sort = ('created_at', True)
    
    form_args = {
        'message_type': {
            'choices': [
                ('user', 'User Message'),
                ('ai', 'AI Response')
            ],
            'widget': SelectField()
        }
    }

class UserPreferenceAdmin(CustomAdminView):
    column_list = ['id', 'user_id', 'product_name', 'product_category', 'quantity', 'unit', 'frequency', 'confidence_score', 'extracted_at']
    column_searchable_list = ['product_name', 'product_category', 'product_description']
    column_filters = ['product_category', 'frequency', 'unit', 'extracted_at']
    form_excluded_columns = ['extracted_at', 'source_file']
    form_args = {
        'frequency': {
            'choices': [
                ('monthly', 'Monthly'),
                ('quarterly', 'Quarterly'),
                ('yearly', 'Yearly'),
                ('as_needed', 'As Needed')
            ],
            'widget': SelectField()
        },
        'unit': {
            'choices': [
                ('pcs', 'Pieces'),
                ('kilo', 'Kilograms'),
                ('meter', 'Meters'),
                ('liter', 'Liters'),
                ('box', 'Boxes'),
                ('set', 'Sets')
            ],
            'widget': SelectField()
        },
        'quality_preference': {
            'choices': [
                ('premium', 'Premium'),
                ('standard', 'Standard'),
                ('budget', 'Budget')
            ],
            'widget': SelectField()
        },
        'payment_preference': {
            'choices': [
                ('cash', 'Cash'),
                ('credit', 'Credit'),
                ('net30', 'Net 30'),
                ('net60', 'Net 60')
            ],
            'widget': SelectField()
        }
    }

class CompanyAdmin(CustomAdminView):
    column_list = ['id', 'name_ar', 'name_en', 'email', 'registered_address', 'is_active', 'is_approved', 'registration_status']
    form_excluded_columns = ['users', 'orders', 'offers']  # Exclude relationship fields
    form_args = {
        'sector': {
            'choices': [
                ('', 'None'),  # Allow nullable sector
                ('Electronics', 'Electronics'),
                ('Automotive', 'Automotive'),
                ('Manufacturing', 'Manufacturing'),
                ('Other', 'Other')
            ],
            'widget': SelectField()
        }
    }

class OrderAdmin(CustomAdminView):
    column_list = [
        'id', 'user_id', 'company_id', 'created_at',
        'order_name', 'description', 'sector', 'order_type',
        'delivery_date', 'delivery_time', 'delivery_address', 'delivery_notes',
        'payment_way', 'payment_steps', 'direct_negotiation', 
        'accept_unregistered_suppliers', 'max_suppliers'
    ]
    column_searchable_list = ['order_name', 'description', 'sector', 'order_type']
    column_filters = ['sector', 'order_type', 'payment_way', 'created_at', 'delivery_date']
    form_excluded_columns = ['purchases', 'offers']  # Exclude relationship fields
    form_args = {
        'order_type': {
            'choices': [
                ('direct', 'Direct'),
                ('مناقصة', 'مناقصة'),
                ('طلب تسعير', 'طلب تسعير')
            ],
            'widget': SelectField()
        },
        'payment_way': {
            'choices': [
                ('cash', 'Cash'),
                ('bank_transfer', 'Bank Transfer'),
                ('waiting', 'Waiting')
            ],
            'widget': SelectField()
        },
        'sector': {
            'choices': [
                ('Electronics', 'Electronics'),
                ('Automotive', 'Automotive'),
                ('Manufacturing', 'Manufacturing'),
                ('Construction', 'Construction'),
                ('Healthcare', 'Healthcare'),
                ('Food & Beverage', 'Food & Beverage'),
                ('Textiles', 'Textiles'),
                ('Chemicals', 'Chemicals'),
                ('Other', 'Other')
            ],
            'widget': SelectField()
        }
    }

class PurchaseAdmin(CustomAdminView):
    column_list = [
        'id', 'sector', 'quantity', 'part_name', 'description', 'order_id',
        'technical_specs', 'unit', 'max_price_per_unit', 'product_code', 'best_supplier', 'uploaded_file'
    ]
    column_searchable_list = ['part_name', 'description', 'technical_specs', 'product_code', 'best_supplier']
    column_filters = ['sector', 'unit', 'order_id']
    form_args = {
        'sector': {
            'choices': [
                ('Electronics', 'Electronics'),
                ('Automotive', 'Automotive'),
                ('Manufacturing', 'Manufacturing'),
                ('Construction', 'Construction'),
                ('Healthcare', 'Healthcare'),
                ('Food & Beverage', 'Food & Beverage'),
                ('Textiles', 'Textiles'),
                ('Chemicals', 'Chemicals'),
                ('Other', 'Other')
            ],
            'widget': SelectField()
        },
        'unit': {
            'choices': [
                ('pcs', 'Pieces'),
                ('kilo', 'Kilograms'),
                ('meter', 'Meters'),
                ('liter', 'Liters'),
                ('box', 'Boxes'),
                ('set', 'Sets')
            ],
            'widget': SelectField()
        }
    }

class OfferAdmin(CustomAdminView):
    column_list = ['id', 'order_id', 'company_id', 'total_price', 'status', 'created_at']
    form_args = {
        'status': {
            'choices': [('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')],
            'widget': SelectField()
        }
    }

class ChatAdmin(CustomAdminView):
    column_list = ['id', 'client_id', 'company_id', 'created_at', 'updated_at']
    form_excluded_columns = ['messages']

class MessageAdmin(CustomAdminView):
    column_list = ['id', 'chat_id', 'sender_id', 'sender_type', 'content', 'created_at', 'is_read']
    form_args = {
        'sender_type': {
            'choices': [('client', 'Client'), ('company', 'Company')],
            'widget': SelectField()
        }
    }

class ProductAdmin(CustomAdminView):
    column_list = ['id', 'name', 'sku', 'category', 'quantity', 'price', 'company_id', 'is_active']
    form_excluded_columns = ['created_at', 'updated_at']
    form_args = {
        'category': {
            'choices': [
                ('Electronics', 'Electronics'),
                ('Automotive', 'Automotive'),
                ('Manufacturing', 'Manufacturing'),
                ('Raw Materials', 'Raw Materials'),
                ('Tools', 'Tools'),
                ('Other', 'Other')
            ],
            'widget': SelectField()
        },
        'unit': {
            'choices': [
                ('pcs', 'Pieces'),
                ('kg', 'Kilograms'),
                ('l', 'Liters'),
                ('m', 'Meters'),
                ('box', 'Boxes'),
                ('set', 'Sets')
            ],
            'widget': SelectField()
        }
    }

class NotificationPreference(db.Model):
    """Notification preferences for users and companies"""
    __tablename__ = 'notification_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # User or Company association
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
    
    # Notification type and category
    notification_type = db.Column(db.String(50), nullable=False)  # order, offer, chat, inventory, system, financial
    
    # Delivery preferences
    email_enabled = db.Column(db.Boolean, default=True)
    app_enabled = db.Column(db.Boolean, default=True)
    sms_enabled = db.Column(db.Boolean, default=False)
    
    # Frequency settings
    frequency = db.Column(db.String(20), default='instant')  # instant, hourly, daily, weekly
    
    # Time-based preferences
    business_hours_only = db.Column(db.Boolean, default=False)
    start_time = db.Column(db.Time, default=datetime.strptime('09:00', '%H:%M').time())
    end_time = db.Column(db.Time, default=datetime.strptime('17:00', '%H:%M').time())
    
    # Priority filter
    min_priority = db.Column(db.String(10), default='low')  # low, normal, high, urgent
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='notification_preferences')
    company = db.relationship('Company', backref='notification_preferences')
    
    def __repr__(self):
        return f'<NotificationPreference {self.notification_type} for {"User" if self.user_id else "Company"} {self.user_id or self.company_id}>'

class NotificationTemplate(db.Model):
    """Templates for different notification types"""
    __tablename__ = 'notification_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Template identification
    template_name = db.Column(db.String(100), nullable=False, unique=True)
    notification_type = db.Column(db.String(50), nullable=False)
    
    # Template content
    title_template = db.Column(db.Text, nullable=False)
    description_template = db.Column(db.Text, nullable=False)
    email_subject_template = db.Column(db.Text)
    email_body_template = db.Column(db.Text)
    
    # Template settings
    default_priority = db.Column(db.String(10), default='normal')
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<NotificationTemplate {self.template_name}>'
    
    def render_title(self, **kwargs):
        """Render title template with provided variables"""
        try:
            return self.title_template.format(**kwargs)
        except KeyError as e:
            return f"Template error: Missing variable {e}"
    
    def render_description(self, **kwargs):
        """Render description template with provided variables"""
        try:
            return self.description_template.format(**kwargs)
        except KeyError as e:
            return f"Template error: Missing variable {e}"

class NotificationAdmin(CustomAdminView):
    column_list = ['id', 'title', 'notification_type', 'priority', 'is_read', 'user_id', 'company_id', 'created_at']
    form_excluded_columns = ['created_at', 'read_at']
    form_args = {
        'notification_type': {
            'choices': [
                ('order', 'Order'),
                ('offer', 'Offer'),
                ('chat', 'Chat'),
                ('inventory', 'Inventory'),
                ('system', 'System'),
                ('financial', 'Financial')
            ],
            'widget': SelectField()
        },
        'priority': {
            'choices': [
                ('low', 'Low'),
                ('normal', 'Normal'),
                ('high', 'High'),
                ('urgent', 'Urgent')
            ],
            'widget': SelectField()
        }
    }

class Complaint(db.Model):
    """Model to store user complaints about offers or orders"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    offer_id = db.Column(db.Integer, db.ForeignKey('offer.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    # Complaint details
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    complaint_type = db.Column(db.String(50), nullable=False, default='general')  # 'quality', 'delivery', 'service', 'general'
    priority = db.Column(db.String(20), nullable=False, default='normal')  # 'low', 'normal', 'high', 'urgent'
    status = db.Column(db.String(20), nullable=False, default='open')  # 'open', 'in_progress', 'resolved', 'closed'
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    # Resolution details
    resolution_notes = db.Column(db.Text, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id])
    offer = db.relationship('Offer')
    company = db.relationship('Company')
    resolver = db.relationship('User', foreign_keys=[resolved_by])
    
    def __repr__(self):
        return f'<Complaint {self.title} by User {self.user_id}>'

class ComplaintAdmin(CustomAdminView):
    column_list = ['id', 'title', 'complaint_type', 'priority', 'status', 'user_id', 'company_id', 'created_at']
    form_excluded_columns = ['created_at', 'updated_at', 'resolved_at']
    form_args = {
        'complaint_type': {
            'choices': [
                ('quality', 'Quality Issue'),
                ('delivery', 'Delivery Problem'),
                ('service', 'Service Issue'),
                ('general', 'General Complaint')
            ],
            'widget': SelectField()
        },
        'priority': {
            'choices': [
                ('low', 'Low'),
                ('normal', 'Normal'),
                ('high', 'High'),
                ('urgent', 'Urgent')
            ],
            'widget': SelectField()
        },
        'status': {
            'choices': [
                ('open', 'Open'),
                ('in_progress', 'In Progress'),
                ('resolved', 'Resolved'),
                ('closed', 'Closed')
            ],
            'widget': SelectField()
        }
    }

class HiddenOrderAdmin(CustomAdminView):
    column_list = ['id', 'company_id', 'order_id', 'hidden_at']
    form_excluded_columns = ['hidden_at']

# Add views to Flask-Admin - Commented out to avoid initialization issues
# These will be registered when init_admin() is called
# admin.add_view(UserAdmin(User, db.session))
# admin.add_view(CompanyAdmin(Company, db.session))
# admin.add_view(OrderAdmin(Order, db.session))
# admin.add_view(PurchaseAdmin(Purchase, db.session))
# admin.add_view(OfferAdmin(Offer, db.session))
# admin.add_view(ChatAdmin(Chat, db.session))
# admin.add_view(MessageAdmin(Message, db.session))
# admin.add_view(ProductAdmin(Product, db.session))
# admin.add_view(NotificationAdmin(Notification, db.session))
# admin.add_view(HiddenOrderAdmin(HiddenOrder, db.session))
# admin.add_view(UserPreferenceAdmin(UserPreference, db.session))

def register_admin_views(admin_instance):
    """Register all admin views with the admin instance"""
    admin_instance.add_view(UserAdmin(User, db.session))
    admin_instance.add_view(CompanyAdmin(Company, db.session))
    admin_instance.add_view(OrderAdmin(Order, db.session))
    admin_instance.add_view(PurchaseAdmin(Purchase, db.session))
    admin_instance.add_view(OfferAdmin(Offer, db.session))
    admin_instance.add_view(ChatAdmin(Chat, db.session))
    admin_instance.add_view(MessageAdmin(Message, db.session))
    admin_instance.add_view(ProductAdmin(Product, db.session))
    admin_instance.add_view(NotificationAdmin(Notification, db.session))
    admin_instance.add_view(HiddenOrderAdmin(HiddenOrder, db.session))
    admin_instance.add_view(UserPreferenceAdmin(UserPreference, db.session))
    admin_instance.add_view(ComplaintAdmin(Complaint, db.session))
    admin_instance.add_view(BalanceAdmin(Balance, db.session))
    admin_instance.add_view(TransactionAdmin(Transaction, db.session))

class CompanyStatusHistory(db.Model):
    """Model to track company status changes with reasons"""
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Status change details
    old_status = db.Column(db.String(100), nullable=False)  # Previous status
    new_status = db.Column(db.String(100), nullable=False)  # New status
    reason = db.Column(db.Text, nullable=True)  # Optional reason/note
    
    # Timestamps
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    company = db.relationship('Company', backref='status_history')
    admin_user = db.relationship('User', foreign_keys=[admin_user_id])
    
    def __repr__(self):
        return f'<CompanyStatusHistory {self.company_id}: {self.old_status} -> {self.new_status}>'
    
    @property
    def status_display(self):
        """Get human-readable status names"""
        status_map = {
            'approve': 'Approved',
            'reject': 'Rejected',
            'activate': 'Activated',
            'deactivate': 'Deactivated',
            'suspend': 'Suspended',
            'reactivate': 'Reactivated',
            'request_info': 'Information Requested'
        }
        return status_map.get(self.new_status, self.new_status.title())

class Balance(db.Model):
    """Model to track user account balances"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    # Balance details
    current_balance = db.Column(db.Float, nullable=False, default=1200.0)  # Default 1200 EGP
    currency = db.Column(db.String(3), nullable=False, default='EGP')
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('balance', uselist=False))
    transactions = db.relationship('Transaction', backref='balance', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Balance {self.user_id}: {self.current_balance} {self.currency}>'
    
    def get_balance(self):
        """Get current balance as float"""
        return float(self.current_balance)
    
    def add_transaction(self, amount, transaction_type, description=None, reference_id=None):
        """Add a transaction and update balance"""
        transaction = Transaction(
            balance_id=self.id,
            user_id=self.user_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            reference_id=reference_id,
            balance_before=self.current_balance,
            balance_after=self.current_balance + amount
        )
        
        self.current_balance += amount
        self.updated_at = datetime.utcnow()
        
        db.session.add(transaction)
        return transaction

class Transaction(db.Model):
    """Model to track all user transactions for statements"""
    id = db.Column(db.Integer, primary_key=True)
    balance_id = db.Column(db.Integer, db.ForeignKey('balance.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Transaction details
    amount = db.Column(db.Float, nullable=False)  # Positive for credit, negative for debit
    transaction_type = db.Column(db.String(50), nullable=False)  # 'deposit', 'withdrawal', 'payment', 'refund', 'adjustment'
    description = db.Column(db.Text, nullable=True)
    reference_id = db.Column(db.String(100), nullable=True)  # Order ID, Payment ID, etc.
    
    # Balance tracking
    balance_before = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)
    
    # Status and metadata
    status = db.Column(db.String(20), nullable=False, default='completed')  # 'pending', 'completed', 'failed', 'cancelled'
    currency = db.Column(db.String(3), nullable=False, default='EGP')
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    user = db.relationship('User', backref='transactions')
    
    def __repr__(self):
        return f'<Transaction {self.id}: {self.amount} {self.currency} - {self.transaction_type}>'
    
    @property
    def is_credit(self):
        """Check if transaction is a credit (positive amount)"""
        return self.amount > 0
    
    @property
    def is_debit(self):
        """Check if transaction is a debit (negative amount)"""
        return self.amount < 0
    
    @property
    def formatted_amount(self):
        """Get formatted amount with currency"""
        return f"{abs(self.amount):.2f} {self.currency}"

class BalanceAdmin(CustomAdminView):
    column_list = ['id', 'user_id', 'current_balance', 'currency', 'created_at', 'updated_at']
    column_searchable_list = ['user_id']
    column_filters = ['currency', 'created_at']
    form_excluded_columns = ['transactions', 'created_at', 'updated_at']

class TransactionAdmin(CustomAdminView):
    column_list = ['id', 'user_id', 'amount', 'transaction_type', 'status', 'created_at', 'processed_at']
    column_searchable_list = ['user_id', 'reference_id', 'description']
    column_filters = ['transaction_type', 'status', 'currency', 'created_at']
    form_excluded_columns = ['balance_before', 'balance_after', 'created_at', 'processed_at']
    form_args = {
        'transaction_type': {
            'choices': [
                ('deposit', 'Deposit'),
                ('withdrawal', 'Withdrawal'),
                ('payment', 'Payment'),
                ('refund', 'Refund'),
                ('adjustment', 'Adjustment')
            ],
            'widget': SelectField()
        },
        'status': {
            'choices': [
                ('pending', 'Pending'),
                ('completed', 'Completed'),
                ('failed', 'Failed'),
                ('cancelled', 'Cancelled')
            ],
            'widget': SelectField()
        },
        'currency': {
            'choices': [
                ('EGP', 'Egyptian Pound'),
                ('USD', 'US Dollar'),
                ('EUR', 'Euro')
            ],
            'widget': SelectField()
        }
    }

class Bill(db.Model):
    """Bill model for managing company bills and invoices"""
    __tablename__ = 'bill'
    
    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(50), unique=True, nullable=False)  # Unique bill identifier
    
    # Relationships
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)  # Billing company
    client_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)  # Client company
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)  # Related order
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # User who created the bill
    
    # Bill details
    issue_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # 'pending', 'paid', 'overdue', 'cancelled'
    
    # Financial information
    subtotal = db.Column(db.Float, nullable=False, default=0.0)
    tax_rate = db.Column(db.Float, nullable=False, default=0.14)  # 14% VAT in Egypt
    tax_amount = db.Column(db.Float, nullable=False, default=0.0)
    discount_amount = db.Column(db.Float, nullable=False, default=0.0)
    total_amount = db.Column(db.Float, nullable=False, default=0.0)
    currency = db.Column(db.String(3), nullable=False, default='EGP')
    
    # Payment information
    payment_method = db.Column(db.String(50), nullable=True)  # 'cash', 'bank_transfer', 'check', etc.
    payment_date = db.Column(db.Date, nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)
    
    # Additional information
    notes = db.Column(db.Text, nullable=True)
    terms_and_conditions = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    company = db.relationship('Company', foreign_keys=[company_id], backref='issued_bills')
    client = db.relationship('Company', foreign_keys=[client_id], backref='received_bills')
    order = db.relationship('Order', backref='bills')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    bill_items = db.relationship('BillItem', backref='bill', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Bill {self.bill_number}>'
    
    @property
    def is_overdue(self):
        """Check if bill is overdue"""
        if self.status == 'paid':
            return False
        return datetime.utcnow().date() > self.due_date
    
    @property
    def days_until_due(self):
        """Calculate days until due date"""
        if self.status == 'paid':
            return 0
        delta = self.due_date - datetime.utcnow().date()
        return delta.days
    
    @property
    def formatted_total(self):
        """Format total amount with currency"""
        return f"{self.total_amount:,.2f} {self.currency}"
    
    def calculate_totals(self):
        """Calculate bill totals based on bill items"""
        self.subtotal = sum(item.total_price for item in self.bill_items)
        self.tax_amount = self.subtotal * self.tax_rate
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount
        return self.total_amount

class BillItem(db.Model):
    """Individual items in a bill"""
    __tablename__ = 'bill_item'
    
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)  # Optional product reference
    
    # Item details
    product_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False, default='pcs')
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    product = db.relationship('Product', backref='bill_items')
    
    def __repr__(self):
        return f'<BillItem {self.product_name} x {self.quantity}>'
    
    @property
    def formatted_unit_price(self):
        """Format unit price"""
        return f"{self.unit_price:,.2f}"
    
    @property
    def formatted_total_price(self):
        """Format total price"""
        return f"{self.total_price:,.2f}"

class AIAgentTask(db.Model):
    """AI Agent Task model for persistent task storage"""
    __tablename__ = 'ai_agent_tasks'
    
    id = db.Column(db.String(36), primary_key=True)  # UUID
    task_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    parameters = db.Column(db.JSON, nullable=True)
    priority = db.Column(db.String(20), default='medium', nullable=False)  # low, medium, high
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, running, completed, failed
    progress = db.Column(db.Integer, default=0, nullable=False)  # 0-100
    result = db.Column(db.JSON, nullable=True)
    error = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    company = db.relationship('Company', backref=db.backref('ai_tasks', lazy=True))
    
    def to_dict(self):
        """Convert task to dictionary for API responses"""
        return {
            'id': self.id,
            'task_type': self.task_type,
            'description': self.description,
            'company_id': self.company_id,
            'parameters': self.parameters,
            'priority': self.priority,
            'status': self.status,
            'progress': self.progress,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

class AIChatSession(db.Model):
    """AI Chat Session model for managing conversations between AI agent and companies"""
    __tablename__ = 'ai_chat_sessions'
    
    id = db.Column(db.String(36), primary_key=True)  # UUID
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    session_name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='active', nullable=False)  # active, archived, closed
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    company = db.relationship('Company', backref=db.backref('chat_sessions', lazy=True))
    messages = db.relationship('AIChatMessage', backref='session', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        """Convert session to dictionary for API responses"""
        return {
            'id': self.id,
            'company_id': self.company_id,
            'session_name': self.session_name,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_message_at': self.last_message_at.isoformat() if self.last_message_at else None,
            'message_count': db.session.query(AIChatMessage).filter_by(session_id=self.id).count()
        }

class AIChatMessage(db.Model):
    """AI Chat Message model for storing individual messages in chat sessions"""
    __tablename__ = 'ai_chat_messages'
    
    id = db.Column(db.String(36), primary_key=True)  # UUID
    session_id = db.Column(db.String(36), db.ForeignKey('ai_chat_sessions.id'), nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)  # 'user', 'ai'
    message_content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text', nullable=False)  # text, task_result, error
    
    # Additional metadata
    message_metadata = db.Column(db.JSON, nullable=True)  # Store additional data like task_id, etc.
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def to_dict(self):
        """Convert message to dictionary for API responses"""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'sender_type': self.sender_type,
            'message_content': self.message_content,
            'message_type': self.message_type,
            'message_metadata': self.message_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# Company Balance and Transaction Models
class CompanyBalance(db.Model):
    """Company balance model for tracking company financial balances"""
    __tablename__ = 'company_balance'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False, unique=True)
    
    # Balance information
    current_balance = db.Column(db.Float, nullable=False, default=0.0)
    currency = db.Column(db.String(3), nullable=False, default='EGP')
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    company = db.relationship('Company', backref=db.backref('balance', uselist=False))
    transactions = db.relationship('CompanyTransaction', backref='company_balance', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<CompanyBalance {self.company_id}: {self.current_balance} {self.currency}>'
    
    def get_balance(self):
        """Get current balance"""
        return self.current_balance
    
    def add_transaction(self, amount, transaction_type, description=None, reference_id=None, created_by_user_id=None):
        """Add a new transaction and update balance"""
        balance_before = self.current_balance
        balance_after = balance_before + amount
        
        # Create transaction record
        transaction = CompanyTransaction(
            company_balance_id=self.id,
            company_id=self.company_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            reference_id=reference_id,
            balance_before=balance_before,
            balance_after=balance_after,
            created_by_user_id=created_by_user_id,
            processed_at=datetime.utcnow()
        )
        
        # Update balance
        self.current_balance = balance_after
        self.updated_at = datetime.utcnow()
        
        db.session.add(transaction)
        return transaction

class CompanyTransaction(db.Model):
    """Company transaction model for tracking company financial transactions"""
    __tablename__ = 'company_transaction'
    
    id = db.Column(db.Integer, primary_key=True)
    company_balance_id = db.Column(db.Integer, db.ForeignKey('company_balance.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    # Transaction details
    amount = db.Column(db.Float, nullable=False)  # Positive for credit, negative for debit
    transaction_type = db.Column(db.String(50), nullable=False)  # 'revenue', 'expense', 'payment', 'refund', 'adjustment'
    description = db.Column(db.Text, nullable=True)
    reference_id = db.Column(db.String(100), nullable=True)  # Order ID, Payment ID, etc.
    
    # Balance tracking
    balance_before = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)
    
    # Status and metadata
    status = db.Column(db.String(20), nullable=False, default='completed')  # 'pending', 'completed', 'failed', 'cancelled'
    currency = db.Column(db.String(3), nullable=False, default='EGP')
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    
    # User who created this transaction (for audit trail)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relationships
    company = db.relationship('Company', backref='transactions')
    created_by_user = db.relationship('User', foreign_keys=[created_by_user_id])
    
    def __repr__(self):
        return f'<CompanyTransaction {self.id}: {self.amount} {self.currency} ({self.transaction_type})>'
    
    @property
    def is_credit(self):
        """Check if transaction is a credit (positive amount)"""
        return self.amount > 0
    
    @property
    def is_debit(self):
        """Check if transaction is a debit (negative amount)"""
        return self.amount < 0
    
    @property
    def formatted_amount(self):
        """Format amount with currency"""
        return f"{self.amount:,.2f} {self.currency}"

# Admin Views for Company Balance and Transactions
class CompanyBalanceAdmin(CustomAdminView):
    column_list = ['id', 'company_id', 'current_balance', 'currency', 'created_at', 'updated_at']
    column_searchable_list = ['company_id']
    column_filters = ['currency', 'created_at']
    form_excluded_columns = ['transactions', 'created_at', 'updated_at']

class CompanyTransactionAdmin(CustomAdminView):
    column_list = ['id', 'company_id', 'amount', 'transaction_type', 'status', 'created_at', 'processed_at']
    column_searchable_list = ['company_id', 'reference_id', 'description']
    column_filters = ['transaction_type', 'status', 'currency', 'created_at']
    form_excluded_columns = ['balance_before', 'balance_after', 'created_at', 'processed_at']
    form_args = {
        'transaction_type': {
            'choices': [
                ('revenue', 'Revenue'),
                ('expense', 'Expense'),
                ('payment', 'Payment'),
                ('refund', 'Refund'),
                ('adjustment', 'Adjustment')
            ],
            'widget': SelectField()
        },
        'status': {
            'choices': [
                ('pending', 'Pending'),
                ('completed', 'Completed'),
                ('failed', 'Failed'),
                ('cancelled', 'Cancelled')
            ],
            'widget': SelectField()
        },
        'currency': {
            'choices': [
                ('EGP', 'Egyptian Pound'),
                ('USD', 'US Dollar'),
                ('EUR', 'Euro')
            ],
            'widget': SelectField()
        }
    }