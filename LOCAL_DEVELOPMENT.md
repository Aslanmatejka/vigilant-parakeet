# Local Development Setup

Your DoGoods app is now configured to work with a local Supabase instance for development.

## 🚀 Quick Start

1. **Start local Supabase:**
   ```bash
   npm run supabase:start
   ```

2. **Start the development server:**
   ```bash
   npm run dev
   ```

3. **Open your app:**
   - App: http://localhost:3000
   - Database Studio: http://127.0.0.1:54323

## 📍 Service URLs

- **App**: http://localhost:3000
- **Supabase API**: http://127.0.0.1:54321
- **Database Studio**: http://127.0.0.1:54323
- **Email Testing (Inbucket)**: http://127.0.0.1:54324
- **Database**: postgresql://postgres:postgres@127.0.0.1:54322/postgres

## 🛠 Available Commands

| Command | Description |
|---------|-------------|
| `npm run supabase:start` | Start local Supabase services |
| `npm run supabase:stop` | Stop local Supabase services |
| `npm run supabase:restart` | Restart local Supabase services |
| `npm run supabase:reset` | Reset local database (runs migrations) |
| `npm run supabase:studio` | Open database management studio |
| `npm run dev:local` | Start both Supabase and dev server |
| `node scripts/check-local.js` | Test local environment |

## 🔄 Environment Switching

The app automatically detects the environment:

- **Development**: Uses local Supabase (http://127.0.0.1:54321)
- **Production**: Uses production Supabase (configured in environment)

You can override this by setting environment variables in `.env`:

```env
NODE_ENV=development
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=your-local-anon-key
```

## 📊 Database Management

1. **View tables and data**: Open http://127.0.0.1:54323
2. **Run migrations**: `npm run supabase:reset`
3. **Add new migrations**: Place SQL files in `supabase/migrations/`

## 📧 Email Testing

All emails sent in development are captured by Inbucket:
- View emails at: http://127.0.0.1:54324
- No emails are actually sent in development

## 🔍 Troubleshooting

### Supabase won't start
- Make sure Docker is running
- Check if ports 54321-54324 are available
- Run `docker ps` to see running containers

### App can't connect to database
- Verify Supabase is running: `npm run supabase:start`
- Check console logs for connection errors
- Run connection test: `node scripts/check-local.js`

### Database schema issues
- Reset database: `npm run supabase:reset`
- Check migration files in `supabase/migrations/`

## 🔒 Authentication

Local Supabase uses the same authentication system as production:
- JWT tokens work the same way
- All auth providers are available (configure in `supabase/config.toml`)
- User sessions persist across development restarts
