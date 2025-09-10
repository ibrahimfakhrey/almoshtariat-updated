# Flask Business Management System

A comprehensive business management system built with Flask, featuring AI-powered chat assistants, order management, inventory tracking, and advanced analytics.

## 🌟 Features

### Core Functionality
- **Multi-role System**: Support for clients, companies, and administrators
- **Order Management**: Complete order lifecycle management
- **Inventory Tracking**: Real-time inventory management
- **Bill Management**: Invoice generation and payment tracking
- **Offer System**: Dynamic pricing and offer management

### AI-Powered Features
- **Client AI Assistant**: Personal shopping assistant with order analysis
- **Company AI Analytics**: Advanced business intelligence with function calling
- **Agentic AI Service**: Smart business insights using Google Gemini
- **Multi-language Support**: Arabic and English interfaces

### Technical Features
- **Responsive Design**: Mobile-first approach with RTL support
- **Real-time Updates**: WebSocket integration for live updates
- **Security**: CSRF protection, role-based access control
- **Database**: SQLAlchemy ORM with Flask-Migrate
- **Internationalization**: Flask-Babel for multi-language support

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- pip (Python package manager)
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd mysite
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure AI Services** (Optional)
   - Copy `ai_config.py.example` to `ai_config.py`
   - Add your Google Gemini API key

5. **Initialize Database**
   ```bash
   flask db upgrade
   ```

6. **Run the application**
   ```bash
   python flask_app.py
   ```

7. **Access the application**
   - Open your browser and navigate to `http://localhost:8001`

## 📱 User Interfaces

### Client Dashboard
- **AI Chat Assistant**: Personal shopping advisor
- **Order Management**: Track and manage orders
- **Balance Management**: View account balance and transactions
- **Offer Browsing**: Browse and accept company offers

### Company Dashboard
- **AI Business Analytics**: Advanced business intelligence
- **Inventory Management**: Track products and stock levels
- **Order Processing**: Manage incoming orders
- **Bill Generation**: Create and manage invoices
- **Employee Management**: Manage company staff

### Admin Panel
- **System Overview**: Monitor system health
- **User Management**: Manage all system users
- **Company Approval**: Review and approve company registrations
- **Analytics Dashboard**: System-wide analytics

## 🤖 AI Features

### Client AI Assistant
- Personal shopping recommendations
- Order history analysis
- Balance and transaction insights
- Quick actions for common tasks

### Company AI Analytics
- **Sales Analysis**: Revenue trends and performance metrics
- **Customer Insights**: Behavior patterns and segmentation
- **Inventory Optimization**: Stock level recommendations
- **Financial Analysis**: Profit margins and cost analysis
- **Predictive Analytics**: Market trends and forecasting

### Available AI Functions
- `get_recent_orders`: Retrieve and analyze recent orders
- `create_offer_for_order`: Generate competitive offers
- `get_company_balance`: Financial status overview
- `get_bills_summary`: Invoice and payment tracking
- `get_customer_behavior_analysis`: Customer insights
- `get_market_trends_analysis`: Market intelligence
- And 10+ more specialized functions

## 🛠️ Technology Stack

### Backend
- **Flask**: Web framework
- **SQLAlchemy**: ORM and database management
- **Flask-Login**: User session management
- **Flask-Migrate**: Database migrations
- **Flask-Babel**: Internationalization
- **Flask-SocketIO**: Real-time communication

### Frontend
- **Alpine.js**: Reactive JavaScript framework
- **Tailwind CSS**: Utility-first CSS framework
- **RTL Support**: Right-to-left language support
- **Responsive Design**: Mobile-first approach

### AI & Analytics
- **Google Gemini**: Advanced language model
- **Function Calling**: Structured AI interactions
- **Agentic AI**: Intelligent business automation

## 📊 Database Schema

### Core Models
- **User**: System users (clients, companies, admins)
- **Company**: Business entities
- **Order**: Purchase orders and requests
- **Product**: Inventory items
- **Bill**: Invoices and payments
- **Offer**: Price quotes and proposals

### AI Models
- **ChatMessage**: Conversation history
- **AIAnalysis**: Cached analysis results
- **UserPreference**: Personalization data

## 🔧 Configuration

### Environment Variables
Create a `.env` file with:
```env
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///purchases.db
GEMINI_API_KEY=your-gemini-api-key
FLASK_ENV=development
```

### AI Configuration
Update `ai_config.py` with your API credentials:
```python
class AIConfig:
    GEMINI_API_KEY = "your-api-key"
    MODEL_NAME = "gemini-1.5-pro"
    TEMPERATURE = 0.7
```

## 🌐 API Endpoints

### Authentication
- `POST /login` - User login
- `POST /register` - User registration
- `GET /logout` - User logout

### AI Chat
- `POST /api/ai_chat` - Client AI assistant
- `POST /api/company_ai_chat` - Company AI analytics

### Business Operations
- `GET /api/user_orders` - User orders
- `GET /api/company_balance` - Company financials
- `POST /api/create_offer` - Generate offers
- `GET /api/bills_summary` - Invoice overview

## 🚀 Deployment

### Production Setup
1. Set environment to production
2. Configure production database
3. Set up reverse proxy (nginx)
4. Configure SSL certificates
5. Set up monitoring and logging

### Docker Deployment
```bash
# Build image
docker build -t flask-business-app .

# Run container
docker run -p 8001:8001 flask-business-app
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue on GitHub
- Check the documentation
- Review the code comments

## 🔄 Version History

- **v1.0.0**: Initial release with core features
- **v1.1.0**: Added AI chat assistants
- **v1.2.0**: Enhanced analytics and reporting
- **v1.3.0**: Agentic AI integration

---

**Built with ❤️ using Flask and modern web technologies**