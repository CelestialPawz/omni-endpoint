# OMNI Endpoint

Discord bot for server management + StarServer/Pi-hole monitoring.  
Developed by Axel Thornton @ [Crystal Kitsune Studios](https://crystal-kitsune-studios.com).

## Features

- **Auto-mod** — spam, caps, and banned link detection
- **Welcome / farewell** messages
- **Auto-role** on join + role management commands
- **Moderation** — `!ban`, `!kick`, `!mute`, `!purge`, `!unban`
- **Audit logs** — deleted/edited messages, bans
- **Custom commands** — `!info`, `!rules`, `!cks`
- **StarServer status** — Prometheus metrics (CPU, RAM, disk, uptime) with SSH fallback
- **Pi-hole status** — query stats, block rate, client count
- **Automatic alerts** — posts to status channel when resources hit >90% or Pi-hole goes down

## Setup

1. Copy `.env.example` to `.env` and fill in your values
2. Deploy on StarServer:

```bash
docker compose up -d --build
```

## Commands

| Command | Description |
|---|---|
| `!serverstatus` / `!ss` | Full StarServer + Pi-hole status |
| `!sshstatus` | Deep SSH dump (admin only) |
| `!pihole` | Pi-hole stats only |
| `!ban @user [reason]` | Ban a member |
| `!kick @user [reason]` | Kick a member |
| `!mute @user [minutes] [reason]` | Timeout a member |
| `!purge [amount]` | Bulk delete messages |
| `!unban [user_id]` | Unban by ID |
| `!role @user RoleName` | Assign a role |
| `!removerole @user RoleName` | Remove a role |
| `!info` | Bot info |
| `!rules` | Server rules |
| `!cks` | CKS website |
