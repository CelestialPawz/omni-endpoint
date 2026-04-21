import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import paramiko
import ssl
import config

_DOCKER_FMT = "{" + "{.Names}}: {" + "{.Status}}"

def _uptime_str(ms: int) -> str:
    s = ms // 1000
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts) if parts else "0m"


class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.alert_loop.start()

    def cog_unload(self):
        self.alert_loop.cancel()

    # ── Prometheus ──────────────────────────────────────────────────────────

    async def _prom_query(self, session, query):
        try:
            async with session.get(
                f"{config.PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                data = await r.json()
                results = data.get("data", {}).get("result", [])
                if results:
                    return float(results[0]["value"][1])
        except Exception:
            pass
        return None

    async def get_prometheus_stats(self):
        async with aiohttp.ClientSession() as s:
            cpu       = await self._prom_query(s, '100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)')
            ram_used  = await self._prom_query(s, 'node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes')
            ram_total = await self._prom_query(s, 'node_memory_MemTotal_bytes')
            disk_used = await self._prom_query(s, 'node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_free_bytes{mountpoint="/"}')
            disk_tot  = await self._prom_query(s, 'node_filesystem_size_bytes{mountpoint="/"}')
            uptime_s  = await self._prom_query(s, 'node_time_seconds - node_boot_time_seconds')

        def gb(v): return round(v / 1024**3, 2) if v else None
        def upfmt(s):
            if s is None: return "N/A"
            s = int(s); d, r = divmod(s, 86400); h, r = divmod(r, 3600); m = r // 60
            return f"{d}d {h}h {m}m"
        return {
            "cpu": round(cpu, 1) if cpu is not None else None,
            "ram_used_gb": gb(ram_used), "ram_total_gb": gb(ram_total),
            "disk_used_gb": gb(disk_used), "disk_total_gb": gb(disk_tot),
            "uptime": upfmt(uptime_s),
        }

    # ── SSH ──────────────────────────────────────────────────────────────────

    async def get_ssh_stats(self):
        def _run():
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(hostname=config.STARSERVER_HOST, port=config.STARSERVER_PORT,
                      username=config.STARSERVER_USER, key_filename=config.STARSERVER_KEY_PATH, timeout=8)
            cmds = {
                "uptime":    "uptime -p",
                "cpu":       "top -bn1 | grep Cpu | awk '{print $2}'",
                "ram":       "free -h | awk '/Mem:/ {print $3, $2}'",
                "disk":      "df -h / | awk 'NR==2 {print $3, $2, $5}'",
                "docker_ps": f"docker ps --format '{_DOCKER_FMT}'",
                "fail2ban":  "sudo fail2ban-client status sshd 2>/dev/null | grep -E 'Currently (failed|banned)' || echo 'N/A'",
            }
            res = {}
            for k, cmd in cmds.items():
                _, out, _ = c.exec_command(cmd)
                res[k] = out.read().decode().strip()
            c.close()
            res["source"] = "ssh"
            return res
        try:
            return await asyncio.to_thread(_run)
        except Exception as e:
            return {"error": str(e), "source": "ssh"}

    # ── Pi-hole ───────────────────────────────────────────────────────────────

    async def get_pihole_stats(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ctx)) as s:
                async with s.post(f"{config.PIHOLE_URL}/auth",
                                  json={"password": config.PIHOLE_API_KEY},
                                  timeout=aiohttp.ClientTimeout(total=5)) as r:
                    auth = await r.json(content_type=None)
                    sid  = auth.get("session", {}).get("sid")
                    if not sid:
                        return {"error": "Pi-hole auth failed - check PIHOLE_API_KEY in .env"}
                hdrs = {"X-FTL-SID": sid}
                async with s.get(f"{config.PIHOLE_URL}/stats/summary", headers=hdrs,
                                 timeout=aiohttp.ClientTimeout(total=5)) as r:
                    data = await r.json(content_type=None)
                status = "unknown"
                try:
                    async with s.get(f"{config.PIHOLE_URL}/dns/blocking", headers=hdrs,
                                     timeout=aiohttp.ClientTimeout(total=5)) as r:
                        status = (await r.json(content_type=None)).get("blocking", "unknown")
                except Exception:
                    pass
                await s.delete(f"{config.PIHOLE_URL}/auth", headers=hdrs,
                               timeout=aiohttp.ClientTimeout(total=3))
                q = data.get("queries", {})
                g = data.get("gravity", {})
                try:
                    domains = f"{int(g.get('domains_being_blocked', 0)):,}"
                except Exception:
                    domains = str(g.get("domains_being_blocked", "N/A"))
                return {
                    "status":          status,
                    "queries_today":   q.get("total", "N/A"),
                    "blocked_today":   q.get("blocked", "N/A"),
                    "block_pct":       q.get("percent_blocked", 0),
                    "domains_blocked": domains,
                    "clients":         data.get("clients", {}).get("active", "N/A"),
                }
        except Exception as e:
            return {"error": str(e)}

    # ── Pterodactyl ───────────────────────────────────────────────────────────

    async def get_pterodactyl_stats(self):
        if not config.PTERODACTYL_API_KEY:
            return [{"error": "PTERODACTYL_API_KEY not set in .env"}]
        base  = config.PTERODACTYL_URL.rstrip("/")
        hdrs  = {"Authorization": f"Bearer {config.PTERODACTYL_API_KEY}", "Accept": "application/json"}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{base}/api/client/servers", headers=hdrs,
                                 timeout=aiohttp.ClientTimeout(total=8)) as r:
                    data = await r.json(content_type=None)
                servers = []
                for srv in data.get("data", []):
                    attr   = srv.get("attributes", {})
                    sid    = attr.get("identifier", "")
                    name   = attr.get("name", "Unknown")
                    limits = attr.get("limits", {})
                    try:
                        async with s.get(f"{base}/api/client/servers/{sid}/resources",
                                         headers=hdrs, timeout=aiohttp.ClientTimeout(total=5)) as r2:
                            res      = await r2.json(content_type=None)
                        ra       = res.get("attributes", {})
                        state    = ra.get("current_state", "unknown")
                        resources = ra.get("resources", {})
                        servers.append({
                            "name":          name,
                            "identifier":    sid,
                            "state":         state,
                            "cpu":           round(resources.get("cpu_absolute", 0), 1),
                            "cpu_limit":     limits.get("cpu", 100),
                            "mem_mb":        round(resources.get("memory_bytes", 0) / 1024**2, 1),
                            "mem_limit_mb":  limits.get("memory", 0),
                            "disk_mb":       round(resources.get("disk_bytes", 0) / 1024**2, 1),
                            "disk_limit_mb": limits.get("disk", 0),
                            "uptime":        _uptime_str(resources.get("uptime", 0)) if state == "running" else "\u2014",
                        })
                    except Exception as e:
                        servers.append({"name": name, "identifier": sid, "state": "unknown", "error": str(e)})
                return servers or [{"error": "No servers found"}]
        except Exception as e:
            return [{"error": str(e)}]

    # ── Commands ─────────────────────────────────────────────────────────────

    @commands.command(name="serverstatus", aliases=["ss"])
    async def server_status(self, ctx):
        await ctx.typing()
        prom, pihole, ptero = await asyncio.gather(
            self.get_prometheus_stats(),
            self.get_pihole_stats(),
            self.get_pterodactyl_stats(),
        )
        embed = discord.Embed(title="\u2699\ufe0f StarServer Status", color=discord.Color.blurple())

        # System
        if prom.get("cpu") is not None:
            ci = "\U0001f7e2" if prom["cpu"] < 70 else "\U0001f7e1" if prom["cpu"] < 90 else "\U0001f534"
            embed.add_field(name="\U0001f5a5\ufe0f System", inline=False, value=(
                f"**CPU:** {ci} {prom['cpu']}%\n"
                f"**RAM:** {prom['ram_used_gb']} / {prom['ram_total_gb']} GB\n"
                f"**Disk:** {prom['disk_used_gb']} / {prom['disk_total_gb']} GB\n"
                f"**Uptime:** {prom['uptime']}"
            ))
        else:
            ssh = await self.get_ssh_stats()
            if "error" not in ssh:
                embed.add_field(name="\U0001f5a5\ufe0f System (SSH)", inline=False, value=(
                    f"**CPU:** {ssh.get('cpu','N/A')}%  **RAM:** {ssh.get('ram','N/A')}\n"
                    f"**Disk:** {ssh.get('disk','N/A')}  **Uptime:** {ssh.get('uptime','N/A')}"
                ))
                if ssh.get("docker_ps"):
                    embed.add_field(name="\U0001f433 Docker", value=f"```{ssh['docker_ps'][:800]}```", inline=False)
            else:
                embed.add_field(name="\u26a0\ufe0f System", value=f"Unreachable: {ssh['error']}", inline=False)

        # Pi-hole
        if "error" not in pihole:
            pi = "\U0001f7e2" if pihole["status"] == "enabled" else "\U0001f534"
            embed.add_field(name="\U0001f310 Pi-hole", inline=False, value=(
                f"**Status:** {pi} {pihole['status'].capitalize()}\n"
                f"**Queries:** {pihole['queries_today']}  **Blocked:** {pihole['blocked_today']} ({round(pihole['block_pct'],1)}%)\n"
                f"**Blocklist:** {pihole['domains_blocked']} domains  **Clients:** {pihole['clients']}"
            ))
        else:
            embed.add_field(name="\u26a0\ufe0f Pi-hole", value=pihole["error"], inline=False)

        # Pterodactyl
        if ptero and "error" not in ptero[0]:
            lines = []
            for srv in ptero:
                if "error" in srv:
                    lines.append(f"\u26a0\ufe0f **{srv.get('name','?')}**: {srv['error']}")
                    continue
                icon = "\U0001f7e2" if srv["state"] == "running" else "\U0001f534" if srv["state"] == "offline" else "\U0001f7e1"
                lines.append(
                    f"{icon} **{srv['name']}** `{srv['state']}`\n"
                    f"\u00a0CPU {srv['cpu']}% \u00b7 RAM {srv['mem_mb']}/{srv['mem_limit_mb']} MB \u00b7 Up {srv['uptime']}"
                )
            embed.add_field(name="\U0001f9a4 Pterodactyl", value="\n".join(lines)[:1024] or "No servers.", inline=False)
        else:
            embed.add_field(name="\u26a0\ufe0f Pterodactyl", value=ptero[0].get("error", "No response") if ptero else "No response", inline=False)

        embed.set_footer(text="OMNI Endpoint | Crystal Kitsune Studios")
        await ctx.send(embed=embed)

    @commands.command(name="ptero", aliases=["pterodactyl", "servers"])
    async def ptero_cmd(self, ctx):
        """Show Pterodactyl server statuses. Usage: !ptero"""
        await ctx.typing()
        servers = await self.get_pterodactyl_stats()
        if servers and "error" in servers[0]:
            await ctx.send(f"\u274c Pterodactyl unreachable: `{servers[0]['error']}`")
            return
        embed = discord.Embed(title="\U0001f9a4 Pterodactyl \u2014 Server Status", color=discord.Color.green())
        for srv in servers:
            if "error" in srv:
                embed.add_field(name=f"\u26a0\ufe0f {srv.get('name','?')}", value=srv["error"], inline=False)
                continue
            state    = srv["state"]
            icon     = "\U0001f7e2" if state == "running" else "\U0001f534" if state == "offline" else "\U0001f7e1"
            mem_pct  = round((srv['mem_mb'] / srv['mem_limit_mb']) * 100) if srv.get('mem_limit_mb') else 0
            disk_pct = round((srv['disk_mb'] / srv['disk_limit_mb']) * 100) if srv.get('disk_limit_mb') else 0
            embed.add_field(
                name=f"{srv['name']} `{srv['identifier']}`",
                value=(
                    f"**State:** {icon} {state.capitalize()}\n"
                    f"**CPU:** {srv['cpu']}% / {srv['cpu_limit']}%\n"
                    f"**RAM:** {srv['mem_mb']} / {srv['mem_limit_mb']} MB ({mem_pct}%)\n"
                    f"**Disk:** {srv['disk_mb']} / {srv['disk_limit_mb']} MB ({disk_pct}%)\n"
                    f"**Uptime:** {srv['uptime']}"
                ),
                inline=False
            )
        embed.set_footer(text="panel.starlightsserverhosting.uk \u00b7 OMNI Endpoint")
        await ctx.send(embed=embed)

    @commands.command(name="sshstatus")
    @commands.has_permissions(administrator=True)
    async def ssh_status(self, ctx):
        await ctx.typing()
        ssh = await self.get_ssh_stats()
        if "error" in ssh:
            await ctx.send(f"\u274c SSH failed: `{ssh['error']}`")
            return
        embed = discord.Embed(title="\U0001f510 StarServer \u2014 SSH Deep Status", color=discord.Color.green())
        embed.add_field(name="Uptime", value=ssh.get("uptime","N/A"), inline=True)
        embed.add_field(name="CPU",    value=f"{ssh.get('cpu','N/A')}%", inline=True)
        embed.add_field(name="RAM",    value=ssh.get("ram","N/A"), inline=True)
        embed.add_field(name="Disk",   value=ssh.get("disk","N/A"), inline=False)
        embed.add_field(name="\U0001f433 Docker", value=f"```{ssh.get('docker_ps','N/A')[:800]}```", inline=False)
        embed.add_field(name="\U0001f6e1\ufe0f Fail2Ban", value=ssh.get("fail2ban","N/A"), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="pihole")
    async def pihole_cmd(self, ctx):
        data = await self.get_pihole_stats()
        if "error" in data:
            await ctx.send(f"\u274c Pi-hole unreachable: `{data['error']}`")
            return
        pi = "\U0001f7e2" if data["status"] == "enabled" else "\U0001f534"
        embed = discord.Embed(title="\U0001f310 Pi-hole Status", color=discord.Color.dark_blue())
        embed.add_field(name="Status",  value=f"{pi} {data['status'].capitalize()}", inline=True)
        embed.add_field(name="Queries", value=str(data["queries_today"]), inline=True)
        embed.add_field(name="Blocked", value=f"{data['blocked_today']} ({round(data['block_pct'],1)}%)", inline=True)
        embed.add_field(name="Blocklist", value=str(data["domains_blocked"]), inline=True)
        embed.add_field(name="Clients",   value=str(data["clients"]), inline=True)
        await ctx.send(embed=embed)

    # ── Alert loop ────────────────────────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def alert_loop(self):
        ch = self.bot.get_channel(config.STATUS_CHANNEL_ID)
        if not ch:
            return
        prom, pihole, ptero = await asyncio.gather(
            self.get_prometheus_stats(),
            self.get_pihole_stats(),
            self.get_pterodactyl_stats(),
        )
        alerts = []
        if prom.get("cpu") is not None and prom["cpu"] > 90:
            alerts.append(f"\U0001f534 **CPU critical:** {prom['cpu']}%")
        if prom.get("ram_used_gb") and prom.get("ram_total_gb"):
            if prom["ram_used_gb"] / prom["ram_total_gb"] > 0.90:
                alerts.append(f"\U0001f534 **RAM critical:** {prom['ram_used_gb']}/{prom['ram_total_gb']} GB")
        if prom.get("disk_used_gb") and prom.get("disk_total_gb"):
            if prom["disk_used_gb"] / prom["disk_total_gb"] > 0.90:
                alerts.append(f"\U0001f534 **Disk critical:** {prom['disk_used_gb']}/{prom['disk_total_gb']} GB")
        if "error" in pihole:
            alerts.append(f"\u26a0\ufe0f **Pi-hole unreachable:** `{pihole['error']}`")
        elif pihole["status"] != "enabled":
            alerts.append(f"\U0001f534 **Pi-hole DISABLED** \u2014 DNS blocking is off!")
        if ptero and "error" in ptero[0]:
            alerts.append(f"\u26a0\ufe0f **Pterodactyl unreachable:** `{ptero[0]['error']}`")
        else:
            for srv in (ptero or []):
                if "error" in srv:
                    continue
                if srv["state"] == "offline":
                    alerts.append(f"\U0001f534 **{srv['name']}** is offline on Pterodactyl")
        if alerts:
            await ch.send(embed=discord.Embed(
                title="\U0001f6a8 StarServer Alert",
                description="\n".join(alerts),
                color=discord.Color.red()
            ))

    @alert_loop.before_loop
    async def before_alert(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Status(bot))
