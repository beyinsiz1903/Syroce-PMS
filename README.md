# 🏨 RoomOps - Complete Hotel Management System

Modern, full-featured Property Management System (PMS) for hotels with AI-powered insights, multi-language support, and mobile-responsive design.

## ✨ Features

### 🎯 Core Modules
- **Property Management System (PMS)** - Complete hotel operations
- **Front Desk Management** - Check-in/out, reservations, walk-ins
- **Housekeeping** - Room status, task assignment, staff management
- **Folio Management** - Guest billing, charges, payments
- **Invoicing & Accounting** - E-invoices, tax management, financial reports
- **Revenue Management (RMS)** - Dynamic pricing, demand forecasting
- **Loyalty Program** - Guest rewards, tier management
- **Marketplace** - Wholesale purchasing for hotel supplies
- **Night Audit** - Automated end-of-day procedures
- **Reports & Analytics** - Comprehensive reporting dashboard

### 🌍 Multi-Language Support (8 Languages)
- 🇬🇧 English
- 🇹🇷 Turkish (Türkçe)
- 🇩🇪 German (Deutsch)
- 🇸🇦 Arabic (العربية) with RTL support
- 🇷🇺 Russian (Русский)
- 🇮🇹 Italian (Italiano)
- 🇫🇷 French (Français)
- 🇪🇸 Spanish (Español)

### 📱 Mobile Responsive
- Automatic mobile detection
- Touch-optimized interface
- Bottom sheet design for mobile
- iOS/Android friendly inputs

### 🔐 Security
- JWT Authentication (7-day token expiration)
- Bcrypt password hashing
- Role-based access control
- Automatic session management
- HTTPS/SSL enabled

### 🎨 Modern UI/UX
- Beautiful gradient backgrounds
- Smooth animations
- Dark/Light theme support
- Tailwind CSS styling
- Responsive design

## 🚀 Quick Start

### Demo Account
```
Email: demo@hotel.com
Password: demo123
```

### Demo Data Included
- ✅ 30 Rooms (4 types)
- ✅ 50 Guests
- ✅ 40 Bookings (past, current, future)
- ✅ 10 Invoices
- ✅ Housekeeping tasks
- ✅ Folio records with charges

## 🛠️ Tech Stack

### Frontend
- **React 19** - UI framework
- **Tailwind CSS** - Styling
- **Axios** - API calls
- **React i18next** - Internationalization
- **Lucide Icons** - Icon library
- **Shadcn/ui** - Component library

### Backend
- **FastAPI** - Python web framework
- **Motor** - Async MongoDB driver
- **PyJWT** - JWT authentication
- **Bcrypt** - Password hashing
- **Pydantic** - Data validation

### Database
- **MongoDB** - NoSQL database
- Collections: users, tenants, rooms, guests, bookings, folios, invoices

## 📦 Installation

### Prerequisites
- Python 3.11+
- Node.js 20+
- MongoDB 7.0+

### Local Development
```bash
# Clone repository
git clone <your-repo>
cd hotel-pms

# Install backend dependencies
cd backend
pip install -r requirements.txt

# Install frontend dependencies
cd ../frontend
yarn install

# Start development servers
# Backend: http://localhost:8001
# Frontend: http://localhost:3000
```

## 🌐 Deployment

### Using Emergent Platform
1. Click **Deploy** button in chat interface
2. Wait for deployment to complete (~10 minutes)
3. Access your app at: `https://your-app.emergent.sh`

### Environment Variables
```bash
# Production (MUST CHANGE!)
JWT_SECRET=your-super-secure-random-string-min-32-chars
JWT_EXPIRATION_HOURS=168

# Managed by Emergent
MONGO_URL=<auto-configured>
REACT_APP_BACKEND_URL=<auto-configured>
```

### Custom Domain
1. Go to Deployments → Custom Domain
2. Add your domain (e.g., hotel.yourdomain.com)
3. Configure DNS A Record
4. Wait 5-15 minutes for propagation

## 📚 Documentation

### API Endpoints

#### Authentication
- `POST /api/auth/login` - User login
- `POST /api/auth/register` - User registration
- `GET /api/auth/me` - Get current user

#### PMS
- `GET /api/rooms` - List rooms
- `GET /api/guests` - List guests
- `GET /api/bookings` - List bookings
- `POST /api/bookings` - Create booking

#### Folio
- `GET /api/folios/{folio_id}` - Get folio
- `POST /api/folios/{folio_id}/charges` - Add charge
- `POST /api/folios/{folio_id}/payments` - Add payment

#### Invoices
- `GET /api/invoices` - List invoices
- `POST /api/invoices` - Create invoice

[Full API documentation available]

## 🧪 Testing

### Manual Testing
- Use demo account to test all features
- Check mobile responsive on different devices
- Test multi-language switching
- Verify authentication flow

### Automated Testing
```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
yarn test
```

## 🔧 Configuration

### Multi-Language
Edit language files in `/frontend/src/locales/`:
- `en.json` - English
- `tr.json` - Turkish
- `de.json` - German
- `ar.json` - Arabic
- `ru.json` - Russian
- `it.json` - Italian
- `fr.json` - French
- `es.json` - Spanish

### Theming
Customize in `/frontend/src/App.css` and Tailwind config

## 📊 Database Schema

### Collections
- **users** - Hotel staff and admin accounts
- **tenants** - Hotel properties
- **rooms** - Room inventory
- **guests** - Guest profiles
- **bookings** - Reservations
- **folios** - Guest billing records
- **folio_charges** - Individual charges
- **folio_payments** - Payments
- **invoices** - Financial documents
- **housekeeping_tasks** - Cleaning assignments

## 🤝 Contributing

Contributions are welcome! Please follow these steps:
1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open pull request

## 📝 License

This project is licensed under the MIT License.

## 🆘 Support

For issues or questions:
- Check DEPLOYMENT_CHECKLIST.md
- Review error logs
- Contact support

## 🎉 Acknowledgments

Built with modern tools and best practices for hotel management.

---

**Status**: ✅ Production Ready
**Version**: 1.0.0
**Last Updated**: 2025

Made with ❤️ for the hospitality industry
