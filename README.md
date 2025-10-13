# DoGoods App - Community Food Sharing Platform

A modern, full-stack community food sharing platform built with React, Vite, and Supabase. This application enables users to share, trade, and donate food items while building community connections and reducing food waste.

## 🚀 Features

- **User Authentication & Profiles**: Secure user registration, login, and profile management
- **Food Listings**: Create, browse, and manage food donations and trade offers
- **AI-Powered Matching**: Intelligent food matching using AI algorithms
- **Trading System**: Barter and trade food items with other community members
- **Community Features**: Blog posts, notifications, and community engagement
- **Admin Dashboard**: Comprehensive admin tools for content moderation and user management
- **Responsive Design**: Mobile-first design that works on all devices
- **Real-time Updates**: Live notifications and real-time data synchronization

## 🛠️ Tech Stack

- **Frontend**: React 18, Vite, Tailwind CSS
- **Backend**: Supabase (PostgreSQL, Auth, Storage, Real-time)
- **State Management**: React Context API with custom hooks
- **Testing**: Jest, React Testing Library
- **Build Tool**: Vite
- **Deployment**: Ready for Vercel, Netlify, Firebase, or any static hosting

## 📋 Prerequisites

- Node.js 18+ 
- npm or yarn
- Supabase account and project

## 🚀 Quick Start

### 1. Clone and Install

```bash
git clone <your-repo-url>
cd newproject
npm install
```

### 2. Environment Setup

Copy the environment example file and configure your Supabase credentials:

```bash
cp config/env.example .env.local
```

Edit `.env.local` with your Supabase project details:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
NODE_ENV=development
```

### 3. Start Development Server

```bash
npm run dev
```

The app will open at `http://localhost:3001`

### 4. Start Supabase Local Development (Optional)

```bash
npm run supabase:start
npm run supabase:studio
```

## 🗄️ Database Setup

### Option 1: Use Local Supabase

```bash
npm run supabase:start
npm run supabase:db:reset
```

### Option 2: Use Remote Supabase

1. Create a new project at [supabase.com](https://supabase.com)
2. Run the migrations in your Supabase SQL editor:
   ```bash
   # Copy and run each migration file in order:
   supabase/migrations/001_initial_schema.sql
   supabase/migrations/002_create_profile_trigger.sql
   # ... other migrations
   ```

## 🧪 Testing

```bash
# Run all tests
npm test

# Run tests in watch mode
npm test -- --watch

# Run tests with coverage
npm test -- --coverage
```

## 🏗️ Building for Production

```bash
# Build the application
npm run build

# Preview the build
npm run preview
```

## 🚀 Deployment

### Quick Deploy

```bash
# Deploy to Vercel
./deploy.sh vercel

# Deploy to Netlify
./deploy.sh netlify

# Deploy to Firebase
./deploy.sh firebase
```

### Manual Deployment

1. Build the application: `npm run build`
2. Upload the `dist` folder to your hosting provider
3. Configure environment variables in your hosting platform

## 📁 Project Structure

```
newproject/
├── components/          # Reusable UI components
│   ├── assistant/      # AI assistant components
│   ├── common/         # Common UI elements
│   ├── food/           # Food-related components
│   ├── layout/         # Layout components
│   ├── profile/        # User profile components
│   ├── trade/          # Trading system components
│   └── user/           # User management components
├── pages/              # Page components
│   ├── admin/          # Admin dashboard pages
│   └── ...             # Other page components
├── utils/              # Utility functions and services
│   ├── hooks/          # Custom React hooks
│   ├── services/       # API and service functions
│   └── stores/         # State management
├── styles/             # CSS and styling files
├── supabase/           # Database migrations and config
├── tests/              # Test files
└── public/             # Static assets
```

## 🔧 Configuration

### Supabase Configuration

The app automatically detects your environment and connects to the appropriate Supabase instance:

- **Development**: Uses local Supabase instance
- **Production**: Uses your remote Supabase project

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Your Supabase project URL | Auto-detected |
| `SUPABASE_ANON_KEY` | Your Supabase anonymous key | Auto-detected |
| `NODE_ENV` | Environment mode | `development` |
| `PORT` | Development server port | `3001` |

## 🚀 Available Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |
| `npm run test` | Run tests |
| `npm run lint` | Run ESLint |
| `npm run format` | Format code with Prettier |
| `npm run supabase:start` | Start local Supabase |
| `npm run supabase:stop` | Stop local Supabase |
| `npm run supabase:studio` | Open Supabase Studio |
| `npm run supabase:reset` | Reset local database |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit your changes: `git commit -am 'Add feature'`
4. Push to the branch: `git push origin feature-name`
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: Check the docs folder for detailed guides
- **Issues**: Report bugs and request features via GitHub Issues
- **Community**: Join our community discussions

## 🔮 Roadmap

- [ ] Mobile app (React Native)
- [ ] Advanced AI matching algorithms
- [ ] Food safety verification system
- [ ] Integration with food banks and charities
- [ ] Multi-language support
- [ ] Advanced analytics and reporting

---

Built with ❤️ by the DoGoods Team
