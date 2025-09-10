from typing import Dict, List, Any, Optional, cast
import google.generativeai as genai
from ai_config import ai_config
from models import Order, Purchase, Company, Offer, ProductOffer, CompanyBalance, CompanyTransaction, Bill, BillItem
from app_init import db
from datetime import datetime, timedelta
import json
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

class AgenticAIService:
    def __init__(self):
        self.client = ai_config.client if ai_config.is_configured() else None
        self.model = "gemini-1.5-flash"
        self.functions = [
            {
                "type": "function",
                "function": {
                    "name": "get_recent_orders",
                    "description": "Get recent orders for the company",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Number of orders to retrieve (default: 10)",
                                "default": 10
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_order_details",
                    "description": "Get detailed information about a specific order",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "integer",
                                "description": "The ID of the order to get details for"
                            }
                        },
                        "required": ["order_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_offer_for_order",
                    "description": "Create an offer for a specific order",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "integer",
                                "description": "The ID of the order to create an offer for"
                            },
                            "total_price": {
                                "type": "number",
                                "description": "Total price for the offer"
                            },
                            "delivery_time": {
                                "type": "string",
                                "description": "Delivery time for the offer"
                            },
                            "description": {
                                "type": "string",
                                "description": "Description of the offer"
                            }
                        },
                        "required": ["order_id", "total_price", "delivery_time", "description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_company_balance",
                    "description": "Get the current balance of the company",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_company_registration_status",
                    "description": "Get the company's registration status and required documents",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_company_documents_status",
                    "description": "Get the status of all required company documents",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_company_information",
                    "description": "Get detailed company information including contact details and business info",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_inventory_status",
                    "description": "Get company inventory status including stock levels, product counts, and inventory analytics",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_availability",
                    "description": "البحث عن توفر منتج معين أو فئة منتجات في المخزون",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_query": {
                                "type": "string",
                                "description": "اسم المنتج أو الفئة للبحث عنها"
                            }
                        },
                        "required": ["search_query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_bills_summary",
                    "description": "Get summary of company bills including totals, status breakdown, and recent bills",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Number of recent bills to include (default: 10)",
                                "default": 10
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_bill_details",
                    "description": "Get detailed information about a specific bill",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bill_id": {
                                "type": "integer",
                                "description": "The ID of the bill to retrieve"
                            }
                        },
                        "required": ["bill_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "mark_bill_as_paid",
                    "description": "Mark a bill as paid",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bill_id": {
                                "type": "integer",
                                "description": "The ID of the bill to mark as paid"
                            }
                        },
                        "required": ["bill_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_bills_from_orders",
                    "description": "Generate bills for orders that don't have bills yet",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_customer_analytics",
                    "description": "تحليل أنماط وسلوك العملاء للشركة",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "analysis_type": {
                                "type": "string",
                                "description": "نوع التحليل المطلوب: patterns (الأنماط), behavior (السلوك), retention (الاحتفاظ), value (القيمة)",
                                "enum": ["patterns", "behavior", "retention", "value"]
                            },
                            "time_period": {
                                "type": "string",
                                "description": "الفترة الزمنية للتحليل: last_month, last_3_months, last_6_months, last_year, all_time",
                                "enum": ["last_month", "last_3_months", "last_6_months", "last_year", "all_time"]
                            }
                        },
                        "required": ["analysis_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_customer_behavior_analysis",
                    "description": "تحليل تفصيلي لسلوك العملاء وتفضيلاتهم",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "focus_area": {
                                "type": "string",
                                "description": "مجال التركيز: purchasing_patterns (أنماط الشراء), preferences (التفضيلات), loyalty (الولاء), satisfaction (الرضا)",
                                "enum": ["purchasing_patterns", "preferences", "loyalty", "satisfaction"]
                            },
                            "customer_segment": {
                                "type": "string",
                                "description": "شريحة العملاء: all (الكل), high_value (عالي القيمة), frequent (متكرر), new (جديد)",
                                "enum": ["all", "high_value", "frequent", "new"]
                            }
                        },
                        "required": ["focus_area"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_company_offers_status",
                    "description": "الحصول على حالة جميع عروض الشركة",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status_filter": {
                                "type": "string",
                                "description": "تصفية حسب الحالة: all, pending, accepted, rejected",
                                "default": "all"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "عدد العروض المراد عرضها (افتراضي: 20)",
                                "default": 20
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_order",
                    "description": "Create a new order for the company. If required information is missing, ask the user for it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_name": {
                                "type": "string",
                                "description": "Name/title of the order"
                            },
                            "description": {
                                "type": "string",
                                "description": "Detailed description of the order"
                            },
                            "sector": {
                                "type": "string",
                                "description": "Business sector for the order"
                            },
                            "order_type": {
                                "type": "string",
                                "description": "Type of order: direct, مناقصة, طلب تسعير",
                                "default": "direct"
                            },
                            "delivery_date": {
                                "type": "string",
                                "description": "Delivery date in YYYY-MM-DD format"
                            },
                            "delivery_address": {
                                "type": "string",
                                "description": "Delivery address"
                            },
                            "payment_way": {
                                "type": "string",
                                "description": "Payment method: cash, bank_transfer, waiting"
                            },
                            "priority": {
                                "type": "string",
                                "description": "Order priority: low, medium, high, urgent",
                                "default": "medium"
                            },
                            "products": {
                                "type": "array",
                                "description": "List of products/items to order",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "part_name": {"type": "string"},
                                        "quantity": {"type": "integer"},
                                        "unit": {"type": "string", "default": "pcs"},
                                        "description": {"type": "string"},
                                        "max_price_per_unit": {"type": "number"}
                                    },
                                    "required": ["part_name", "quantity"]
                                }
                            }
                        },
                        "required": ["order_name", "sector"]
                    }
                }
            }
        ]
    
    def process_user_request(self, company_id: int, user_message: str, conversation_history: Optional[List[Dict]] = None, language: str = 'en') -> Dict[str, Any]:
        """Process user request using agentic AI with function calling"""
        try:
            if not ai_config.is_configured():
                error_message = 'خدمة الذكاء الاصطناعي غير مُكوّنة. يرجى الاتصال بالمسؤول.' if language == 'ar' else 'AI service is not available. Please contact administrator.'
                return {
                    'success': False,
                    'error': 'AI service is not configured',
                    'response': error_message
                }
            
            # Prepare conversation messages
            messages = []
            
            # Add system message with language specification
            language_instruction = "Always respond in English unless specifically requested otherwise." if language == 'en' else "Always respond in Arabic unless specifically requested otherwise."
            system_message = f"""
You are an intelligent business assistant for a company (ID: {company_id}). You can help with:
- Checking recent orders and order details
- Creating offers for orders
- Getting company balance information
- Managing bills and invoices (view summaries, get details, mark as paid)
- Generating bills from orders
- Analyzing customer data and business insights

You have access to various functions to help execute these tasks. Always be helpful, professional, and provide accurate information.
When users ask about orders, offers, bills, or company data, use the appropriate functions to get real-time information.

For bill-related queries, you can:
- Show bill summaries when asked about "bills", "invoices", "فواتير", or "last bills"
- Get specific bill details when given a bill ID
- Mark bills as paid when requested
- Generate new bills from existing orders

Respond in a conversational manner and explain what actions you're taking.
{language_instruction}
"""
            messages.append({"role": "system", "content": system_message})
            
            # Add conversation history if provided
            if conversation_history:
                for msg in conversation_history[-10:]:  # Keep last 10 messages
                    if msg.get('role') in ['user', 'assistant']:
                        messages.append({
                            "role": msg['role'],
                            "content": msg['content']
                        })
            
            # Add current user message
            messages.append({"role": "user", "content": user_message})
            
            # Make API call with function calling
            if self.client is None:
                error_message = 'خدمة الذكاء الاصطناعي غير مُكوّنة. يرجى الاتصال بالمسؤول.' if language == 'ar' else 'AI service is not available. Please contact administrator.'
                return {
                    'success': False,
                    'error': 'AI client not configured',
                    'response': error_message
                }
            
            # Convert messages to Gemini format
            conversation_text = ""
            for msg in messages:
                if msg['role'] == 'system':
                    conversation_text += f"System: {msg['content']}\n\n"
                elif msg['role'] == 'user':
                    conversation_text += f"User: {msg['content']}\n\n"
                elif msg['role'] == 'assistant':
                    conversation_text += f"Assistant: {msg['content']}\n\n"
            
            # Configure generation with function calling
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=200,
                temperature=0.7
            )
            
            # For now, use Gemini without function calling (simpler approach)
            # We'll handle function detection through text analysis
            response = self.client.generate_content(
                conversation_text,
                generation_config=generation_config
            )
            
            # Log API call with basic token estimation
            prompt_length = len(conversation_text)
            response_length = len(response.text) if response.text else 0
            estimated_input_tokens = prompt_length // 4  # Rough estimation: 4 chars per token
            estimated_output_tokens = response_length // 4
            logger.info(f"Gemini API Call 1 - Company ID: {company_id}, Model: {self.model}, "
                       f"Estimated Input Tokens: {estimated_input_tokens}, "
                       f"Estimated Output Tokens: {estimated_output_tokens}, "
                       f"Estimated Total: {estimated_input_tokens + estimated_output_tokens}")
            
            # Get response text
            response_text = response.text if response.text else ""
            
            # Enhanced function detection based on keywords in user message
            function_calls = []
            user_message_lower = user_message.lower()
            
            # Check for specific order details requests
            import re
            order_id_match = re.search(r'(?:طلب|order)\s*(?:رقم|#|id)?\s*(\d+)', user_message_lower)
            if order_id_match:
                order_id = int(order_id_match.group(1))
                function_calls.append({'name': 'get_order_details', 'args': {'order_id': order_id}})
            
            # Check for recent orders requests
            if any(keyword in user_message_lower for keyword in ['orders', 'طلبات', 'طلباتي', 'أحدث الطلبات', 'recent orders']):
                if any(keyword in user_message_lower for keyword in ['recent', 'latest', 'أحدث', 'حديثة', 'الأخيرة', 'رؤية']):
                    function_calls.append({'name': 'get_recent_orders', 'args': {'limit': 10}})
                elif 'طلباتي' in user_message_lower or 'my orders' in user_message_lower:
                    function_calls.append({'name': 'get_recent_orders', 'args': {'limit': 10}})
                else:
                    # Default to showing recent orders for any orders request
                    function_calls.append({'name': 'get_recent_orders', 'args': {'limit': 10}})
            
            # Check for balance requests
            if any(keyword in user_message_lower for keyword in ['balance', 'رصيد', 'رصيدي', 'مالية', 'الرصيد الحالي', 'current balance']):
                function_calls.append({'name': 'get_company_balance', 'args': {}})
            
            # Check for inventory requests
            if any(keyword in user_message_lower for keyword in ['inventory', 'stock', 'مخزون', 'مخازن', 'المخزون', 'حالة المخزون']):
                function_calls.append({'name': 'get_inventory_status', 'args': {}})
            
            # Check for offers requests
            if any(keyword in user_message_lower for keyword in ['offers', 'عروض', 'عروضي', 'العروض', 'my offers']):
                function_calls.append({'name': 'get_company_offers_status', 'args': {'status_filter': 'all', 'limit': 10}})
            
            # Check for company information requests
            if any(keyword in user_message_lower for keyword in ['company info', 'معلومات الشركة', 'بيانات الشركة', 'تفاصيل الشركة']):
                function_calls.append({'name': 'get_company_information', 'args': {}})
            
            # Check for analytics requests
            if any(keyword in user_message_lower for keyword in ['تحليل', 'analytics', 'analysis', 'أداء', 'performance', 'إحصائيات']):
                if any(keyword in user_message_lower for keyword in ['عملاء', 'customers', 'clients']):
                    function_calls.append({'name': 'get_customer_analytics', 'args': {'analysis_type': 'patterns', 'time_period': 'last_3_months'}})
                elif any(keyword in user_message_lower for keyword in ['مبيعات', 'sales', 'بيع']):
                    function_calls.append({'name': 'get_company_offers_status', 'args': {'status_filter': 'accepted', 'limit': 20}})
            
            # Check for bill requests
            bill_id_match = re.search(r'(?:فاتورة|bill|invoice)\s*(?:رقم|#|id)?\s*(\d+)', user_message_lower)
            if bill_id_match:
                bill_id = int(bill_id_match.group(1))
                function_calls.append({'name': 'get_bill_details', 'args': {'bill_id': bill_id}})
            elif any(keyword in user_message_lower for keyword in ['bills', 'invoices', 'فواتير', 'الفواتير', 'آخر الفواتير', 'last bills', 'bill summary', 'ملخص الفواتير']):
                function_calls.append({'name': 'get_bills_summary', 'args': {'limit': 10}})
            
            # Check for mark bill as paid requests
            if any(keyword in user_message_lower for keyword in ['mark as paid', 'تم الدفع', 'دفع الفاتورة', 'سداد']):
                # Try to extract bill ID from the message
                paid_bill_match = re.search(r'(?:فاتورة|bill|invoice)\s*(?:رقم|#|id)?\s*(\d+)', user_message_lower)
                if paid_bill_match:
                    bill_id = int(paid_bill_match.group(1))
                    function_calls.append({'name': 'mark_bill_as_paid', 'args': {'bill_id': bill_id}})
            
            # Check if we detected any function calls
            if function_calls:
                # Execute each function call
                function_results = []
                for func_call in function_calls:
                    function_name = func_call['name']
                    function_args = func_call['args']
                    
                    # Execute the function
                    function_result = self._execute_function(company_id, function_name, function_args)
                    function_results.append({
                        'name': function_name,
                        'result': function_result
                    })
                
                # Create a summary of function results for the final response
                function_summary = "\n\nFunction Results:\n"
                for result in function_results:
                    function_summary += f"- {result['name']}: {json.dumps(result['result'], ensure_ascii=False)}\n"
                
                # Generate final response with function results
                final_prompt = f"{conversation_text}\n\nBased on the following function results, provide a helpful response to the user:\n{function_summary}"
                
                if self.client is None:
                    error_message = 'خدمة الذكاء الاصطناعي غير مُكوّنة. يرجى الاتصال بالمسؤول.' if language == 'ar' else 'AI service is not available. Please contact administrator.'
                    return {
                        'success': False,
                        'error': 'AI client not configured',
                        'response': error_message
                    }
                
                final_response = self.client.generate_content(
                    final_prompt,
                    generation_config=generation_config
                )
                
                # Log second API call with token estimation
                final_prompt_length = len(final_prompt)
                final_response_length = len(final_response.text) if final_response.text else 0
                estimated_input_tokens = final_prompt_length // 4
                estimated_output_tokens = final_response_length // 4
                logger.info(f"Gemini API Call 2 - Company ID: {company_id}, Model: {self.model}, "
                           f"Estimated Input Tokens: {estimated_input_tokens}, "
                           f"Estimated Output Tokens: {estimated_output_tokens}, "
                           f"Estimated Total: {estimated_input_tokens + estimated_output_tokens}")
                
                # Get the final response content
                final_content = final_response.text if final_response.text else ""
                
                # If the final response is empty, provide a default message
                if not final_content or final_content.strip() == '':
                    final_content = 'تم تنفيذ العمليات المطلوبة بنجاح.' if language == 'ar' else 'Operations completed successfully.'
                
                # Check if we have list data to display in UI
                list_data = None
                list_type = None
                
                for result in function_results:
                    if result['name'] == 'get_recent_orders' and 'orders' in result['result']:
                        list_data = result['result']['orders']
                        list_type = 'orders'
                        break
                    elif result['name'] == 'get_company_offers_status' and 'offers' in result['result']:
                        list_data = result['result']['offers']
                        list_type = 'offers'
                        break
                    elif result['name'] == 'get_inventory_status' and 'inventory' in result['result']:
                        list_data = result['result']['inventory']
                        list_type = 'inventory'
                        break
                
                response_data = {
                    'success': True,
                    'response': final_content,
                    'function_calls': [{
                        'name': func_call['name'],
                        'arguments': func_call['args']
                    } for func_call in function_calls]
                }
                
                # Add list data if available
                if list_data and list_type:
                    response_data['list_data'] = list_data
                    response_data['list_type'] = list_type
                
                return response_data
            else:
                # No function calls, return direct response
                logger.info(f"Gemini Total Usage - Company ID: {company_id}, Model: {self.model}, Single response generated")
                
                # Get the response content and handle empty responses
                if not response_text or response_text.strip() == '':
                    response_text = 'تم معالجة طلبك بنجاح.' if language == 'ar' else 'Your request has been processed successfully.'
                
                return {
                    'success': True,
                    'response': response_text
                }
                
        except Exception as e:
            logger.error(f"Error in process_user_request: {str(e)}")
            error_message = 'عذراً، واجهت خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى.' if language == 'ar' else 'Sorry, I encountered an error while processing your request. Please try again.'
            return {
                'success': False,
                'error': str(e),
                'response': error_message
            }
    
    def _execute_function(self, company_id: int, function_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a function based on its name"""
        try:
            if function_name == "get_recent_orders":
                return self._get_recent_orders(company_id, args)
            elif function_name == "get_order_details":
                return self._get_order_details(company_id, args)
            elif function_name == "create_offer_for_order":
                return self._create_offer_for_order(company_id, args)
            elif function_name == "get_company_balance":
                return self._get_company_balance(company_id, args)
            elif function_name == "get_company_registration_status":
                return self._get_company_registration_status(company_id, args)
            elif function_name == "get_company_documents_status":
                return self._get_company_documents_status(company_id, args)
            elif function_name == "get_company_information":
                return self._get_company_information(company_id, args)
            elif function_name == "get_inventory_status":
                return self._get_inventory_status(company_id, args)
            elif function_name == "get_product_availability":
                return self._get_product_availability(company_id, args)
            elif function_name == "get_customer_analytics":
                return self._get_customer_analytics(company_id, args)
            elif function_name == "get_customer_behavior_analysis":
                return self._get_customer_behavior_analysis(company_id, args)
            elif function_name == "get_company_offers_status":
                return self._get_company_offers_status(company_id, args)
            elif function_name == "get_bills_summary":
                return self._get_bills_summary(company_id, args)
            elif function_name == "get_bill_details":
                return self._get_bill_details(company_id, args)
            elif function_name == "mark_bill_as_paid":
                return self._mark_bill_as_paid(company_id, args)
            elif function_name == "generate_bills_from_orders":
                return self._generate_bills_from_orders(company_id, args)
            elif function_name == "create_order":
                return self._create_order(company_id, args)
            else:
                return {'error': f'Unknown function: {function_name}'}
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {str(e)}")
            return {'error': f'Error executing function {function_name}: {str(e)}'}
    
    def _get_recent_orders(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get recent orders for the company"""
        limit = args.get('limit', 10)
        
        orders = Order.query.order_by(Order.created_at.desc()).limit(limit).all()
        orders_data = []
        for order in orders:
            orders_data.append({
                'id': order.id,
                'order_name': order.order_name,
                'description': order.description,
                'status': order.status,
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'total_amount': float(order.total_amount) if order.total_amount else 0
            })
        
        return {
            'orders': orders_data,
            'count': len(orders_data)
        }
    
    def _get_order_details(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed information about a specific order"""
        order_id = args.get('order_id')
        
        order = Order.query.filter_by(id=order_id).first()
        if not order:
            return {'error': f'Order {order_id} not found'}
        
        # Get purchases for this order
        purchases = Purchase.query.filter_by(order_id=order_id).all()
        purchases_data = []
        for purchase in purchases:
            purchases_data.append({
                'id': purchase.id,
                'product_name': purchase.part_name,
                'quantity': purchase.quantity,
                'unit_price': purchase.max_price_per_unit if purchase.max_price_per_unit else 0,
                'total_price': (purchase.quantity * purchase.max_price_per_unit) if purchase.max_price_per_unit else 0,
                'specifications': purchase.technical_specs
            })
        
        # Get existing offers for this order
        offers = Offer.query.filter_by(order_id=order_id, company_id=company_id).all()
        offers_data = []
        for offer in offers:
            offers_data.append({
                'id': offer.id,
                'total_price': float(offer.total_price) if offer.total_price else 0,
                'delivery_time': offer.delivery_time,
                'status': offer.status if hasattr(offer, 'status') else 'pending',
                'created_at': offer.created_at.isoformat() if offer.created_at else None,
                'description': offer.description
            })
        
        return {
            'order': {
                'id': order.id,
                'order_name': order.order_name,
                'description': order.description,
                'status': order.status,
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'total_amount': float(order.total_amount) if order.total_amount else 0
            },
            'purchases': purchases_data,
            'existing_offers': offers_data
        }
    
    def _create_offer_for_order(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create an offer for a specific order"""
        order_id = args.get('order_id')
        total_price = args.get('total_price')
        delivery_time = args.get('delivery_time')
        description = args.get('description', '')
        
        # Validate order exists
        order = Order.query.filter_by(id=order_id).first()
        if not order:
            return {'error': f'Order {order_id} not found'}
        
        try:
            # Create new offer
            offer = Offer()
            offer.order_id = order_id
            offer.company_id = company_id
            offer.total_price = Decimal(str(total_price))
            offer.delivery_time = delivery_time
            offer.description = description
            
            db.session.add(offer)
            
            # Get or create company balance
            company_balance = CompanyBalance.query.filter_by(company_id=company_id).first()
            if not company_balance:
                company_balance = CompanyBalance()
                company_balance.company_id = company_id
                company_balance.current_balance = Decimal('0.0')
                db.session.add(company_balance)
            
            # Update company balance (add the offer value)
            if total_price is not None:
                company_balance.current_balance += Decimal(str(total_price))
            else:
                return {'error': 'Total price is required'}
            
            db.session.commit()
            
            return {
                'success': True,
                'message': f'Offer created successfully for order {order_id}',
                'offer_details': {
                    'total_price': float(total_price) if total_price is not None else 0,
                    'delivery_time': delivery_time if delivery_time is not None else '',
                    'description': description if description is not None else '',
                    'status': 'pending'
                }
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating offer: {str(e)}")
            return {'error': f'Error creating offer: {str(e)}'}
    
    def _get_company_balance(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get the current balance of the company"""
        try:
            company_balance = CompanyBalance.query.filter_by(company_id=company_id).first()
            
            if company_balance:
                return {
                    'success': True,
                    'balance': float(company_balance.current_balance),
                    'currency': getattr(company_balance, 'currency', 'EGP'),
                    'last_updated': company_balance.updated_at.isoformat() if company_balance.updated_at else None
                }
            else:
                return {
                    'success': True,
                    'balance': 0.0,
                    'currency': 'EGP',
                    'last_updated': None,
                    'message': 'No balance record found for this company'
                }
                
        except Exception as e:
            logger.error(f"Error getting company balance: {str(e)}")
            return {'error': f'Error getting company balance: {str(e)}'}
    
    def _get_company_registration_status(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get the company's registration status and approval information"""
        try:
            company = Company.query.get(company_id)
            
            if not company:
                return {'error': 'Company not found'}
            
            # Calculate completion percentage
            required_fields = [
                'name_en', 'name_ar', 'email', 'phone', 'address', 'sector',
                'legal_type', 'commercial_registration', 'contact_person_name',
                'contact_person_email', 'contact_person_position', 'owner_name',
                'website', 'office_phone', 'mobile_contact', 'tax_id', 'vat_number',
                'founded_year', 'employees_count', 'registered_address',
                'certifications', 'operating_countries', 'bank_name', 'account_name'
            ]
            
            completed_fields = sum(1 for field in required_fields if getattr(company, field, None))
            completion_percentage = (completed_fields / len(required_fields)) * 100
            
            # Required documents
            required_docs = [
                'commercial_registration_doc', 'tax_card_doc', 'e_invoice_proof_doc',
                'logo_doc', 'letterhead_doc', 'bank_letter_doc', 'owner_id_doc',
                'product_catalog_doc', 'quality_certificates_doc'
            ]
            
            uploaded_docs = sum(1 for doc in required_docs if getattr(company, doc, None))
            docs_completion = (uploaded_docs / len(required_docs)) * 100
            
            return {
                'success': True,
                'company_name': company.name_ar or company.name_en,
                'is_approved': company.is_approved,
                'is_active': company.is_active,
                'registration_date': company.created_at.isoformat() if company.created_at else None,
                'approval_date': company.updated_at.isoformat() if company.is_approved and company.updated_at else None,
                'completion_percentage': round(completion_percentage, 1),
                'documents_completion': round(docs_completion, 1),
                'status': 'مُعتمدة' if company.is_approved else 'قيد المراجعة',
                'status_en': 'Approved' if company.is_approved else 'Under Review',
                'missing_info_count': len(required_fields) - completed_fields,
                'missing_docs_count': len(required_docs) - uploaded_docs
            }
            
        except Exception as e:
            logger.error(f"Error getting company registration status: {str(e)}")
            return {'error': f'Error getting registration status: {str(e)}'}
    
    def _get_company_documents_status(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get the status of all required company documents"""
        try:
            company = Company.query.get(company_id)
            
            if not company:
                return {'error': 'Company not found'}
            
            documents = {
                'commercial_registration_doc': {
                    'name_ar': 'وثيقة السجل التجاري',
                    'name_en': 'Commercial Registration Document',
                    'uploaded': bool(company.commercial_registration_doc),
                    'filename': company.commercial_registration_doc
                },
                'tax_card_doc': {
                    'name_ar': 'البطاقة الضريبية',
                    'name_en': 'Tax Card Document',
                    'uploaded': bool(company.tax_card_doc),
                    'filename': company.tax_card_doc
                },
                'e_invoice_proof_doc': {
                    'name_ar': 'إثبات الفاتورة الإلكترونية',
                    'name_en': 'E-Invoice Proof Document',
                    'uploaded': bool(company.e_invoice_proof_doc),
                    'filename': company.e_invoice_proof_doc
                },
                'logo_doc': {
                    'name_ar': 'شعار الشركة',
                    'name_en': 'Company Logo',
                    'uploaded': bool(company.logo_doc),
                    'filename': company.logo_doc
                },
                'letterhead_doc': {
                    'name_ar': 'ورقة رسمية للشركة',
                    'name_en': 'Company Letterhead',
                    'uploaded': bool(company.letterhead_doc),
                    'filename': company.letterhead_doc
                },
                'bank_letter_doc': {
                    'name_ar': 'خطاب بنكي',
                    'name_en': 'Bank Letter',
                    'uploaded': bool(company.bank_letter_doc),
                    'filename': company.bank_letter_doc
                },
                'owner_id_doc': {
                    'name_ar': 'هوية المالك',
                    'name_en': 'Owner ID Document',
                    'uploaded': bool(company.owner_id_doc),
                    'filename': company.owner_id_doc
                },
                'product_catalog_doc': {
                    'name_ar': 'كتالوج المنتجات',
                    'name_en': 'Product Catalog',
                    'uploaded': bool(company.product_catalog_doc),
                    'filename': company.product_catalog_doc
                },
                'quality_certificates_doc': {
                    'name_ar': 'شهادات الجودة',
                    'name_en': 'Quality Certificates',
                    'uploaded': bool(company.quality_certificates_doc),
                    'filename': company.quality_certificates_doc
                }
            }
            
            uploaded_count = sum(1 for doc in documents.values() if doc['uploaded'])
            total_count = len(documents)
            
            return {
                'success': True,
                'documents': documents,
                'uploaded_count': uploaded_count,
                'total_count': total_count,
                'completion_percentage': round((uploaded_count / total_count) * 100, 1),
                'missing_documents': [doc_key for doc_key, doc_info in documents.items() if not doc_info['uploaded']]
            }
            
        except Exception as e:
            logger.error(f"Error getting company documents status: {str(e)}")
            return {'error': f'Error getting documents status: {str(e)}'}
    
    def _get_company_information(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed company information"""
        try:
            company = Company.query.get(company_id)
            
            if not company:
                return {'error': 'Company not found'}
            
            return {
                'success': True,
                'basic_info': {
                    'name_ar': company.name_ar,
                    'name_en': company.name_en,
                    'email': company.email,
                    'phone': company.phone,
                    'address': company.address,
                    'sector': company.sector,
                    'legal_type': company.legal_type
                },
                'registration_info': {
                    'commercial_registration': company.commercial_registration,
                    'tax_id': company.tax_id,
                    'vat_number': company.vat_number,
                    'founded_year': company.founded_year
                },
                'contact_info': {
                    'contact_person_name': company.contact_person_name,
                    'contact_person_email': company.contact_person_email,
                    'contact_person_position': company.contact_person_position,
                    'office_phone': company.office_phone,
                    'mobile_contact': company.mobile_contact
                },
                'business_info': {
                    'owner_name': company.owner_name,
                    'website': company.website,
                    'employees_count': company.employees_count,
                    'registered_address': company.registered_address,
                    'certifications': company.certifications,
                    'operating_countries': company.operating_countries
                },
                'banking_info': {
                    'bank_name': company.bank_name,
                    'account_name': company.account_name
                },
                'status_info': {
                    'is_approved': company.is_approved,
                    'is_active': company.is_active,
                    'created_at': company.created_at.isoformat() if company.created_at else None,
                    'updated_at': company.updated_at.isoformat() if company.updated_at else None
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting company information: {str(e)}")
            return {'error': f'Error getting company information: {str(e)}'}
    
    def _get_inventory_status(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get company inventory status including stock levels, product counts, and inventory analytics"""
        try:
            from models import Product
            
            # Get all products for the company
            products = Product.query.filter_by(company_id=company_id).all()
            
            if not products:
                return {
                    'success': True,
                    'message': 'لا توجد منتجات في المخزون حالياً',
                    'total_products': 0,
                    'in_stock': 0,
                    'low_stock': 0,
                    'out_of_stock': 0,
                    'total_value': 0
                }
            
            # Calculate inventory statistics
            total_products = len(products)
            in_stock_count = 0
            low_stock_count = 0
            out_of_stock_count = 0
            total_value = 0
            
            low_stock_products = []
            out_of_stock_products = []
            
            for product in products:
                quantity = getattr(product, 'quantity', 0) or 0
                min_quantity = getattr(product, 'min_quantity', 0) or 0
                price = getattr(product, 'price', 0) or 0
                
                total_value += quantity * price
                
                if quantity == 0:
                    out_of_stock_count += 1
                    out_of_stock_products.append({
                        'name': getattr(product, 'name', ''),
                        'sku': getattr(product, 'sku', ''),
                        'category': getattr(product, 'category', '')
                    })
                elif quantity <= min_quantity and min_quantity > 0:
                    low_stock_count += 1
                    low_stock_products.append({
                        'name': getattr(product, 'name', ''),
                        'sku': getattr(product, 'sku', ''),
                        'quantity': quantity,
                        'min_quantity': min_quantity,
                        'category': getattr(product, 'category', '')
                    })
                else:
                    in_stock_count += 1
            
            return {
                'success': True,
                'message': f'إجمالي المنتجات: {total_products}، متوفر: {in_stock_count}، مخزون منخفض: {low_stock_count}، نفذ المخزون: {out_of_stock_count}',
                'total_products': total_products,
                'in_stock': in_stock_count,
                'low_stock': low_stock_count,
                'out_of_stock': out_of_stock_count,
                'total_value': round(total_value, 2),
                'low_stock_products': low_stock_products[:5],  # Top 5 low stock items
                'out_of_stock_products': out_of_stock_products[:5]  # Top 5 out of stock items
            }
            
        except Exception as e:
            logger.error(f"Error getting inventory status: {str(e)}")
            return {'error': f'فشل في الحصول على حالة المخزون: {str(e)}'}
    
    def _get_product_availability(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """البحث عن توفر منتج معين أو فئة منتجات في المخزون"""
        try:
            from models import Product
            from sqlalchemy import or_
            
            search_query = args.get('search_query') if args else None
            
            # Build query
            query = Product.query.filter_by(company_id=company_id)
            
            if search_query:
                query = query.filter(
                    or_(
                        Product.name.ilike(f'%{search_query}%'),
                        getattr(Product, 'sku', Product.name).ilike(f'%{search_query}%'),
                        getattr(Product, 'description', Product.name).ilike(f'%{search_query}%'),
                        getattr(Product, 'category', Product.name).ilike(f'%{search_query}%')
                    )
                )
            
            products = query.all()
            
            if not products:
                search_term = search_query or "المنتجات المطلوبة"
                return {
                    'success': True,
                    'message': f'لم يتم العثور على {search_term} في المخزون',
                    'products': []
                }
            
            product_list = []
            for product in products:
                quantity = getattr(product, 'quantity', 0) or 0
                min_quantity = getattr(product, 'min_quantity', 0) or 0
                
                status = "متوفر"
                if quantity == 0:
                    status = "نفذ المخزون"
                elif quantity <= min_quantity and min_quantity > 0:
                    status = "مخزون منخفض"
                
                product_list.append({
                    'name': getattr(product, 'name', ''),
                    'sku': getattr(product, 'sku', ''),
                    'category': getattr(product, 'category', ''),
                    'quantity': quantity,
                    'min_quantity': min_quantity,
                    'price': getattr(product, 'price', 0) or 0,
                    'status': status,
                    'location': getattr(product, 'location', ''),
                    'unit': getattr(product, 'unit', '')
                })
            
            return {
                'success': True,
                'message': f'تم العثور على {len(products)} منتج',
                'products': product_list
            }
            
        except Exception as e:
            logger.error(f"Error getting product availability: {str(e)}")
            return {'error': f'فشل في البحث عن المنتجات: {str(e)}'}
    
    def _get_customer_analytics(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """تحليل أنماط وسلوك العملاء للشركة"""
        try:
            analysis_type = args.get('analysis_type', 'patterns')
            time_period = args.get('time_period', 'last_3_months')
            
            # Calculate date range based on time_period
            end_date = datetime.now()
            if time_period == 'last_month':
                start_date = end_date - timedelta(days=30)
            elif time_period == 'last_3_months':
                start_date = end_date - timedelta(days=90)
            elif time_period == 'last_6_months':
                start_date = end_date - timedelta(days=180)
            elif time_period == 'last_year':
                start_date = end_date - timedelta(days=365)
            else:  # all_time
                start_date = None
            
            # Get orders for analysis
            orders_query = Order.query
            if start_date:
                orders_query = orders_query.filter(Order.created_at >= start_date)
            
            orders = orders_query.all()
            
            if analysis_type == 'patterns':
                return self._analyze_customer_patterns(orders, time_period)
            elif analysis_type == 'behavior':
                return self._analyze_customer_behavior(orders, time_period)
            elif analysis_type == 'retention':
                return self._analyze_customer_retention(orders, time_period)
            elif analysis_type == 'value':
                return self._analyze_customer_value(orders, time_period)
            else:
                return {'error': f'نوع التحليل غير مدعوم: {analysis_type}'}
                
        except Exception as e:
            logger.error(f"Error in customer analytics: {str(e)}")
            return {'error': f'فشل في تحليل العملاء: {str(e)}'}
    
    def _get_customer_behavior_analysis(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """تحليل تفصيلي لسلوك العملاء وتفضيلاتهم"""
        try:
            focus_area = args.get('focus_area', 'purchasing_patterns')
            customer_segment = args.get('customer_segment', 'all')
            
            # Get relevant data based on focus area
            orders = Order.query.all()
            
            if focus_area == 'purchasing_patterns':
                return self._analyze_purchasing_patterns(orders, customer_segment)
            elif focus_area == 'preferences':
                return self._analyze_customer_preferences(orders, customer_segment)
            elif focus_area == 'loyalty':
                return self._analyze_customer_loyalty(orders, customer_segment)
            elif focus_area == 'satisfaction':
                return self._analyze_customer_satisfaction(orders, customer_segment)
            else:
                return {'error': f'مجال التركيز غير مدعوم: {focus_area}'}
                
        except Exception as e:
            logger.error(f"Error in customer behavior analysis: {str(e)}")
            return {'error': f'فشل في تحليل سلوك العملاء: {str(e)}'}
    
    def _analyze_customer_patterns(self, orders: List[Order], time_period: str) -> Dict[str, Any]:
        """تحليل أنماط العملاء"""
        if not orders:
            return {
                'success': True,
                'message': 'لا توجد طلبات في الفترة المحددة',
                'patterns': {}
            }
        
        # Analyze order frequency patterns
        order_counts = {}
        total_orders = len(orders)
        
        # Group by day of week
        weekday_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
        weekday_names = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
        
        for order in orders:
            if order.created_at:
                weekday = order.created_at.weekday()
                weekday_counts[weekday] += 1
        
        # Find peak day
        peak_day = max(weekday_counts.keys(), key=lambda k: weekday_counts[k])
        
        return {
            'success': True,
            'message': f'تحليل أنماط العملاء لـ {total_orders} طلب في فترة {time_period}',
            'patterns': {
                'total_orders': total_orders,
                'peak_day': weekday_names[peak_day],
                'peak_day_orders': weekday_counts[peak_day],
                'weekday_distribution': {
                    weekday_names[i]: weekday_counts[i] for i in range(7)
                },
                'average_orders_per_day': round(total_orders / 7, 2)
            }
        }
    
    def _analyze_customer_behavior(self, orders: List[Order], time_period: str) -> Dict[str, Any]:
        """تحليل سلوك العملاء"""
        if not orders:
            return {
                'success': True,
                'message': 'لا توجد طلبات للتحليل',
                'behavior': {}
            }
        
        # Analyze order values and timing
        order_values = [float(order.total_amount) for order in orders if order.total_amount]
        avg_order_value = sum(order_values) / len(order_values) if order_values else 0
        
        # Status distribution
        status_counts = {}
        for order in orders:
            status = order.status or 'غير محدد'
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            'success': True,
            'message': f'تحليل سلوك العملاء لـ {len(orders)} طلب',
            'behavior': {
                'total_orders': len(orders),
                'average_order_value': round(avg_order_value, 2),
                'total_value': sum(order_values),
                'status_distribution': status_counts,
                'orders_with_value': len(order_values)
            }
        }
    
    def _analyze_customer_retention(self, orders: List[Order], time_period: str) -> Dict[str, Any]:
        """تحليل الاحتفاظ بالعملاء"""
        return {
            'success': True,
            'message': f'تحليل الاحتفاظ بالعملاء لفترة {time_period}',
            'retention': {
                'total_orders': len(orders),
                'analysis_period': time_period,
                'note': 'تحليل الاحتفاظ يتطلب بيانات العملاء التفصيلية'
            }
        }
    
    def _analyze_customer_value(self, orders: List[Order], time_period: str) -> Dict[str, Any]:
        """تحليل قيمة العملاء"""
        if not orders:
            return {
                'success': True,
                'message': 'لا توجد طلبات للتحليل',
                'value_analysis': {}
            }
        
        order_values = [float(order.total_amount) for order in orders if order.total_amount]
        
        if not order_values:
            return {
                'success': True,
                'message': 'لا توجد قيم للطلبات للتحليل',
                'value_analysis': {}
            }
        
        total_value = sum(order_values)
        avg_value = total_value / len(order_values)
        max_value = max(order_values)
        min_value = min(order_values)
        
        return {
            'success': True,
            'message': f'تحليل قيمة العملاء لـ {len(orders)} طلب',
            'value_analysis': {
                'total_value': round(total_value, 2),
                'average_order_value': round(avg_value, 2),
                'highest_order_value': round(max_value, 2),
                'lowest_order_value': round(min_value, 2),
                'total_orders': len(orders),
                'orders_with_value': len(order_values)
            }
        }
    
    def _analyze_purchasing_patterns(self, orders: List[Order], customer_segment: str) -> Dict[str, Any]:
        """تحليل أنماط الشراء"""
        return {
            'success': True,
            'message': f'تحليل أنماط الشراء لشريحة {customer_segment}',
            'purchasing_patterns': {
                'total_orders': len(orders),
                'customer_segment': customer_segment,
                'note': 'تحليل أنماط الشراء التفصيلي يتطلب بيانات المنتجات'
            }
        }
    
    def _analyze_customer_preferences(self, orders: List[Order], customer_segment: str) -> Dict[str, Any]:
        """تحليل تفضيلات العملاء"""
        return {
            'success': True,
            'message': f'تحليل تفضيلات العملاء لشريحة {customer_segment}',
            'preferences': {
                'total_orders': len(orders),
                'customer_segment': customer_segment,
                'note': 'تحليل التفضيلات يتطلب بيانات المنتجات والفئات'
            }
        }
    
    def _analyze_customer_loyalty(self, orders: List[Order], customer_segment: str) -> Dict[str, Any]:
        """تحليل ولاء العملاء"""
        return {
            'success': True,
            'message': f'تحليل ولاء العملاء لشريحة {customer_segment}',
            'loyalty': {
                'total_orders': len(orders),
                'customer_segment': customer_segment,
                'note': 'تحليل الولاء يتطلب تتبع العملاء عبر الطلبات المتعددة'
            }
        }
    
    def _analyze_customer_satisfaction(self, orders: List[Order], customer_segment: str) -> Dict[str, Any]:
        """تحليل رضا العملاء"""
        return {
            'success': True,
            'message': f'تحليل رضا العملاء لشريحة {customer_segment}',
            'satisfaction': {
                'total_orders': len(orders),
                'customer_segment': customer_segment,
                'note': 'تحليل الرضا يتطلب بيانات التقييمات والمراجعات'
            }
        }
    
    def _get_company_offers_status(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """الحصول على حالة جميع عروض الشركة"""
        try:
            status_filter = args.get('status_filter', 'all')
            limit = args.get('limit', 20)
            
            # Build query for company offers
            offers_query = Offer.query.filter_by(company_id=company_id)
            
            # Apply status filter if specified
            if status_filter != 'all':
                if hasattr(Offer, 'status'):
                    offers_query = offers_query.filter_by(status=status_filter)
            
            # Apply limit and order by creation date
            offers = offers_query.order_by(Offer.created_at.desc()).limit(limit).all()
            
            if not offers:
                return {
                    'success': True,
                    'message': 'لا توجد عروض للشركة حالياً',
                    'offers': [],
                    'total_count': 0
                }
            
            # Process offers data
            offers_data = []
            total_value = 0
            status_counts = {}
            
            for offer in offers:
                # Get order information
                order = Order.query.get(offer.order_id) if offer.order_id else None
                
                offer_status = getattr(offer, 'status', 'pending')
                status_counts[offer_status] = status_counts.get(offer_status, 0) + 1
                
                offer_value = float(offer.total_price) if offer.total_price else 0
                total_value += offer_value
                
                offers_data.append({
                    'id': offer.id,
                    'order_id': offer.order_id,
                    'order_name': order.order_name if order else 'غير محدد',
                    'total_price': offer_value,
                    'delivery_time': offer.delivery_time,
                    'description': offer.description or '',
                    'status': offer_status,
                    'created_at': offer.created_at.isoformat() if offer.created_at else None
                })
            
            return {
                'success': True,
                'message': f'تم العثور على {len(offers)} عرض للشركة',
                'offers': offers_data,
                'total_count': len(offers),
                'total_value': round(total_value, 2),
                'status_distribution': status_counts,
                'filter_applied': status_filter
            }
            
        except Exception as e:
            logger.error(f"Error getting company offers status: {str(e)}")
            return {'error': f'فشل في الحصول على حالة العروض: {str(e)}'}
    
    def _get_bills_summary(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get summary of company bills including totals, status breakdown, and recent bills"""
        limit = args.get('limit', 10)
        
        try:
            # Get all bills for the company
            bills = Bill.query.filter_by(company_id=company_id).all()
            
            # Calculate totals
            total_bills = len(bills)
            total_amount = sum(float(bill.total_amount) for bill in bills)
            paid_bills = [bill for bill in bills if bill.status == 'paid']
            pending_bills = [bill for bill in bills if bill.status == 'pending']
            overdue_bills = [bill for bill in bills if bill.status == 'overdue']
            
            paid_amount = sum(float(bill.total_amount) for bill in paid_bills)
            pending_amount = sum(float(bill.total_amount) for bill in pending_bills)
            overdue_amount = sum(float(bill.total_amount) for bill in overdue_bills)
            
            # Get recent bills
            recent_bills = Bill.query.filter_by(company_id=company_id).order_by(Bill.created_at.desc()).limit(limit).all()
            recent_bills_data = []
            
            for bill in recent_bills:
                recent_bills_data.append({
                    'id': bill.id,
                    'bill_number': bill.bill_number,
                    'client_name': bill.client.display_name if bill.client else 'Unknown Client',
                    'status': bill.status,
                    'total_amount': float(bill.total_amount),
                    'issue_date': bill.issue_date.isoformat() if bill.issue_date else None,
                    'due_date': bill.due_date.isoformat() if bill.due_date else None
                })
            
            return {
                'summary': {
                    'total_bills': total_bills,
                    'total_amount': total_amount,
                    'paid_count': len(paid_bills),
                    'paid_amount': paid_amount,
                    'pending_count': len(pending_bills),
                    'pending_amount': pending_amount,
                    'overdue_count': len(overdue_bills),
                    'overdue_amount': overdue_amount
                },
                'recent_bills': recent_bills_data
            }
        except Exception as e:
            logger.error(f"Error getting bills summary: {str(e)}")
            return {'error': f'Error getting bills summary: {str(e)}'}
    
    def _get_bill_details(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed information about a specific bill"""
        bill_id = args.get('bill_id')
        
        if not bill_id:
            return {'error': 'Bill ID is required'}
        
        try:
            bill = Bill.query.filter_by(id=bill_id, company_id=company_id).first()
            
            if not bill:
                return {'error': 'Bill not found'}
            
            # Get bill items
            bill_items = BillItem.query.filter_by(bill_id=bill.id).all()
            items_data = []
            
            for item in bill_items:
                items_data.append({
                    'id': item.id,
                    'product_name': item.product_name,
                    'description': item.description,
                    'quantity': float(item.quantity),
                    'unit_price': float(item.unit_price),
                    'total_price': float(item.total_price)
                })
            
            return {
                'bill': {
                    'id': bill.id,
                    'bill_number': bill.bill_number,
                    'client_name': bill.client.company_name if bill.client else 'Unknown Client',
                    'status': bill.status,
                    'total_amount': float(bill.total_amount),
                    'issue_date': bill.issue_date.isoformat() if bill.issue_date else None,
                    'due_date': bill.due_date.isoformat() if bill.due_date else None,
                    'created_at': bill.created_at.isoformat() if bill.created_at else None,
                    'order_id': bill.order_id
                },
                'items': items_data
            }
        except Exception as e:
            logger.error(f"Error getting bill details: {str(e)}")
            return {'error': f'Error getting bill details: {str(e)}'}
    
    def _mark_bill_as_paid(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Mark a bill as paid"""
        bill_id = args.get('bill_id')
        
        if not bill_id:
            return {'error': 'Bill ID is required'}
        
        try:
            bill = Bill.query.filter_by(id=bill_id, company_id=company_id).first()
            
            if not bill:
                return {'error': 'Bill not found'}
            
            if bill.status == 'paid':
                return {'message': 'Bill is already marked as paid'}
            
            bill.status = 'paid'
            db.session.commit()
            
            return {
                'success': True,
                'message': f'Bill {bill.bill_number} has been marked as paid',
                'bill': {
                    'id': bill.id,
                    'bill_number': bill.bill_number,
                    'status': bill.status,
                    'total_amount': float(bill.total_amount)
                }
            }
        except Exception as e:
            logger.error(f"Error marking bill as paid: {str(e)}")
            db.session.rollback()
            return {'error': f'Error marking bill as paid: {str(e)}'}
    
    def _generate_bills_from_orders(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate bills for orders that don't have bills yet"""
        try:
            # Get orders without bills
            orders_without_bills = Order.query.filter(
                Order.company_id == company_id,
                ~Order.id.in_(db.session.query(Bill.order_id).filter(Bill.order_id.isnot(None)))
            ).all()
            
            if not orders_without_bills:
                return {'message': 'No orders found that need bills generated'}
            
            generated_bills = []
            
            for order in orders_without_bills:
                # Create bill from order
                bill = Bill()
                bill.company_id = company_id
                bill.client_id = order.company_id if order.company_id else company_id
                bill.order_id = order.id
                bill.created_by_user_id = 1  # Default admin user, should be passed as parameter
                bill.bill_number = f"BILL-{datetime.now().strftime('%Y%m%d')}-{order.id}"
                bill.status = 'pending'
                bill.total_amount = order.total_amount or 0
                bill.issue_date = datetime.now().date()
                bill.due_date = datetime.now().date() + timedelta(days=30)
                
                db.session.add(bill)
                db.session.flush()  # Get the bill ID
                
                # Create bill items from order purchases
                purchases = Purchase.query.filter_by(order_id=order.id).all()
                for purchase in purchases:
                    bill_item = BillItem()
                    bill_item.bill_id = bill.id
                    bill_item.product_name = purchase.product.name if purchase.product else 'Unknown Product'
                    bill_item.description = purchase.product.description if purchase.product else ''
                    bill_item.quantity = purchase.quantity
                    bill_item.unit_price = purchase.unit_price
                    bill_item.total_price = purchase.total_price
                    db.session.add(bill_item)
                
                generated_bills.append({
                    'bill_id': bill.id,
                    'bill_number': bill.bill_number,
                    'order_id': order.id,
                    'client_name': bill.client.company_name if bill.client else 'Unknown Client',
                    'total_amount': float(bill.total_amount)
                })
            
            db.session.commit()
            
            return {
                'success': True,
                'message': f'Generated {len(generated_bills)} bills from orders',
                'generated_bills': generated_bills
            }
        except Exception as e:
            logger.error(f"Error generating bills from orders: {str(e)}")
            db.session.rollback()
            return {'error': f'Error generating bills from orders: {str(e)}'}
    
    def _create_order(self, company_id: int, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new order with products - matches the flask_app.py new_purchase functionality"""
        try:
            from models import User
            import json
            
            # Get order details (Panel 1)
            order_name = args.get('order_name', 'New Order')
            description = args.get('description', '')
            sector = args.get('sector', 'Other')
            order_type = args.get('order_type', 'direct')
            
            # Get delivery details (Panel 3)
            delivery_date_str = args.get('delivery_date')
            delivery_date = None
            if delivery_date_str:
                try:
                    if isinstance(delivery_date_str, str):
                        delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
                    else:
                        delivery_date = delivery_date_str
                except ValueError:
                    pass
            
            delivery_time = args.get('delivery_time', '')
            delivery_address = args.get('delivery_address', '')
            delivery_notes = args.get('delivery_notes', '')
            receiver_name = args.get('receiver_name', '')
            receiver_phone = args.get('receiver_phone', '')
            
            # Get payment details (Panel 4)
            payment_way = args.get('payment_way', '')
            payment_steps_data = args.get('payment_steps', [])
            payment_steps_json = json.dumps(payment_steps_data) if payment_steps_data else None
            
            # Get settings (Panel 5)
            direct_negotiation = args.get('direct_negotiation', False)
            accept_unregistered_suppliers = args.get('accept_unregistered_suppliers', False)
            max_suppliers = args.get('max_suppliers', 10)
            
            # Get products (Panel 2)
            products = args.get('products', [])
            
            # Smart validation - ask for missing critical information
            missing_info = []
            if not order_name or order_name == 'New Order':
                missing_info.append('order name')
            if not sector or sector == 'Other':
                missing_info.append('sector/industry')
            if not delivery_date:
                missing_info.append('delivery date')
            if not delivery_address:
                missing_info.append('delivery address')
            if not products:
                missing_info.append('product details')
            if not payment_way:
                missing_info.append('payment method')
            
            # Check product details
            for i, product in enumerate(products):
                if not product.get('product_name') and not product.get('part_name'):
                    missing_info.append(f'product {i+1} name')
                if not product.get('quantity'):
                    missing_info.append(f'product {i+1} quantity')
                if not product.get('unit'):
                    missing_info.append(f'product {i+1} unit')
            
            if missing_info:
                return {
                    'success': False,
                    'missing_fields': missing_info,
                    'message': f'I need more information to create your order. Please provide: {", ".join(missing_info)}. What additional details can you share?'
                }
            
            # Get user for this company
            user = User.query.filter_by(company_id=company_id).first()
            if not user:
                return {'error': 'No user found for this company'}
            
            # Create the order with all fields matching flask_app.py
            order = Order()
            order.user_id = user.id
            order.company_id = company_id
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
            order.status = 'pending'
            order.priority = 'medium'
            
            db.session.add(order)
            db.session.flush()  # Get the order ID
            
            # Create purchases for each product
            total_amount = Decimal('0.00')
            created_products = []
            
            for product in products:
                # Handle both product_name and part_name for compatibility
                product_name = product.get('product_name') or product.get('part_name')
                
                # Convert max_price_per_unit to float if provided
                max_price = None
                if product.get('max_price_per_unit'):
                    try:
                        max_price = float(product['max_price_per_unit'])
                    except (ValueError, TypeError):
                        max_price = None
                
                purchase = Purchase()
                purchase.order_id = order.id
                purchase.sector = sector
                purchase.quantity = int(product['quantity'])
                purchase.part_name = product_name
                purchase.description = product.get('technical_specs') or product.get('description', '')
                purchase.technical_specs = product.get('technical_specs', '')
                purchase.unit = product.get('unit', 'pcs')
                purchase.max_price_per_unit = max_price
                purchase.product_code = product.get('product_code', '')
                purchase.best_supplier = product.get('best_supplier', '')
                purchase.uploaded_file = None  # File uploads handled separately
                
                db.session.add(purchase)
                
                # Calculate total if price is provided
                if max_price:
                    product_total = Decimal(str(purchase.quantity)) * Decimal(str(max_price))
                    total_amount += product_total
                else:
                    product_total = Decimal('0.00')
                
                created_products.append({
                    'product_name': purchase.part_name,
                    'quantity': purchase.quantity,
                    'unit': purchase.unit,
                    'max_price_per_unit': max_price,
                    'total': float(product_total) if product_total else 0.00
                })
            
            # Update order total
            order.total_amount = total_amount
            
            db.session.commit()
            
            return {
                'success': True,
                'order_id': order.id,
                'order_name': order.order_name,
                'sector': order.sector,
                'delivery_date': order.delivery_date.isoformat() if order.delivery_date else None,
                'delivery_address': order.delivery_address,
                'total_amount': float(total_amount),
                'products_count': len(created_products),
                'products': created_products,
                'message': f'✅ Order "{order_name}" has been created successfully with {len(created_products)} product(s). Order ID: {order.id}'
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating order: {str(e)}")
            return {'error': f'Error creating order: {str(e)}'}

agentic_ai_service = AgenticAIService()