# 🏭 Ritefoods Limited — Deployment Guide

## Prerequisites
- Docker + Docker Compose installed on the server
- SQL Server accessible from the server on the LAN
- Server has a static LAN IP (set this in your router's DHCP settings)

---

## 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
```env
DB_SERVER=192.168.1.xx        # SQL Server IP on your LAN
DB_NAME=ritefoods_prod
DB_USER=ritefoods_user
DB_PASSWORD=your-password
DB_DRIVER=ODBC Driver 17 for SQL Server
```

---

## 2. Build and start

```bash
docker compose up -d --build
```

The app is now accessible from **any device on the LAN** at:
```
http://192.168.1.xx
```
Replace with your server's actual LAN IP. No port number needed.

---

## 3. Find your server's LAN IP

**Windows:**
```
ipconfig
```
Look for `IPv4 Address` under your active network adapter.

**Linux:**
```
ip addr show
```

---

## 4. Make the IP permanent (recommended)

Log into your router admin page and reserve the server's IP address
against its MAC address under DHCP settings. This ensures the server
always gets the same IP — workers bookmark it once and it never changes.

---

## 5. Useful commands

```bash
# View live logs
docker compose logs -f app

# Restart app after a code update
docker compose up -d --build app

# Stop everything
docker compose down

# Check status
docker compose ps
```

---

## 6. Updating the app

```bash
# Rebuild and redeploy (zero downtime swap)
docker compose up -d --build app
```