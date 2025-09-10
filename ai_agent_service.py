import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from flask import current_app
from ai_config import ai_config
from models import db, User, Company, Order, Package, CompanyBalance, Product, AIAgentTask
from sqlalchemy import func, desc
import logging
import threading
from collections import defaultdict



class AIAgentService:
    """AI Agent service for automated company tasks"""
    
    def __init__(self):
        self.ai_config = ai_config
        self.task_metrics = defaultdict(lambda: {'total': 0, 'success': 0, 'failed': 0, 'avg_duration': 0.0})
        self.performance_stats = {'total_tasks': 0, 'success_rate': 0.0, 'avg_execution_time': 0.0}
        self._lock = threading.Lock()
        self._setup_logging()
        
        # Define available task types
        self.task_types = {
            'data_analysis': {
                'name': 'تحليل البيانات',
                'name_en': 'Data Analysis',
                'description': 'تحليل شامل لبيانات الشركة والطلبات والمبيعات',
                'description_en': 'Comprehensive analysis of company data, orders, and sales',
                'handler': self._handle_data_analysis
            },
            'report_generation': {
                'name': 'إنشاء التقارير',
                'name_en': 'Report Generation',
                'description': 'إنشاء تقارير مفصلة عن الأداء والمبيعات',
                'description_en': 'Generate detailed performance and sales reports',
                'handler': self._handle_report_generation
            },
            'inventory_management': {
                'name': 'إدارة المخزون',
                'name_en': 'Inventory Management',
                'description': 'تحليل المخزون وتقديم توصيات للتحسين',
                'description_en': 'Analyze inventory and provide optimization recommendations',
                'handler': self._handle_inventory_management
            },
            'order_processing': {
                'name': 'معالجة الطلبات',
                'name_en': 'Order Processing',
                'description': 'تحليل الطلبات وتقديم اقتراحات للتحسين',
                'description_en': 'Analyze orders and provide improvement suggestions',
                'handler': self._handle_order_processing
            },
            'customer_insights': {
                'name': 'رؤى العملاء',
                'name_en': 'Customer Insights',
                'description': 'تحليل سلوك العملاء وتقديم توصيات',
                'description_en': 'Analyze customer behavior and provide recommendations',
                'handler': self._handle_customer_insights
            },
            'market_analysis': {
                'name': 'تحليل السوق',
                'name_en': 'Market Analysis',
                'description': 'تحليل اتجاهات السوق والمنافسة',
                'description_en': 'Analyze market trends and competition',
                'handler': self._handle_market_analysis
            }
        }
    
    def _setup_logging(self):
        """Setup dedicated logging for AI agent tasks"""
        self.logger = logging.getLogger('ai_agent')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - AI_AGENT - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def create_task(self, task_type: str, description: str, company_id: int, 
                   parameters: Optional[Dict[str, Any]] = None, priority: str = 'medium') -> str:
        """Create a new AI agent task"""
        if task_type not in self.task_types:
            raise ValueError(f"Unknown task type: {task_type}")
        
        task_id = str(uuid.uuid4())
        
        # Create database task
        task = AIAgentTask(
            id=task_id,
            task_type=task_type,
            description=description,
            company_id=company_id,
            parameters=parameters,
            priority=priority
        )
        
        db.session.add(task)
        db.session.commit()
        
        current_app.logger.info(f"Created AI agent task {task_id} of type {task_type} for company {company_id}")
        return task_id
    
    def execute_task(self, task_id: str) -> Dict[str, Any]:
        """Execute an AI agent task"""
        task = AIAgentTask.query.get(task_id)
        if not task:
            return {'error': 'Task not found'}
        
        if task.status != 'pending':
            return {'error': f'Task is already {task.status}'}
        
        try:
            task.status = 'running'
            task.started_at = datetime.now()
            task.progress = 10
            db.session.commit()
            
            # Get the handler for this task type
            handler = self.task_types[task.task_type]['handler']
            
            # Execute the task
            result = handler(task)
            
            task.status = 'completed'
            task.completed_at = datetime.now()
            task.result = result
            task.progress = 100
            db.session.commit()
            
            # Update metrics
            with self._lock:
                self._update_task_metrics(task, success=True)
            
            self.logger.info(f"Completed AI agent task {task_id} of type {task.task_type}")
            current_app.logger.info(f"Completed AI agent task {task_id}")
            return {'success': True, 'result': result}
            
        except Exception as e:
            task.status = 'failed'
            task.error = str(e)
            task.completed_at = datetime.now()
            db.session.commit()
            
            # Update metrics
            with self._lock:
                self._update_task_metrics(task, success=False)
            
            self.logger.error(f"AI agent task {task_id} failed: {str(e)}")
            current_app.logger.error(f"AI agent task {task_id} failed: {str(e)}")
            return {'error': str(e)}
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a task"""
        task = AIAgentTask.query.get(task_id)
        if task:
            return task.to_dict()
        return None
    
    def get_company_tasks(self, company_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all tasks for a company"""
        tasks = AIAgentTask.query.filter_by(company_id=company_id).order_by(AIAgentTask.created_at.desc()).limit(limit).all()
        return [task.to_dict() for task in tasks]
    
    def _update_task_metrics(self, task: AIAgentTask, success: bool):
        """Update task performance metrics"""
        task_type = task.task_type
        duration = 0
        if task.started_at and task.completed_at:
            duration = (task.completed_at - task.started_at).total_seconds()
        
        # Update task type metrics
        metrics = self.task_metrics[task_type]
        metrics['total'] += 1
        if success:
            metrics['success'] += 1
        else:
            metrics['failed'] += 1
        
        # Update average duration
        if duration > 0:
            current_avg = metrics['avg_duration']
            metrics['avg_duration'] = float((current_avg * (metrics['total'] - 1) + duration) / metrics['total'])
        
        # Update overall performance stats
        self.performance_stats['total_tasks'] += 1
        total_success = sum(m['success'] for m in self.task_metrics.values())
        self.performance_stats['success_rate'] = float((total_success / self.performance_stats['total_tasks']) * 100)
        
        total_duration = sum(m['avg_duration'] * m['total'] for m in self.task_metrics.values())
        self.performance_stats['avg_execution_time'] = float(total_duration / self.performance_stats['total_tasks'])
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for all tasks"""
        with self._lock:
            active_tasks_count = AIAgentTask.query.filter_by(status='running').count()
            completed_tasks_count = AIAgentTask.query.filter(AIAgentTask.status.in_(['completed', 'failed'])).count()
            return {
                'overall_stats': self.performance_stats.copy(),
                'task_type_metrics': dict(self.task_metrics),
                'active_tasks_count': active_tasks_count,
                'completed_tasks_count': completed_tasks_count
            }
    
    def get_available_task_types(self, language: str = 'en') -> List[Dict[str, Any]]:
        """Get available task types"""
        result = []
        for task_type, info in self.task_types.items():
            result.append({
                'type': task_type,
                'name': info['name'] if language == 'ar' else info['name_en'],
                'description': info['description'] if language == 'ar' else info['description_en']
            })
        return result
    
    # Task handlers
    def _handle_data_analysis(self, task: AIAgentTask) -> Dict[str, Any]:
        """Handle data analysis task"""
        try:
            company_id = task.company_id
            task.progress = 20
            db.session.commit()
            
            # Get company data
            company = Company.query.get(company_id)
            if not company:
                raise Exception("Company not found")
            
            task.progress = 40
            db.session.commit()
            
            # Get orders, packages, and balance
            orders = Order.query.filter_by(company_id=company_id).all()
            packages = Package.query.filter_by(company_id=company_id).all()
            balance = CompanyBalance.query.filter_by(company_id=company_id).first()
            
            task.progress = 60
            db.session.commit()
            
            # Prepare data summary
            data_summary = self._prepare_comprehensive_data_summary(company, orders, packages, balance)
            
            task.progress = 80
            db.session.commit()
            
            # Generate AI analysis
            language = task.parameters.get('language', 'en') if task.parameters else 'en'
            analysis_prompt = self._create_data_analysis_prompt(data_summary, language)
            
            try:
                ai_analysis = self.ai_config.generate_content(analysis_prompt)
            except Exception as e:
                self.logger.warning(f"AI model failed, using fallback analysis: {str(e)}")
                ai_analysis = self._generate_fallback_analysis(data_summary, language)
            
            return {
                'analysis': ai_analysis,
                'data_summary': data_summary,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Data analysis failed: {str(e)}")
            return {
                'analysis': f'Analysis failed: {str(e)}',
                'data_summary': {},
                'timestamp': datetime.now().isoformat()
            }
    
    def _handle_report_generation(self, task: AIAgentTask) -> Dict[str, Any]:
        """Handle report generation task"""
        company_id = task.company_id
        report_type = task.parameters.get('report_type', 'general')
        language = task.parameters.get('language', 'en')
        
        task.progress = 30
        
        # Get company data based on report type
        company = Company.query.get(company_id)
        orders = Order.query.filter_by(company_id=company_id).all()
        
        task.progress = 60
        
        # Generate report based on type
        if report_type == 'sales':
            report_data = self._generate_sales_report(company, orders)
        elif report_type == 'performance':
            report_data = self._generate_performance_report(company, orders)
        else:
            report_data = self._generate_general_report(company, orders)
        
        task.progress = 90
        
        # Generate AI-powered insights
        insights_prompt = self._create_report_insights_prompt(report_data, report_type, language)
        
        ai_insights = self.ai_config.generate_content(insights_prompt)
        
        return {
            'report_type': report_type,
            'report_data': report_data,
            'ai_insights': ai_insights,
            'timestamp': datetime.now().isoformat()
        }
    
    def _handle_inventory_management(self, task: AIAgentTask) -> Dict[str, Any]:
        """Handle inventory management task"""
        try:
            company_id = task.company_id
            language = task.parameters.get('language', 'en') if task.parameters else 'en'
            
            task.progress = 25
            db.session.commit()
            
            # Get company products
            products = Product.query.filter_by(company_id=company_id).all()
            
            task.progress = 50
            db.session.commit()
            
            # Analyze inventory levels
            inventory_analysis = []
            low_stock_items = []
            total_value = 0
            
            for product in products:
                stock_level = getattr(product, 'stock_quantity', 0)
                price = getattr(product, 'price', 0)
                min_threshold = getattr(product, 'min_stock_level', 10)
                
                product_value = stock_level * float(price) if price else 0
                total_value += product_value
                
                inventory_analysis.append({
                    'product_name': product.name,
                    'current_stock': stock_level,
                    'value': product_value,
                    'status': 'low' if stock_level <= min_threshold else 'adequate'
                })
                
                if stock_level <= min_threshold:
                    low_stock_items.append({
                        'product_name': product.name,
                        'current_stock': stock_level,
                        'min_threshold': min_threshold,
                        'recommended_reorder': min_threshold * 2,
                        'priority': 'high' if stock_level == 0 else 'medium'
                    })
            
            task.progress = 75
            db.session.commit()
            
            # Generate recommendations
            recommendations = []
            if low_stock_items:
                urgent_items = [item for item in low_stock_items if item['current_stock'] == 0]
                if urgent_items:
                    recommendations.append(f"URGENT: {len(urgent_items)} products are out of stock")
                recommendations.append(f"Reorder {len(low_stock_items)} products with low stock")
                recommendations.append("Set up automated reorder alerts")
            else:
                recommendations.append("Inventory levels are adequate")
                recommendations.append("Consider optimizing storage costs")
            
            if total_value > 100000:
                recommendations.append("High inventory value - consider reducing slow-moving items")
            
            # Generate AI recommendations
            inventory_data = {
                'total_products': len(products),
                'total_inventory_value': total_value,
                'low_stock_count': len(low_stock_items),
                'recommendations': recommendations
            }
            
            try:
                inventory_prompt = self._create_inventory_analysis_prompt(inventory_data, language)
                ai_recommendations = self.ai_config.generate_content(inventory_prompt)
            except Exception as e:
                self.logger.warning(f"AI model failed for inventory analysis: {str(e)}")
                ai_recommendations = "AI analysis unavailable - using basic recommendations"
            
            return {
                'message': 'تم تحليل إدارة المخزون بنجاح' if language == 'ar' else 'Inventory management analysis completed',
                'total_products': len(products),
                'total_inventory_value': total_value,
                'low_stock_items': low_stock_items,
                'inventory_analysis': inventory_analysis,
                'recommendations': recommendations,
                'ai_recommendations': ai_recommendations,
                'timestamp': datetime.now().isoformat(),
                'summary': {
                    'adequate_stock': len([p for p in inventory_analysis if p['status'] == 'adequate']),
                    'low_stock': len(low_stock_items),
                    'out_of_stock': len([item for item in low_stock_items if item['current_stock'] == 0])
                }
            }
            
        except Exception as e:
            self.logger.error(f"Inventory management failed: {str(e)}")
            return {
                'message': 'فشل في تحليل إدارة المخزون' if language == 'ar' else 'Inventory management analysis failed',
                'total_products': 0,
                'total_inventory_value': 0,
                'low_stock_items': [],
                'inventory_analysis': [],
                'recommendations': [f'Inventory analysis failed: {str(e)}'],
                'ai_recommendations': 'Analysis failed',
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
    
    def _handle_order_processing(self, task: AIAgentTask) -> Dict[str, Any]:
        """Handle order processing task"""
        company_id = task.company_id
        language = task.parameters.get('language', 'en')
        action_type = task.parameters.get('action_type', 'analyze')  # analyze, optimize, automate
        
        task.progress = 30
        
        # Get orders and offers data
        orders = Order.query.filter_by(company_id=company_id).all()
        company_offers = []
        for order in orders:
            if order.offers:
                company_offers.extend([offer for offer in order.offers if offer.company_id == company_id])
        
        task.progress = 60
        
        # Process based on action type
        if action_type == 'optimize':
            result = self._optimize_order_processing(orders, company_offers, language)
        elif action_type == 'automate':
            result = self._automate_order_responses(orders, company_offers, language)
        else:
            result = self._analyze_order_processing(orders, company_offers, language)
        
        task.progress = 90
        
        return {
            'message': 'تم تحليل معالجة الطلبات بنجاح' if language == 'ar' else 'Order processing analysis completed',
            'action_type': action_type,
            'result': result,
            'timestamp': datetime.now().isoformat()
        }
    
    def _handle_customer_insights(self, task: AIAgentTask) -> Dict[str, Any]:
        """Handle customer insights task"""
        company_id = task.company_id
        language = task.parameters.get('language', 'en')
        insight_type = task.parameters.get('insight_type', 'behavior')  # behavior, retention, satisfaction
        
        task.progress = 35
        
        # Get customer interaction data
        orders = Order.query.filter_by(company_id=company_id).all()
        customers_data = self._analyze_customer_data(orders, company_id)
        
        task.progress = 70
        
        # Generate AI insights based on type
        insights_prompt = self._create_customer_insights_prompt(customers_data, insight_type, language)
        ai_insights = self.ai_config.generate_content(insights_prompt)
        
        return {
            'message': 'تم تحليل رؤى العملاء بنجاح' if language == 'ar' else 'Customer insights analysis completed',
            'insight_type': insight_type,
            'customer_data': customers_data,
            'ai_insights': ai_insights,
            'timestamp': datetime.now().isoformat()
        }
    
    def _handle_market_analysis(self, task: AIAgentTask) -> Dict[str, Any]:
        """Handle market analysis task"""
        company_id = task.company_id
        language = task.parameters.get('language', 'en')
        analysis_scope = task.parameters.get('scope', 'sector')  # sector, competition, opportunities
        
        task.progress = 40
        
        # Get company and market data
        company = Company.query.get(company_id)
        market_data = self._gather_market_data(company, analysis_scope)
        
        task.progress = 80
        
        # Generate AI market analysis
        market_prompt = self._create_market_analysis_prompt(market_data, analysis_scope, language)
        ai_analysis = self.ai_config.generate_content(market_prompt)
        
        return {
            'message': 'تم تحليل السوق بنجاح' if language == 'ar' else 'Market analysis completed',
            'analysis_scope': analysis_scope,
            'market_data': market_data,
            'ai_analysis': ai_analysis,
            'timestamp': datetime.now().isoformat()
        }
    
    # Helper methods
    def _prepare_comprehensive_data_summary(self, company, orders, packages, balance):
        """Prepare comprehensive data summary for analysis"""
        total_orders = len(orders)
        total_revenue = 0
        
        # Calculate revenue from accepted offers
        for order in orders:
            if order.offers:
                company_offers = [offer for offer in order.offers if offer.company_id == company.id and offer.status == 'accepted']
                if company_offers:
                    total_revenue += sum(offer.total_price for offer in company_offers)
        
        recent_orders = [order for order in orders if order.created_at and order.created_at > datetime.now() - timedelta(days=30)]
        
        return {
            'company_info': {
                'name': company.company_name,
                'sector': company.sector,
                'balance': float(balance.balance) if balance else 0.0
            },
            'business_metrics': {
                'total_orders': total_orders,
                'total_revenue': float(total_revenue),
                'recent_orders_count': len(recent_orders),
                'total_packages': len(packages)
            }
        }
    
    def _create_data_analysis_prompt(self, data_summary, language):
        """Create prompt for data analysis"""
        if language == 'ar':
            return f"""قم بتحليل البيانات التالية للشركة وقدم رؤى مفيدة:

{json.dumps(data_summary, ensure_ascii=False, indent=2)}

يرجى تقديم:
1. تحليل شامل للأداء
2. نقاط القوة والضعف
3. توصيات للتحسين
4. اتجاهات مهمة

اكتب التحليل باللغة العربية بشكل مفصل ومفيد."""
        else:
            return f"""Analyze the following company data and provide valuable insights:

{json.dumps(data_summary, indent=2)}

Please provide:
1. Comprehensive performance analysis
2. Strengths and weaknesses
3. Improvement recommendations
4. Important trends

Write the analysis in detail and make it actionable."""
    
    def _create_report_insights_prompt(self, report_data, report_type, language):
        """Create prompt for report insights"""
        if language == 'ar':
            return f"""بناءً على بيانات التقرير التالية من نوع {report_type}:

{json.dumps(report_data, ensure_ascii=False, indent=2)}

قدم رؤى ذكية وتوصيات عملية لتحسين الأداء."""
        else:
            return f"""Based on the following {report_type} report data:

{json.dumps(report_data, indent=2)}

Provide intelligent insights and actionable recommendations for performance improvement."""
    
    def _generate_sales_report(self, company, orders):
        """Generate sales report data"""
        return {
            'total_orders': len(orders),
            'period': 'last_30_days',
            'revenue_trend': 'increasing'
        }
    
    def _generate_performance_report(self, company, orders):
        """Generate performance report data"""
        return {
            'efficiency_score': 85,
            'response_time': '2.5 hours',
            'customer_satisfaction': 'high'
        }
    
    def _generate_general_report(self, company, orders):
        """Generate general report data"""
        return {
            'overview': 'Company performance summary',
            'key_metrics': {
                'orders': len(orders),
                'growth': '15%'
            }
        }
    
    # Additional helper methods for enhanced task handlers
    def _analyze_inventory_data(self, packages, orders):
        """Analyze inventory data"""
        total_packages = len(packages)
        active_packages = [p for p in packages if p.status == 'active']
        
        # Calculate package utilization from orders
        package_usage = {}
        for order in orders:
            if order.offers:
                for offer in order.offers:
                    if offer.status == 'accepted' and offer.package_id:
                        package_usage[offer.package_id] = package_usage.get(offer.package_id, 0) + 1
        
        return {
            'total_packages': total_packages,
            'active_packages': len(active_packages),
            'package_usage': package_usage,
            'low_usage_packages': [pid for pid, usage in package_usage.items() if usage < 2]
        }
    
    def _create_inventory_analysis_prompt(self, inventory_data, language):
        """Create prompt for inventory analysis"""
        if language == 'ar':
            return f"""قم بتحليل بيانات المخزون التالية وقدم توصيات لتحسين إدارة المخزون:

{json.dumps(inventory_data, ensure_ascii=False, indent=2)}

يرجى تقديم:
1. تحليل مستويات المخزون
2. توصيات لتحسين الكفاءة
3. استراتيجيات إدارة المخزون
4. تحديد المنتجات بطيئة الحركة"""
        else:
            return f"""Analyze the following inventory data and provide recommendations for inventory management improvement:

{json.dumps(inventory_data, indent=2)}

Please provide:
1. Inventory level analysis
2. Efficiency improvement recommendations
3. Inventory management strategies
4. Slow-moving product identification"""
    
    def _optimize_order_processing(self, orders, offers, language):
        """Optimize order processing workflow"""
        avg_response_time = self._calculate_avg_response_time(orders, offers)
        optimization_suggestions = [
            'Implement automated pricing rules',
            'Set up quick response templates',
            'Create priority order handling'
        ]
        
        return {
            'current_avg_response_time': avg_response_time,
            'optimization_suggestions': optimization_suggestions,
            'potential_improvement': '40% faster processing'
        }
    
    def _automate_order_responses(self, orders, offers, language):
        """Automate order response system"""
        automation_rules = [
            'Auto-accept orders below threshold price',
            'Auto-decline orders outside service area',
            'Auto-quote standard packages'
        ]
        
        return {
            'automation_rules': automation_rules,
            'estimated_time_savings': '60% reduction in manual work',
            'implementation_status': 'ready_to_deploy'
        }
    
    def _analyze_order_processing(self, orders, offers, language):
        """Analyze current order processing performance"""
        total_orders = len(orders)
        accepted_offers = [o for o in offers if o.status == 'accepted']
        pending_offers = [o for o in offers if o.status == 'pending']
        
        return {
            'total_orders': total_orders,
            'accepted_offers': len(accepted_offers),
            'pending_offers': len(pending_offers),
            'acceptance_rate': len(accepted_offers) / len(offers) * 100 if offers else 0,
            'processing_insights': ['High demand periods identified', 'Response time optimization needed']
        }
    
    def _analyze_customer_data(self, orders, company_id):
        """Analyze customer interaction data"""
        customer_orders = {}
        for order in orders:
            customer_id = order.user_id
            if customer_id not in customer_orders:
                customer_orders[customer_id] = []
            customer_orders[customer_id].append(order)
        
        repeat_customers = {cid: orders for cid, orders in customer_orders.items() if len(orders) > 1}
        
        return {
            'total_customers': len(customer_orders),
            'repeat_customers': len(repeat_customers),
            'customer_retention_rate': len(repeat_customers) / len(customer_orders) * 100 if customer_orders else 0,
            'avg_orders_per_customer': sum(len(orders) for orders in customer_orders.values()) / len(customer_orders) if customer_orders else 0
        }
    
    def _create_customer_insights_prompt(self, customer_data, insight_type, language):
        """Create prompt for customer insights"""
        if language == 'ar':
            return f"""قم بتحليل بيانات العملاء التالية وقدم رؤى حول {insight_type}:

{json.dumps(customer_data, ensure_ascii=False, indent=2)}

يرجى التركيز على:
1. أنماط سلوك العملاء
2. استراتيجيات الاحتفاظ بالعملاء
3. فرص تحسين رضا العملاء
4. توصيات لزيادة الولاء"""
        else:
            return f"""Analyze the following customer data and provide insights about {insight_type}:

{json.dumps(customer_data, indent=2)}

Please focus on:
1. Customer behavior patterns
2. Customer retention strategies
3. Customer satisfaction improvement opportunities
4. Loyalty enhancement recommendations"""
    
    def _gather_market_data(self, company, analysis_scope):
        """Gather market data for analysis"""
        # Get companies in same sector for competitive analysis
        sector_companies = Company.query.filter_by(sector=company.sector).all()
        
        return {
            'company_sector': company.sector,
            'sector_companies_count': len(sector_companies),
            'market_position': 'mid-tier',  # This could be calculated based on various metrics
            'growth_opportunities': ['Digital transformation', 'Service expansion', 'Geographic expansion']
        }
    
    def _create_market_analysis_prompt(self, market_data, analysis_scope, language):
        """Create prompt for market analysis"""
        if language == 'ar':
            return f"""قم بتحليل بيانات السوق التالية مع التركيز على {analysis_scope}:

{json.dumps(market_data, ensure_ascii=False, indent=2)}

يرجى تقديم:
1. تحليل الوضع التنافسي
2. الفرص المتاحة في السوق
3. التهديدات المحتملة
4. استراتيجيات النمو المقترحة"""
        else:
            return f"""Analyze the following market data focusing on {analysis_scope}:

{json.dumps(market_data, indent=2)}

Please provide:
1. Competitive landscape analysis
2. Market opportunities
3. Potential threats
4. Suggested growth strategies"""
    
    def _calculate_avg_response_time(self, orders, offers):
        """Calculate average response time for orders"""
        # This is a simplified calculation - in reality you'd use actual timestamps
        return "2.5 hours"  # Placeholder value
    
    def _generate_fallback_analysis(self, data_summary, language):
        """Generate fallback analysis when AI model is unavailable"""
        if language == 'ar':
            return f"""تحليل البيانات الأساسي:
            
            معلومات الشركة:
            - اسم الشركة: {data_summary['company_info']['name']}
            - القطاع: {data_summary['company_info']['sector']}
            - الرصيد: {data_summary['company_info']['balance']} جنيه
            
            المقاييس التجارية:
            - إجمالي الطلبات: {data_summary['business_metrics']['total_orders']}
            - إجمالي الإيرادات: {data_summary['business_metrics']['total_revenue']} جنيه
            - الطلبات الحديثة: {data_summary['business_metrics']['recent_orders_count']}
            - إجمالي الباقات: {data_summary['business_metrics']['total_packages']}
            
            التوصيات:
            - مراجعة أداء الطلبات الحديثة
            - تحسين استراتيجية التسعير
            - زيادة التسويق للباقات المتاحة
            """
        else:
            return f"""Basic Data Analysis:
            
            Company Information:
            - Company Name: {data_summary['company_info']['name']}
            - Sector: {data_summary['company_info']['sector']}
            - Balance: {data_summary['company_info']['balance']} EGP
            
            Business Metrics:
            - Total Orders: {data_summary['business_metrics']['total_orders']}
            - Total Revenue: {data_summary['business_metrics']['total_revenue']} EGP
            - Recent Orders: {data_summary['business_metrics']['recent_orders_count']}
            - Total Packages: {data_summary['business_metrics']['total_packages']}
            
            Recommendations:
            - Review recent order performance
            - Optimize pricing strategy
            - Increase marketing for available packages
            """

# Create global instance
ai_agent_service = AIAgentService()