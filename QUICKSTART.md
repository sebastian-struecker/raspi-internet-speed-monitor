# Quick Start Guide

## Local Development (5 seconds)

```bash
git clone <your-repo-url>
cd raspi-internet-speed-monitor
docker compose up -d --build
```

Open http://localhost:8080/

Done! 🎉

---

## Production Deployment on Raspberry Pi

### 1. Clone and setup

```bash
git clone <your-repo-url>
cd raspi-internet-speed-monitor
```

### 2. Create external network

```bash
docker network create webapps_network
```

### 3. Configure nginx (see NGINX_PROXY_SETUP.md)

### 4. Deploy

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### 5. Access

Open http://raspberry-pi-ip:8080/internet-speed-dashboard/

---

## What Just Happened?

### Local Development
- Used `.env.local` (automatically created on first run)
- Created local Docker network
- Exposed port 8080 directly
- No URL prefix

### Production
- Used `.env` with `/internet-speed-dashboard` prefix
- Connected to external `webapps_network`
- Works with nginx reverse proxy
- Shares port 8080 with other apps

---

## Common Commands

```bash
# Local development
docker compose up -d              # Start
docker compose down               # Stop
docker compose logs -f            # View logs

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d    # Start
docker compose -f docker-compose.yml -f docker-compose.prod.yml down     # Stop
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f  # Logs
```

---

## Next Steps

- **Customize settings:** Edit `.env.local` (local) or `.env` (production)
- **Auto-start on boot:** See README.md "Auto-start on boot" section
- **Configure nginx:** See NGINX_PROXY_SETUP.md
- **Understand architecture:** See CLAUDE.md

---

## Need Help?

- Full documentation: README.md
- Deployment modes: DEPLOYMENT_MODES.md
- Issues: https://github.com/your-username/raspi-internet-speed-monitor/issues
