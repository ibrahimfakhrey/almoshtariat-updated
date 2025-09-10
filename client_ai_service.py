import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Union
from flask import current_app
from models import db, User, Company, Order, Package, CompanyBalance

import os
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Client-specific AI configuration
class ClientAIConfig:
    def __init__(self):
        # Initialize Google Gemini client with client-specific API key
        self.api_key = "AIzaSyDsrWXnC85p1suLt39IAzWmhxUcXFQJMO0"
        
        # Configure Gemini client
        try:
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            print(f"Warning: Client Gemini client initialization failed: {e}")
            self.client = None
        
        # Model configuration - using Gemini 1.5 Flash for better performance
        self.model_name = "gemini-1.5-flash"
        self.model = self.client  # For backward compatibility
    
    def generate_content(self, prompt, max_tokens=200, temperature=0.7):
        """Generate content using Google Gemini for client"""
        if self.client is None:
            raise Exception("Client Gemini client not initialized")
            
        try:
            # Configure generation parameters
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature
            )
            
            response = self.client.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Log token usage with estimation
            prompt_length = len(str(prompt))
            response_length = len(response.text) if response.text else 0
            estimated_input_tokens = prompt_length // 4  # Rough estimation: 4 chars per token
            estimated_output_tokens = response_length // 4
            logger.info(f"Client Gemini API Call - Model: {self.model_name}, "
                       f"Estimated Input Tokens: {estimated_input_tokens}, "
                       f"Estimated Output Tokens: {estimated_output_tokens}, "
                       f"Estimated Total: {estimated_input_tokens + estimated_output_tokens}")
            
            return response.text if response.text else ""
            
        except Exception as e:
            logger.error(f"Client Gemini API error: {str(e)}")
            raise Exception(f"Client AI generation failed: {str(e)}")
    
    def is_configured(self):
        """Check if client AI is properly configured"""
        return self.client is not None and self.api_key is not None

client_ai_config = ClientAIConfig()

class ClientAIAnalysisService:
    def __init__(self):
        self.ai_config = client_ai_config
    
    def analyze_user_data(self, user_id, query, language='en', conversation_history=None):
        """Analyze user data and provide insights with conversation context, or answer general questions"""
        if not self.ai_config.is_configured():
            error_msg = "خدمة الذكاء الاصطناعي غير مُكوّنة. يرجى الاتصال بالمسؤول." if language == 'ar' else "AI service not configured. Please contact administrator."
            return {"error": error_msg}
        
        try:
            # Get user data
            user = User.query.get(user_id)
            if not user:
                error_msg = "المستخدم غير موجود" if language == 'ar' else "User not found"
                return {"error": error_msg}
            
            # Determine if this is a user-specific query or general question
            is_user_specific = self._is_user_specific_query(query, language)
            
            # Get system message based on language
            system_message = self._get_system_message_user(language)
            
            # Build conversation messages
            messages: List[Dict[str, Any]] = [{"role": "system", "content": system_message}]
            
            # Add conversation history if provided
            if conversation_history:
                for msg in conversation_history:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        messages.append({"role": str(msg["role"]), "content": str(msg["content"])})
            
            # Create context-aware prompt
            if is_user_specific:
                # User-specific query - always include user data summary
                orders = Order.query.filter_by(user_id=user_id).all()
                data_summary = self._prepare_user_data_summary(user, orders)
                prompt = self._create_user_analysis_prompt(data_summary, query, language)
            else:
                # General question - more conversational
                prompt = self._create_conversational_prompt(query, language)
            
            messages.append({"role": "user", "content": prompt})
            
            # Prepare the full conversation for Gemini
            conversation_text = ""
            for msg in messages:
                if msg["role"] == "system":
                    conversation_text += f"System: {msg['content']}\n\n"
                elif msg["role"] == "user":
                    conversation_text += f"User: {msg['content']}\n\n"
                elif msg["role"] == "assistant":
                    conversation_text += f"Assistant: {msg['content']}\n\n"
            
            # Get AI response from OpenAI
            response = self.ai_config.generate_content(
                conversation_text,
                max_tokens=200,
                temperature=0.8
            )

            return {
                "response": response,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            import traceback
            current_app.logger.error(f"AI Analysis Error: {str(e)}")
            current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
            error_msg = "فشل في تحليل البيانات. يرجى المحاولة مرة أخرى." if language == 'ar' else "Failed to analyze data. Please try again."
            return {"error": error_msg}
    
    def analyze_company_data(self, company_id, query, language='en', conversation_history=None):
        """Analyze company data and provide business insights, or answer general questions"""
        if not self.ai_config.is_configured():
            error_msg = "خدمة الذكاء الاصطناعي غير مُكوّنة. يرجى الاتصال بالمسؤول." if language == 'ar' else "AI service not configured. Please contact administrator."
            return {"error": error_msg}
        
        try:
            # Get company data
            company = Company.query.get(company_id)
            if not company:
                error_msg = "الشركة غير موجودة" if language == 'ar' else "Company not found"
                return {"error": error_msg}
            
            # Determine query type
            is_order_management = self._is_order_management_query(query, language)
            is_company_specific = self._is_company_specific_query(query, language)
            
            # Get system message based on language
            system_message = self._get_system_message_company(language)
            
            # Build conversation messages
            messages: List[Dict[str, Any]] = [{"role": "system", "content": system_message}]
            
            # Add conversation history if provided
            if conversation_history:
                for msg in conversation_history:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        messages.append({"role": str(msg["role"]), "content": str(msg["content"])})
            
            # Create context-aware prompt
            if (is_order_management or is_company_specific) and not conversation_history:
                # First message with company-specific data - include full data summary
                orders = Order.query.filter_by(company_id=company_id).all()
                packages = Package.query.filter_by(company_id=company_id).all()
                balance = CompanyBalance.query.filter_by(company_id=company_id).first()
                data_summary = self._prepare_company_data_summary(company, orders, packages, balance)
                
                if is_order_management:
                    prompt = self._create_order_management_prompt(data_summary, query, language)
                else:
                    prompt = self._create_company_analysis_prompt(data_summary, query, language)
            else:
                # Follow-up message or general question - more conversational
                prompt = self._create_conversational_prompt(query, language)
            
            messages.append({"role": "user", "content": prompt})
            
            # Convert messages to conversation text for Gemini
            conversation_text = "\n\n".join([f"{msg['role'].title()}: {msg['content']}" for msg in messages]) + "\n\n"
            
            # Get AI response from OpenAI
            response = self.ai_config.generate_content(
                conversation_text,
                max_tokens=200,
                temperature=0.7
            )

            return {
                "response": response,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            current_app.logger.error(f"AI Analysis Error: {str(e)}")
            error_msg = "فشل في تحليل البيانات. يرجى المحاولة مرة أخرى." if language == 'ar' else "Failed to analyze data. Please try again."
            return {"error": error_msg}
    
    def _prepare_user_data_summary(self, user, orders):
        """Prepare user data summary for AI analysis"""
        total_orders = len(orders)
        
        # Calculate total spent from accepted offers
        total_spent = 0
        for order in orders:
            if order.offers:
                # Get the accepted offer or the first offer if none accepted
                accepted_offers = [offer for offer in order.offers if offer.status == 'accepted']
                if accepted_offers:
                    total_spent += accepted_offers[0].total_price if accepted_offers[0].total_price else 0
                elif order.offers:
                    # If no accepted offers, use the first offer for estimation
                    total_spent += order.offers[0].total_price if order.offers[0].total_price else 0
        
        recent_orders = [order for order in orders if order.created_at and order.created_at > datetime.now() - timedelta(days=30)]
        
        order_statuses = {}
        for order in orders:
            status = order.status or 'unknown'
            order_statuses[status] = order_statuses.get(status, 0) + 1
        
        # Prepare detailed order information
        detailed_orders = []
        for order in orders[-10:]:  # Last 10 orders
            order_info = {
                "id": order.id,
                "name": order.order_name or f"Order #{order.id}",
                "status": order.status or 'pending',
                "created_at": order.created_at.strftime('%Y-%m-%d %H:%M') if order.created_at else 'Unknown',
                "delivery_date": order.delivery_date.strftime('%Y-%m-%d') if order.delivery_date else 'Not specified',
                "priority": order.priority or 'medium',
                "sector": order.sector or 'general',
                "payment_method": order.payment_way or 'not specified',
                "offers_count": len(order.offers) if order.offers else 0,
                "purchases_count": len(order.purchases) if order.purchases else 0
            }
            
            # Add offer details if available
            if order.offers:
                accepted_offers = [offer for offer in order.offers if offer.status == 'accepted']
                if accepted_offers:
                    offer = accepted_offers[0]
                    order_info["accepted_offer"] = {
                        "company_name": offer.company.name_ar if offer.company else 'Unknown Company',
                        "total_price": float(offer.total_price) if offer.total_price else 0,
                        "status": offer.status
                    }
                else:
                    # Show best offer if no accepted offers
                    best_offer = min(order.offers, key=lambda x: x.total_price if x.total_price else 0)
                    order_info["best_offer"] = {
                        "company_name": best_offer.company.name_ar if best_offer.company else 'Unknown Company',
                        "total_price": float(best_offer.total_price) if best_offer.total_price else 0,
                        "status": best_offer.status
                    }
            
            # Add purchase details if available
            if order.purchases:
                order_info["key_items"] = []
                for purchase in order.purchases[:3]:  # First 3 items
                    order_info["key_items"].append({
                        "name": purchase.part_name or 'Unknown Item',
                        "quantity": purchase.quantity or 1,
                        "specifications": purchase.technical_specs or 'No specifications'
                    })
            
            detailed_orders.append(order_info)
        
        return {
            "user_info": {
                "username": user.username,
                "email": user.email,
                "registration_date": None  # User model doesn't have created_at field
            },
            "order_summary": {
                "total_orders": total_orders,
                "total_spent": float(total_spent),
                "recent_orders_count": len(recent_orders),
                "order_statuses": order_statuses
            },
            "detailed_orders": detailed_orders
        }
    
    def _prepare_company_data_summary(self, company, orders, packages, balance):
        """Prepare comprehensive company data summary for AI analysis"""
        total_orders = len(orders)
        
        # Calculate total revenue from accepted offers
        total_revenue = 0
        for order in orders:
            if order.offers:
                # Get accepted offers for this company
                company_offers = [offer for offer in order.offers if offer.company_id == company.id and offer.status == 'accepted']
                if company_offers:
                    total_revenue += sum(offer.total_price if offer.total_price else 0 for offer in company_offers)
        
        recent_orders = [order for order in orders if order.created_at and order.created_at > datetime.now() - timedelta(days=30)]
        average_order_value = total_revenue / total_orders if total_orders > 0 else 0
        
        order_statuses = {}
        for order in orders:
            status = order.status or 'unknown'
            order_statuses[status] = order_statuses.get(status, 0) + 1
        
        # Prepare detailed orders data with business analysis
        orders_data = []
        for order in orders[:20]:  # Last 20 orders
            # Calculate potential profitability
            order_value = 0
            if order.offers and len(order.offers) > 0:
                order_value = order.offers[0].total_price if order.offers[0].total_price else 0
            estimated_cost = order_value * 0.7  # Assume 70% cost ratio
            estimated_profit = order_value - estimated_cost
            profit_margin = (estimated_profit / order_value * 100) if order_value > 0 else 0
            
            # Analyze delivery feasibility
            delivery_urgency = 'high' if order.priority in ['high', 'urgent'] else 'medium' if order.priority == 'medium' else 'low'
            
            # Get purchase details for better analysis
            purchases_info = []
            if hasattr(order, 'purchases') and order.purchases:
                for purchase in order.purchases:
                    purchases_info.append({
                        'part_name': purchase.part_name if hasattr(purchase, 'part_name') else 'Unknown',
                        'quantity': purchase.quantity if hasattr(purchase, 'quantity') else 0,
                        'unit': purchase.unit if hasattr(purchase, 'unit') else '',
                        'max_price_per_unit': purchase.max_price_per_unit if hasattr(purchase, 'max_price_per_unit') else 0,
                        'description': (purchase.description[:100] + '...') if hasattr(purchase, 'description') and purchase.description and len(purchase.description) > 100 else (purchase.description if hasattr(purchase, 'description') else '')
                    })
            
            order_data = {
                'id': order.id,
                'name': order.order_name if hasattr(order, 'order_name') else 'Unknown Order',
                'status': order.status,
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M') if order.created_at else 'Unknown',
                'sector': order.sector if hasattr(order, 'sector') else 'Unknown',
                'priority': order.priority if hasattr(order, 'priority') else 'medium',
                'delivery_urgency': delivery_urgency,
                'offers_count': len(order.offers),
                'total_value': order_value,
                'estimated_profit': round(estimated_profit, 2),
                'profit_margin': round(profit_margin, 2),
                'delivery_date': order.delivery_date.strftime('%Y-%m-%d') if hasattr(order, 'delivery_date') and order.delivery_date else None,
                'delivery_address': order.delivery_address if hasattr(order, 'delivery_address') else None,
                'payment_way': order.payment_way if hasattr(order, 'payment_way') else None,
                'direct_negotiation': order.direct_negotiation if hasattr(order, 'direct_negotiation') else False,
                'purchases': purchases_info[:3],  # First 3 purchases for context
                'purchases_count': len(purchases_info),
                'description': (order.description[:200] + '...') if hasattr(order, 'description') and order.description and len(order.description) > 200 else (order.description if hasattr(order, 'description') else '')
            }
            orders_data.append(order_data)
        
        package_summary = {
            "total_packages": len(packages),
            "active_packages": len([p for p in packages if hasattr(p, 'is_active') and p.is_active]),
            "package_types": list(set(p.package_type for p in packages if hasattr(p, 'package_type') and p.package_type))
        }
        
        balance_info = {
            "current_balance": float(balance.current_balance) if balance else 0,
            "currency": balance.currency if balance else 'EGP'
        }
        
        # Calculate business metrics
        pending_orders = [o for o in orders if o.status == 'pending']
        accepted_orders = [o for o in orders if o.status == 'accepted']
        completed_orders = [o for o in orders if o.status == 'completed']
        
        return {
            "company_info": {
                "name": company.name_ar or company.name_en or "Unknown Company",
                "email": company.email,
                "registration_date": company.created_at.isoformat() if company.created_at else None
            },
            "business_summary": {
                "total_orders": total_orders,
                "pending_orders_count": len(pending_orders),
                "accepted_orders_count": len(accepted_orders),
                "completed_orders_count": len(completed_orders),
                "total_revenue": float(total_revenue),
                "average_order_value": average_order_value,
                "recent_orders_count": len(recent_orders),
                "order_statuses": order_statuses,
                "packages": package_summary,
                "balance": balance_info,
                "orders": orders_data
            }
        }
    
    def _get_system_message_user(self, language):
        """Get system message for user analysis based on language"""
        if language == 'ar':
            return """أنت شلبي، مساعد ذكي ومفيد يمكنه التحدث في أي موضوع والمساعدة في تحليل البيانات الشخصية والتجارية. أنت ودود ومحادث وتقدم رؤى قيمة.
            
خصائصك:
- اسمك شلبي وتعرف نفسك بهذا الاسم
- تتحدث بطريقة طبيعية ومحادثة في أي موضوع
- تجيب على الأسئلة العامة بمعرفة واسعة ومفيدة
- تحلل البيانات الشخصية عندما يُطلب منك ذلك
- تقدم إجابات متنوعة ومرنة
- تطرح أسئلة متابعة عند الحاجة
- تقدم خيارات وبدائل متعددة
- تشرح الأمور بطرق مختلفة حسب السياق
- تتذكر السياق السابق للمحادثة
- تقدم أمثلة عملية وتوضيحات
- تساعد في المواضيع العامة مثل التكنولوجيا، العلوم، الثقافة، النصائح، إلخ

مهم جداً: يجب أن تكون إجاباتك قصيرة ومختصرة ومباشرة. لا تكتب فقرات طويلة. اجعل الإجابة في 2-3 جمل كحد أقصى.

يجب أن تكون جميع الردود باللغة العربية وبأسلوب محادثة طبيعي."""
        else:
            return """You are Shalaby, a smart and helpful assistant who can discuss any topic and help with personal and business data analysis. You are friendly, conversational, and provide valuable insights.
            
Your characteristics:
- Your name is Shalaby and you introduce yourself with this name
- Speak naturally and conversationally about any topic
- Answer general questions with broad, helpful knowledge
- Analyze personal data when specifically requested
- Provide varied and flexible responses
- Ask follow-up questions when needed
- Offer multiple options and alternatives
- Explain things in different ways based on context
- Remember previous conversation context
- Provide practical examples and clarifications
- Help with general topics like technology, science, culture, advice, etc.

Very Important: Keep your responses short, concise, and direct. Don't write long paragraphs. Limit your answer to 2-3 sentences maximum.

Keep your responses natural and conversational."""
    
    def _get_system_message_company(self, language):
        """Get system message for company analysis based on language"""
        if language == 'ar':
            return "أنت محلل ذكاء أعمال. قدم رؤى استراتيجية وتحليل الاتجاهات وتوصيات قابلة للتنفيذ بناءً على بيانات الشركة. ركز على فرص النمو والكفاءة التشغيلية. مهم جداً: اجعل إجاباتك قصيرة ومختصرة (2-3 جمل كحد أقصى). يجب أن تكون جميع الردود باللغة العربية."
        else:
            return "You are a business intelligence analyst. Provide strategic insights, trends analysis, and actionable recommendations based on company data. Focus on growth opportunities and operational efficiency. Very Important: Keep your responses short and concise (2-3 sentences maximum)."
    
    def _create_user_analysis_prompt(self, data_summary, query, language='en'):
        """Create analysis prompt for user data"""
        if language == 'ar':
            detailed_orders_text = ""
            if data_summary.get('detailed_orders'):
                detailed_orders_text = "\n\nتفاصيل آخر الطلبات:\n"
                for order in data_summary['detailed_orders']:
                    detailed_orders_text += f"- طلب #{order['id']}: {order['name']} - الحالة: {order['status']} - التاريخ: {order['created_at']} - الأولوية: {order['priority']}\n"
                    if order.get('accepted_offer'):
                        detailed_orders_text += f"  العرض المقبول: {order['accepted_offer']['total_price']} جنيه من {order['accepted_offer']['company_name']}\n"
                    if order.get('purchased_items'):
                        detailed_orders_text += f"  المشتريات: {', '.join(order['purchased_items'])}\n"
            
            return f"""
المستخدم يسأل: {query}

معلومات حساب المستخدم التفصيلية:
{json.dumps(data_summary, indent=2, ensure_ascii=False)}

السياق والتفاصيل المطلوبة للتحليل:
- إجمالي عدد الطلبات: {data_summary.get('total_orders', 0)}
- إجمالي المبلغ المنفق: {data_summary.get('total_spent', 0)} جنيه
- متوسط قيمة الطلب: {data_summary.get('average_order_value', 0)} جنيه
- آخر طلب: {data_summary.get('last_order_date', 'غير متوفر')}
- الرصيد الحالي: {data_summary.get('current_balance', 0)} جنيه
- أكثر الشركات طلباً: {', '.join([comp.get('name', '') for comp in data_summary.get('top_companies', [])])}{detailed_orders_text}

يرجى تحليل بيانات المستخدم والإجابة على سؤاله بناءً على المعلومات المتاحة. يمكنك مساعدته في:
- فهم أنماط طلباته وعاداته الشرائية بناءً على التواريخ والمبالغ
- تحليل سلوك الإنفاق مقارنة بالمتوسطات وتقديم نصائح للتوفير
- اقتراح قرارات شراء أفضل بناءً على تاريخ الطلبات
- تحديد الاتجاهات والفرص من خلال تحليل البيانات الزمنية
- تقديم رؤى مخصصة بناءً على بياناته الفعلية

كن ودوداً ومحادثاً وقدم إجابة مفيدة ومخصصة وقصيرة (2-3 جمل كحد أقصى).
"""
        else:
            detailed_orders_text = ""
            if data_summary.get('detailed_orders'):
                detailed_orders_text = "\n\nDetailed Recent Orders:\n"
                for order in data_summary['detailed_orders']:
                    detailed_orders_text += f"- Order #{order['id']}: {order['name']} - Status: {order['status']} - Date: {order['created_at']} - Priority: {order['priority']}\n"
                    if order.get('accepted_offer'):
                        detailed_orders_text += f"  Accepted Offer: {order['accepted_offer']['total_price']} EGP from {order['accepted_offer']['company_name']}\n"
                    if order.get('purchased_items'):
                        detailed_orders_text += f"  Purchased Items: {', '.join(order['purchased_items'])}\n"
            
            return f"""
User asks: {query}

Detailed User Account Information:
{json.dumps(data_summary, indent=2)}

Context and Details Required for Analysis:
- Total Orders: {data_summary.get('total_orders', 0)}
- Total Amount Spent: {data_summary.get('total_spent', 0)} EGP
- Average Order Value: {data_summary.get('average_order_value', 0)} EGP
- Last Order Date: {data_summary.get('last_order_date', 'Not available')}
- Current Balance: {data_summary.get('current_balance', 0)} EGP
- Top Companies: {', '.join([comp.get('name', '') for comp in data_summary.get('top_companies', [])])}{detailed_orders_text}

Please analyze the user's data and answer their question based on the available information. You can help them with:
- Understanding their order patterns and purchasing habits based on dates and amounts
- Analyzing spending behavior compared to averages and offering saving tips
- Suggesting better purchasing decisions based on order history
- Identifying trends and opportunities through temporal data analysis
- Providing personalized insights based on their actual data

Be friendly, conversational, and provide a helpful, personalized, and short response (2-3 sentences maximum).
"""
    
    def _create_company_analysis_prompt(self, data_summary, query, language='en'):
        """Create analysis prompt for company data"""
        if language == 'ar':
            return f"""
طلب تحليل ذكاء الأعمال:

بيانات الشركة التفصيلية:
{json.dumps(data_summary, indent=2)}

المؤشرات الرئيسية للتحليل:
- إجمالي الطلبات: {data_summary.get('total_orders', 0)}
- إجمالي الإيرادات: {data_summary.get('total_revenue', 0)} جنيه
- متوسط قيمة الطلب: {data_summary.get('average_order_value', 0)} جنيه
- عدد الحزم النشطة: {len(data_summary.get('packages', []))}
- الرصيد الحالي: {data_summary.get('current_balance', {}).get('amount', 0)} جنيه
- آخر طلب: {data_summary.get('last_order_date', 'غير متوفر')}
- معدل نمو الطلبات: يحتاج تحليل زمني

استفسار الأعمال: {query}

يرجى تحليل بيانات أعمال هذه الشركة وتقديم رؤى استراتيجية متعلقة باستفسارها. ركز على:
- اتجاهات وأنماط الإيرادات بناءً على البيانات الفعلية
- كفاءة تنفيذ الطلبات مقارنة بالمعايير
- أداء الحزم وتأثيرها على الإيرادات
- مؤشرات الصحة المالية من خلال الرصيد والإيرادات
- فرص النمو بناءً على الاتجاهات الحالية
- التوصيات التشغيلية المحددة والقابلة للتطبيق

قدم توصيات أعمال استراتيجية وقابلة للتنفيذ وقصيرة (2-3 جمل كحد أقصى).
"""
        else:
            return f"""
Business Intelligence Analysis Request:

Detailed Company Data:
{json.dumps(data_summary, indent=2)}

Key Metrics for Analysis:
- Total Orders: {data_summary.get('total_orders', 0)}
- Total Revenue: {data_summary.get('total_revenue', 0)} EGP
- Average Order Value: {data_summary.get('average_order_value', 0)} EGP
- Active Packages: {len(data_summary.get('packages', []))}
- Current Balance: {data_summary.get('current_balance', {}).get('amount', 0)} EGP
- Last Order Date: {data_summary.get('last_order_date', 'Not available')}
- Order Growth Rate: Requires temporal analysis

Business Query: {query}

Please analyze this company's business data and provide strategic insights related to their query. Focus on:
- Revenue trends and patterns based on actual data
- Order fulfillment efficiency compared to benchmarks
- Package performance and impact on revenue
- Financial health indicators through balance and revenue
- Growth opportunities based on current trends
- Specific, actionable operational recommendations

Provide strategic, actionable business recommendations that are short and concise (2-3 sentences maximum).
"""

    def _create_conversational_prompt(self, query, language='en'):
        """Create a conversational prompt for general questions or follow-up questions"""
        if language == 'ar':
            return f"""المستخدم يسأل: {query}

السياق والتفاصيل:
- هذا سؤال عام أو محادثة طبيعية
- المستخدم قد يحتاج معلومات سريعة ومفيدة
- قد يكون السؤال متعلقاً بموضوع تقني، ثقافي، أو نصائح عامة
- إذا كان السؤال متعلقاً ببيانات شخصية، يجب توجيهه للسؤال بشكل أكثر تحديداً

يرجى الإجابة بطريقة محادثة طبيعية ومفيدة وقصيرة (2-3 جمل كحد أقصى). إذا كان السؤال عاماً، قدم إجابة مفيدة ومباشرة. إذا كان السؤال متعلقاً ببيانات المستخدم الشخصية (مثل طلباته أو مشترياته)، أخبره أنك تحتاج لمعلومات أكثر تحديداً أو اقترح عليه أن يسأل عن بياناته بشكل مباشر.

تذكر أن تكون ودوداً ومحادثاً ومفيداً في جميع الأحوال."""
        else:
            return f"""User asks: {query}

Context and Details:
- This is a general question or natural conversation
- User may need quick and helpful information
- Question might be about technical, cultural topics, or general advice
- If question is about personal data, should guide them to ask more specifically

Please respond in a natural, conversational, and helpful way that is short and concise (2-3 sentences maximum). If this is a general question, provide a useful and direct answer. If the question is about the user's personal data (like their orders or purchases), let them know you need more specific information or suggest they ask about their data directly.

Remember to be friendly, conversational, and helpful in all cases."""
    
    def _is_user_specific_query(self, query, language='en'):
        """Determine if the query is asking for user-specific data analysis"""
        if language == 'ar':
            user_specific_keywords = [
                # Direct possessive forms
                'طلباتي', 'طلبي', 'مشترياتي', 'إنفاقي', 'حسابي', 'بياناتي',
                'عروضي', 'فواتيري', 'مدفوعاتي', 'رصيدي',
                # Action verbs in past/present
                'أنفقت', 'اشتريت', 'طلبت', 'أطلب', 'أشتري', 'دفعت',
                # Question patterns
                'كم أنفقت', 'كم طلبت', 'كم اشتريت', 'كم دفعت',
                'ما هي طلباتي', 'ما هو رصيدي', 'أين طلباتي',
                # Analysis requests
                'تحليل طلباتي', 'تحليل مشترياتي', 'تحليل إنفاقي',
                'حلل طلباتي', 'حلل مشترياتي', 'حلل إنفاقي',
                # General patterns that likely refer to personal data
                'الطلبات الخاصة', 'المشتريات الخاصة', 'العروض الخاصة',
                'طلبات', 'مشتريات', 'عروض', 'فواتير', 'مدفوعات'
            ]
        else:
            user_specific_keywords = [
                'my orders', 'my purchases', 'my spending', 'my account', 'my data',
                'my offers', 'my bills', 'my payments', 'my balance',
                'i spent', 'i bought', 'i ordered', 'i purchase', 'i buy', 'i paid',
                'how much did i', 'how many orders', 'analyze my', 'analyse my',
                'my order history', 'my purchase history', 'what are my',
                'where are my', 'show me my', 'orders', 'purchases', 'offers'
            ]
        
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in user_specific_keywords)
    
    def _is_company_specific_query(self, query, language='en'):
        """Determine if the query is asking for company-specific data analysis"""
        if language == 'ar':
            company_specific_keywords = [
                # Direct possessive forms
                'شركتي', 'شركتنا', 'أعمالي', 'أعمالنا', 'مبيعاتي', 'مبيعاتنا',
                'إيراداتي', 'إيراداتنا', 'أرباحي', 'أرباحنا', 'رصيدي', 'رصيدنا',
                'طلباتي', 'طلباتنا', 'عملائي', 'عملاؤنا', 'منتجاتي', 'منتجاتنا',
                # Business analysis terms
                'تحليل الأعمال', 'تحليل المبيعات', 'تحليل الإيرادات', 'تحليل الأرباح',
                'أداء الشركة', 'أداء المبيعات', 'نمو الشركة', 'نمو المبيعات',
                'إحصائيات الشركة', 'إحصائيات المبيعات', 'تقرير الأعمال',
                # Question patterns
                'كم بعنا', 'كم ربحنا', 'كم طلب', 'كيف أداء', 'ما هو وضع',
                'أين نقف', 'كيف نحسن', 'ما هي استراتيجية',
                # Order management terms
                'آخر الطلبات', 'الطلبات الأخيرة', 'تحقق من الطلبات', 'اعرض الطلبات',
                'طلبات جديدة', 'طلبات معلقة', 'طلبات مقبولة', 'طلبات مرفوضة',
                'أي طلبات أقبل', 'أي طلبات أرفض', 'توصيات الطلبات', 'تحليل الطلبات',
                # Business terms
                'مبيعات', 'إيرادات', 'أرباح', 'طلبات', 'عملاء', 'منتجات',
                'حزم', 'عروض', 'فواتير', 'مدفوعات', 'رصيد', 'ميزانية'
            ]
        else:
            company_specific_keywords = [
                # Direct possessive forms
                'our company', 'our business', 'our sales', 'our revenue', 'our profit',
                'our orders', 'our customers', 'our products', 'our packages',
                'our balance', 'our performance', 'our growth', 'our analytics',
                # Business analysis terms
                'business analysis', 'sales analysis', 'revenue analysis', 'profit analysis',
                'company performance', 'sales performance', 'business growth', 'sales growth',
                'company statistics', 'sales statistics', 'business report', 'sales report',
                # Question patterns
                'how much did we sell', 'how much profit', 'how many orders', 'how is our',
                'what is our performance', 'where do we stand', 'how can we improve',
                'analyze our', 'analyse our', 'show me our', 'what are our',
                # Order management terms
                'last orders', 'recent orders', 'check orders', 'show orders', 'view orders',
                'new orders', 'pending orders', 'accepted orders', 'rejected orders',
                'which orders to accept', 'which orders to reject', 'order recommendations',
                'order analysis', 'analyze orders', 'order insights', 'order status',
                # Business terms
                'sales', 'revenue', 'profit', 'orders', 'customers', 'products',
                'packages', 'offers', 'bills', 'payments', 'balance', 'budget',
                'business', 'company', 'performance', 'analytics', 'metrics'
            ]
        
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in company_specific_keywords)
    
    def _is_order_management_query(self, query, language='en'):
        """Determine if the query is specifically about order management"""
        if language == 'ar':
            order_keywords = [
                'آخر الطلبات', 'الطلبات الأخيرة', 'تحقق من الطلبات', 'اعرض الطلبات',
                'طلبات جديدة', 'طلبات معلقة', 'طلبات مقبولة', 'طلبات مرفوضة',
                'أي طلبات أقبل', 'أي طلبات أرفض', 'توصيات الطلبات', 'تحليل الطلبات',
                'حالة الطلبات', 'إدارة الطلبات', 'معاينة الطلبات'
            ]
        else:
            order_keywords = [
                'last orders', 'recent orders', 'check orders', 'show orders', 'view orders',
                'new orders', 'pending orders', 'accepted orders', 'rejected orders',
                'which orders to accept', 'which orders to reject', 'order recommendations',
                'order analysis', 'analyze orders', 'order insights', 'order status',
                'order management', 'manage orders', 'review orders'
            ]
        
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in order_keywords)
    
    def _create_order_management_prompt(self, data_summary, query, language='en'):
        """Create specialized prompt for order management queries"""
        
        # Extract recent orders for detailed analysis
        business_summary = data_summary.get('business_summary', {})
        recent_orders = business_summary.get('orders', [])
        pending_orders = [order for order in recent_orders if order.get('status') == 'pending']
        
        # Create detailed order analysis for recent orders
        order_analysis = ""
        for order in recent_orders[:10]:  # Focus on last 10 orders
            order_analysis += f"""

Order #{order.get('id')}: {order.get('name')}
- Status: {order.get('status')}
- Created: {order.get('created_at')}
- Value: {order.get('total_value')} EGP
- Estimated Profit: {order.get('estimated_profit')} EGP ({order.get('profit_margin')}% margin)
- Priority: {order.get('priority')} (Delivery Urgency: {order.get('delivery_urgency')})
- Sector: {order.get('sector')}
- Offers Received: {order.get('offers_count')}
- Purchases Required: {order.get('purchases_count')} items
- Payment Method: {order.get('payment_way')}
- Delivery Date: {order.get('delivery_date') or 'Not specified'}
- Direct Negotiation: {'Yes' if order.get('direct_negotiation') else 'No'}
"""
            if order.get('purchases'):
                order_analysis += "- Key Items: "
                for purchase in order.get('purchases', [])[:2]:
                    order_analysis += f"{purchase.get('part_name')} ({purchase.get('quantity')} {purchase.get('unit')}), "
                order_analysis = order_analysis.rstrip(', ') + "\n"
        
        if language == 'ar':
            return f"""
أنت مستشار أعمال خبير في إدارة الطلبات والمشتريات الصناعية.

ملف الشركة:
الاسم: {data_summary.get('company_info', {}).get('name', 'غير محدد')}
الرصيد الحالي: {business_summary.get('balance', {}).get('current_balance', 0):,.2f} {business_summary.get('balance', {}).get('currency', 'جنيه')}

مؤشرات الأعمال:
- إجمالي الطلبات: {business_summary.get('total_orders', 0)}
- الطلبات المعلقة: {business_summary.get('pending_orders_count', 0)}
- الطلبات المقبولة: {business_summary.get('accepted_orders_count', 0)}
- الطلبات المكتملة: {business_summary.get('completed_orders_count', 0)}
- متوسط قيمة الطلب: {business_summary.get('average_order_value', 0):,.2f} جنيه

تحليل الطلبات:{order_analysis}

التعليمات:
لكل طلب يتطلب قرار، قدم توصية منظمة:

✅ القرار: [قبول/رفض/تفاوض] - مستوى الثقة: [عالي/متوسط/منخفض]
💰 التحليل المالي:
  - هامش الربح: X%
  - الربح المتوقع: X جنيه
  - الجدول الزمني للعائد: X يوم
  - تأثير التدفق النقدي: [إيجابي/سلبي/محايد]

⚠️ تقييم المخاطر:
  - مخاطر التسليم: [منخفض/متوسط/عالي]
  - مخاطر الدفع: [منخفض/متوسط/عالي]
  - التعقيد التقني: [منخفض/متوسط/عالي]
  - ظروف السوق: [مواتية/محايدة/غير مواتية]

🎯 القيمة الاستراتيجية:
  - توافق القطاع: [ممتاز/جيد/ضعيف]
  - علاقة العميل: [جديد/موجود/استراتيجي]
  - الفرص المستقبلية: [عالية/متوسطة/منخفضة]

📋 خطوات العمل:
  - الخطوات الفورية المطلوبة
  - تخصيص الموارد المطلوب
  - اعتبارات الجدول الزمني

استفسار المستخدم: "{query}"

قدم توصيات محددة وقابلة للتنفيذ مع التبرير الواضح.
"""
        else:
            return f"""
You are an expert AI business advisor specializing in order management and procurement decisions for industrial companies.

COMPANY PROFILE:
Name: {data_summary.get('company_info', {}).get('name', 'Unknown')}
Current Balance: {business_summary.get('balance', {}).get('current_balance', 0):,.2f} {business_summary.get('balance', {}).get('currency', 'EGP')}

BUSINESS METRICS:
- Total Orders: {business_summary.get('total_orders', 0)}
- Pending Orders: {business_summary.get('pending_orders_count', 0)}
- Accepted Orders: {business_summary.get('accepted_orders_count', 0)}
- Completed Orders: {business_summary.get('completed_orders_count', 0)}
- Average Order Value: {business_summary.get('average_order_value', 0):,.2f} EGP

ORDER ANALYSIS:{order_analysis}

INSTRUCTIONS:
For each order that requires a decision, provide a structured recommendation:

🔍 ORDER RECOMMENDATION FORMAT:
✅ DECISION: [ACCEPT/REJECT/NEGOTIATE] - Confidence: [HIGH/MEDIUM/LOW]
💰 FINANCIAL ANALYSIS:
  - Profit Margin: X%
  - Expected Profit: X EGP
  - ROI Timeline: X days
  - Cash Flow Impact: [Positive/Negative/Neutral]

⚠️ RISK ASSESSMENT:
  - Delivery Risk: [Low/Medium/High]
  - Payment Risk: [Low/Medium/High]
  - Technical Complexity: [Low/Medium/High]
  - Market Conditions: [Favorable/Neutral/Unfavorable]

🎯 STRATEGIC VALUE:
  - Sector Alignment: [Excellent/Good/Poor]
  - Client Relationship: [New/Existing/Strategic]
  - Future Opportunities: [High/Medium/Low]

📋 ACTION ITEMS:
  - Immediate steps required
  - Resource allocation needed
  - Timeline considerations

User Query: "{query}"

Provide specific, actionable recommendations with clear reasoning.
"""

# Global AI service instance
client_ai_service = ClientAIAnalysisService()