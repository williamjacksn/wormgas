import aiohttp
import discord.ext.commands
import logging
import os

from wormgas.models import Database

log = logging.getLogger(__name__)


class Wormgas(discord.ext.commands.Bot):
    def __init__(self, command_prefix, **options):
        super().__init__(command_prefix, **options)
        self.db = Database(os.getenv("DATABASE", "/etc/wormgas/config.db"))
        self.session = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(
            loop=self.loop, timeout=aiohttp.ClientTimeout(total=10)
        )
        extension_names = [
            "wormgas.cogs.chat",
            "wormgas.cogs.config",
            "wormgas.cogs.rainwave",
            "wormgas.cogs.rand",
            "wormgas.cogs.roles",
            "wormgas.cogs.rps",
            "wormgas.cogs.wiki",
            "wormgas.cogs.wolframalpha",
        ]
        for extension_name in extension_names:
            await self.load_extension(extension_name)


def main():
    log.info("Starting wormgas")
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = Wormgas(command_prefix="!", pm_help=True, intents=intents)
    bot.db.migrate()
    token = bot.db.config_get("discord:token")
    bot.run(token, log_handler=None)
