# Deployment Modes

This application automatically detects your environment and uses the appropriate configuration.

## 🏠 Local Development Mode (Automatic)

**Just run:**
```bash
docker compose up -d --build
```

That's it! The application automatically:
- Uses `.env.local` for configuration (git-ignored)
- Creates a local Docker network
- Exposes port 8080 for direct access
- No URL prefix needed

**Access:**
- Dashboard: http://localhost:8080/
- API: http://localhost:8080/api/history

**Configuration file:** `.env.local` (automatically created, git-ignored)

---

## 🌐 Production/Reverse Proxy Mode

For deployment behind nginx on Raspberry Pi:

### Prerequisites

1. **Create external Docker network:**
   ```bash
   docker network create webapps_network
   ```

2. **Configure nginx** (see NGINX_PROXY_SETUP.md)
   - Nginx must be running and exposing port 8080
   - Nginx routes `/internet-speed-dashboard/` to this container

### Deploy

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

**Access:**
- Dashboard: http://raspberry-pi-ip:8080/internet-speed-dashboard/
- API: http://raspberry-pi-ip:8080/internet-speed-dashboard/api/history

**Configuration file:** `.env` (for production settings)

**Important:** In production mode, the speed monitor does NOT expose port 8080 directly. Nginx handles external access and routes traffic to the container via the `webapps_network` Docker network.

---

## 📁 File Structure

```
.
├── docker-compose.yml              # Base configuration
├── docker-compose.override.yml     # Local dev (auto-loaded, git-ignored)
├── docker-compose.prod.yml         # Production (use with -f flag)
├── .env                            # Production config (can commit)
├── .env.local                      # Local config (git-ignored, auto-created)
└── .env.example                    # Template for production
```

### How Auto-Detection Works

**Local Development:**
- `docker compose up` automatically loads `docker-compose.override.yml`
- Override file uses `.env.local` for environment variables
- Network created automatically (not external)
- Port 8080 exposed directly for testing

**Production:**
- Explicit command: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up`
- Uses `.env` for environment variables
- External network required (`webapps_network`)
- URL prefix: `/internet-speed-dashboard`
- **No port exposure** - nginx handles external access via Docker network

---

## 🔄 Switching Between Modes

### Local → Production

On your Raspberry Pi:

```bash
# Ensure external network exists
docker network create webapps_network

# Deploy with production config
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Production → Local

```bash
# Stop production
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# Start local (uses override automatically)
docker compose up -d --build
```

---

## ⚙️ Configuration Reference

### `.env.local` (Local Development)
```bash
URL_PREFIX=                    # Empty for direct access
NETWORK_EXTERNAL=false         # Not used (override controls this)
DASHBOARD_PORT=8080
LOG_LEVEL=INFO
```

### `.env` (Production)
```bash
URL_PREFIX=/internet-speed-dashboard
DASHBOARD_PORT=8080
LOG_LEVEL=INFO
```

---

## 🐛 Troubleshooting

### "Network webapps_network not found" (Production)

**Solution:**
```bash
docker network create webapps_network
```

### "Port 8080 already allocated" (Production)

This is **expected**! In production mode, the speed monitor doesn't expose ports.

**Cause:** Your nginx reverse proxy is already using port 8080.

**Solution:** Make sure you're using the production compose command:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The production config does NOT expose ports - nginx routes traffic via Docker network.

### Dashboard shows blank page in production

**Check:**
1. Nginx config routes `/internet-speed-dashboard/` correctly
2. Nginx container is on `webapps_network`
3. URL_PREFIX is set in `.env`
4. Used production compose file: `-f docker-compose.prod.yml`
5. Nginx is routing to `internet-speed-monitor-dashboard:8080` (container name)

### Changes to .env.local not taking effect

**Solution:**
```bash
docker compose down
docker compose up -d --build
```

### Want to customize local settings

Edit `.env.local` (git-ignored) - changes won't affect git or production.

---

## 💡 Best Practices

✅ **Do:**
- Use `docker compose up` for local development
- Edit `.env.local` for local customization
- Use production compose file on Raspberry Pi
- Keep `.env` in version control with production defaults

❌ **Don't:**
- Commit `.env.local` or `docker-compose.override.yml`
- Mix local and production settings in same file
- Forget to create external network before production deploy
