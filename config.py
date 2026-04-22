import os
from dotenv import load_dotenv

load_dotenv()

TOKEN                = os.getenv("DISCORD_TOKEN")
GUILD_ID             = int(os.getenv("GUILD_ID", 0))
LOG_CHANNEL_ID       = int(os.getenv("LOG_CHANNEL_ID", 0))
WELCOME_CHANNEL_ID   = int(os.getenv("WELCOME_CHANNEL_ID", 0))
AUTO_ROLE_ID         = int(os.getenv("AUTO_ROLE_ID", 0))
STATUS_CHANNEL_ID    = int(os.getenv("STATUS_CHANNEL_ID", 0))
MODMAIL_CATEGORY_ID  = int(os.getenv("MODMAIL_CATEGORY_ID", 0))

STARSERVER_HOST      = os.getenv("STARSERVER_HOST", "starserver")
STARSERVER_PORT      = int(os.getenv("STARSERVER_PORT", 2222))
STARSERVER_USER      = os.getenv("STARSERVER_USER", "celestialpawz")
STARSERVER_KEY_PATH  = os.getenv("STARSERVER_KEY_PATH", "/root/.ssh/id_rsa")

PROMETHEUS_URL       = os.getenv("PROMETHEUS_URL", "http://starserver:9090")

PIHOLE_URL           = os.getenv("PIHOLE_URL", "http://starserver/admin/api.php")
PIHOLE_API_KEY       = os.getenv("PIHOLE_API_KEY", "")

PTERODACTYL_URL      = os.getenv("PTERODACTYL_URL", "https://panel.starlightsserverhosting.uk")
PTERODACTYL_API_KEY  = os.getenv("PTERODACTYL_API_KEY", "")

GROQ_API_KEY         = os.getenv("GROQ_API_KEY", "")

PREFIX               = "!"
