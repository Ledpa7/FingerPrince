# Server Vibe - Web (Step 3)

## Setup
```powershell
cd web
copy .env.example .env.local
npm install
npm run dev
```

## Required env
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_DEMO_USER_ID` (optional fallback)

## Supabase notes
- Enable Anonymous sign-in in Supabase Auth if you want auto-session.
- Chat inserts into `public.commands` with `status = 'pending'`.
- Realtime listens to INSERT/UPDATE on `commands` filtered by `user_id`.

## Deploy (Vercel)
1. Create a new Vercel project from this repo.
2. Set **Root Directory** to `web`.
3. Add Environment Variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_DEMO_USER_ID` (optional fallback)
4. Deploy, then open the Vercel URL on mobile.

Note: Vercel hosts only the web UI. The desktop Python agent must still run on your PC to process commands.

## PWA
- Manifest route: `/manifest.webmanifest`
- Service worker: `/sw.js`
- Add to Home Screen supported on mobile browsers.
