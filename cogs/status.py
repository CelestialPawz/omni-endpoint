import discord
from discord.ext import commands
from discord.ext import tasks
import aiohttp
import asyncio
import paramiko
import ssl
import config

class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.alert_loop.start()

    def cog_unload(self):
        self.alert_loop.cancel()

    async def _prom_query(self, session: aiohttp.ClientSession, query: str) -> float | None:
        try:
            url = f"{config.PROMETHEUS_URL}/api/v1/query"
            async with session.get(url, params={"query": query}, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                results = data.get("data", {}).get("result", [])
                if results:
                    return float(results[0]["value"][1])
        except Exception:
            pass
        return None

    async def get_prometheus_stats(self) -> dict:
        async with aiohttp.ClientSession() as session:
            cpu = await self._prom_query(
                session,
                '100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
            )
            ram_used  = await self._prom_query(session, 'node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes')
            ram_total = await self._prom_query(session, 'node_memory_MemTotal_bytes')
            disk_used  = await self._prom_query(session, 'node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_free_bytes{mountpoint="/"}')
            disk_total = await self._prom_query(session, 'node_filesystem_size_bytes{mountpoint="/"}')
            uptime_s  = await self._prom_query(session, 'node_time_seconds - node_boot_time_seconds')

        def to_gb(v): return round(v / 1024**3, 2) if v else None
        def uptime_str(s):
            if s is None: return "N/A"
            s = int(s)
            d, r = divmod(s, 86400); h, r = divmod(r, 3600); m = r // 60
            return f"{d}d {h}h {m}m"

        return {
            "cpu": round(cpu, 1) if cpu is not None else None,
            "ram_used_gb": to_gb(ram_used),
            "ram_total_gb": to_gb(ram_total),
            "disk_used_gb": to_gb(disk_used),
            "disk_total_gb": to_gb(disk_total),
            "uptime": uptime_str(uptime_s),
        }

    async def get_ssh_stats(self) -> dict:
        def _run():
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=config.STARSERVER_HOST,
                port=config.STARSERVER_PORT,
                username=config.STARSERVER_USER,
                key_filename=config.STARSERVER_KEY_PATH,
                timeout=8,
            )
            results = {}
            cmds = {
                "uptime":    "uptime -p",
                "cpu":       "top -bn1 | grep Cpu | awk '{print $2}'",
                "ram":       "free -h | awk '/Mem:/ {print $3, $2}'",
                "disk":      "df -h / | awk 'NR==2 {print $3, $2, $5}'",
                "docker_ps": "docker ps --format '.Names: .Status'",
                "fail2ban":  "sudo fail2ban-client status sshd 2>/dev/null | grep Currently || echo N/A",
            }
            for key, cmd in cmds.items():
                _, stdout, _ = client.exec_command(cmd)
                results[key] = stdout.read().decode().strip()
            client.close()
            results["source"] = "ssh"
            return results
        try:
            return await asyncio.to_thread(_run)
        except Exception as e:
            return {"error": str(e), "source": "ssh"}

    async def get_pihole_stats(self) -> dict:
        """Pi-hole v6 API: password auth -> session SID -> stats."""
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                # Authenticate
                async with session.post(
                    f"{config.PIHOLE_URL}/auth",
                    json={"password": config.PIHOLE_API_KEY},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as r:
                    auth = await r.json(content_type=None)
                    sid = auth.get("session", {}).get("sid")
                    if not sid:
                        return {"error": "Pi-hole auth failed - check PIHOLE_API_KEY in .env"}

                headers = {"X-FTL-SID": sid}

                # Stats summary (includes gravity.domains_being_blocked)
                async with session.get(
                    f"{config.PIHOLE_URL}/stats/summary",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as r:
                    data = await r.json(content_type=None)

                # Blocking status
                status = "unknown"
                try:
                    async with session.get(
                        f"{config.PIHOLE_URL}/dns/blocking",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as r:
                        b = await r.json(content_type=None)
                        status = b.get("blocking", "unknown")
                except Exception:
                    pass

                # Clean up session
                await session.delete(
                    f"{config.PIHOLE_URL}/auth",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=3)
                )

                queries = data.get("queries", {})
                clients = data.get("clients", {})
                gravity = data.get("gravity", {})

                domains_raw = gravity.get("domains_being_blocked")
                try:
                    domains_fmt = f"{int(domains_raw):,}" if domains_raw is not None else "N/A"
                except (ValueError, TypeError):
                    domains_fmt = str(domains_raw)

                return {
                    "status":          status,
                    "queries_today":   queries.get("total", "N/A"),
                    "blocked_today":   queries.get("blocked", "N/A"),
                    "block_pct":       queries.get("percent_blocked", 0),
                    "domains_blocked": domains_fmt,
                    "clients":         clients.get("active", "N/A"),
                }
        except Exception as e:
            return {"error": str(e)}

    @commands.command(name="serverstatus", aliases=["ss"])
    async def server_status(self, ctx):
        """Full StarServer status report."""
        await ctx.typing()
        prom   = await self.get_prometheus_stats()
        pihole = await self.get_pihole_stats()

        embed = discord.Embed(title="\u2699\ufe0f StarServer Status", color=discord.Color.blurple())

        if prom.get("cpu") is not None:
            cpu_val  = prom["cpu"]
            cpu_icon = "\U0001f7e2" if cpu_val < 70 else "\U0001f7e1" if cpu_val < 90 else "\U0001f534"
            embed.add_field(
                name="\U0001f5a5\ufe0f System (Prometheus)",
                value=(
                    f"**CPU:** {cpu_icon} {cpu_val}%\n"
                    f"**RAM:** {prom['ram_used_gb']} / {prom['ram_total_gb']} GB\n"
                    f"**Disk:** {prom['disk_used_gb']} / {prom['disk_total_gb']} GB\n"
                    f"**Uptime:** {prom['uptime']}"
                ),
                inline=False
            )
        else:
            ssh = await self.get_ssh_stats()
            if "error" not in ssh:
                embed.add_field(
                    name="\U0001f5a5\ufe0f System (SSH fallback)",
                    value=(
                        f"**CPU:** {ssh.get('cpu', 'N/A')}%\n"
                        f"**RAM:** {ssh.get('ram', 'N/A')}\n"
                        f"**Disk:** {ssh.get('disk', 'N/A')}\n"
                        f"**Uptime:** {ssh.get('uptime', 'N/A')}"
                    ),
                    inline=False
                )
                if ssh.get("docker_ps"):
                    embed.add_field(name="\U0001f433 Docker", value=f"```{ssh['docker_ps'][:800]}```", inline=False)
            else:
                embed.add_field(name="\u26a0\ufe0f System", value=f"Unreachable: {ssh['error']}", inline=False)

        if "error" not in pihole:
            ph_icon = "\U0001f7e2" if pihole["status"] == "enabled" else "\U0001f534"
            embed.add_field(
                name="\U0001f310 Pi-hole (Starviewer)",
                value=(
                    f"**Status:** {ph_icon} {pihole['status'].capitalize()}\n"
                    f"**Queries today:** {pihole['queries_today']}\n"
                    f"**Blocked today:** {pihole['blocked_today']} ({round(pihole['block_pct'], 1)}%)\n"
                    f"**Blocklist:** {pihole['domains_blocked']} domains\n"
                    f"**Clients:** {pihole['clients']}"
                ),
                inline=False
            )
        else:
            embed.add_field(name="\u26a0\ufe0f Pi-hole", value=f"Unreachable: {pihole['error']}", inline=False)

        embed.set_footer(text="OMNI Endpoint | Crystal Kitsune Studios")
        await ctx.send(embed=embed)

    @commands.command(name="sshstatus")
    @commands.has_permissions(administrator=True)
    async def ssh_status(self, ctx):
        """Full SSH-based deep status dump (admin only)."""
        await ctx.typing()
        ssh = await self.get_ssh_stats()
        if "error" in ssh:
            await ctx.send(f"\u274c SSH failed: `{ssh['error']}`")
            return
        embed = discord.Embed(title="\U0001f510 StarServer \u2014 SSH Deep Status", color=discord.Color.green())
        embed.add_field(name="Uptime", value=ssh.get("uptime", "N/A"), inline=True)
        embed.add_field(name="CPU",    value=f"{ssh.get('cpu', 'N/A')}%", inline=True)
        embed.add_field(name="RAM",    value=ssh.get("ram", "N/A"), inline=True)
        embed.add_field(name="Disk",   value=ssh.get("disk", "N/A"), inline=False)
        embed.add_field(name="\U0001f433 Docker", value=f"```{ssh.get('docker_ps', 'N/A')[:800]}```", inline=False)
        embed.add_field(name="Fail2Ban (sshd)", value=ssh.get("fail2ban", "N/A"), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="pihole")
    async def pihole_cmd(self, ctx):
        """Pi-hole stats."""
        data = await self.get_pihole_stats()
        if "error" in data:
            await ctx.send(f"\u274c Pi-hole unreachable: `{data['error']}`")
            return
        ph_icon = "\U0001f7e2" if data["status"] == "enabled" else "\U0001f534"
        embed = discord.Embed(title="\U0001f310 Pi-hole Status (Starviewer)", color=discord.Color.dark_blue())
        embed.add_field(name="Status",            value=f"{ph_icon} {data['status'].capitalize()}", inline=True)
        embed.add_field(name="Queries Today",     value=str(data["queries_today"]), inline=True)
        embed.add_field(name="Blocked Today",     value=f"{data['blocked_today']} ({round(data['block_pct'],1)}%)", inline=True)
        embed.add_field(name="Blocklist Domains", value=str(data["domains_blocked"]), inline=True)
        embed.add_field(name="Active Clients",    value=str(data["clients"]), inline=True)
        await ctx.send(embed=embed)

    @tasks.loop(minutes=5)
    async def alert_loop(self):
        ch = self.bot.get_channel(config.STATUS_CHANNEL_ID)
        if not ch:
            return
        prom   = await self.get_prometheus_stats()
        alerts = []

        if prom.get("cpu") is not None and prom["cpu"] > 90:
            alerts.append(f"\U0001f534 **CPU critical:** {prom['cpu']}%")
        if prom.get("ram_used_gb") and prom.get("ram_total_gb"):
            if prom["ram_used_gb"] / prom["ram_total_gb"] > 0.90:
                alerts.append(f"\U0001f534 **RAM critical:** {prom['ram_used_gb']}/{prom['ram_total_gb']} GB")
        if prom.get("disk_used_gb") and prom.get("disk_total_gb"):
            if prom["disk_used_gb"] / prom["disk_total_gb"] > 0.90:
                alerts.append(f"\U0001f534 **Disk critical:** {prom['disk_used_gb']}/{prom['disk_total_gb']} GB")

        pihole = await self.get_pihole_stats()
        if "error" in pihole:
            alerts.append(f"\u26a0\ufe0f **Pi-hole unreachable:** `{pihole['error']}`")
        elif pihole["status"] != "enabled":
            alerts.append(f"\U0001f534 **Pi-hole is DISABLED** \u2014 DNS blocking is off!")

        if alerts:
            embed = discord.Embed(
                title="\U0001f6a8 StarServer Alert",
                description="\n".join(alerts),
                color=discord.Color.red()
            )
            await ch.send(embed=embed)

    @alert_loop.before_loop
    async def before_alert(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Status(bot))
