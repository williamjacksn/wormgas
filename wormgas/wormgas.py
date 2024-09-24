__version__ = '2024.0'

import aiohttp
import discord
import discord.ext.commands as cmds
import logging
import os
import pathlib

from wormgas.config import ConfigManager
from wormgas.models import Database

log = logging.getLogger(__name__)


class Wormgas(cmds.Bot):

    def __init__(self, config_path: pathlib.Path, command_prefix, **options):
        super().__init__(command_prefix, **options)
        self.config = ConfigManager(config_path)
        self.db = Database(os.getenv('DATABASE', '/etc/wormgas/config.db'))
        self.session = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(loop=self.loop, timeout=aiohttp.ClientTimeout(total=10))
        extension_names = [
            'wormgas.cogs.chat',
            'wormgas.cogs.config',
            'wormgas.cogs.rainwave',
            'wormgas.cogs.rand',
            'wormgas.cogs.roles',
            'wormgas.cogs.rps',
            'wormgas.cogs.wiki',
            'wormgas.cogs.wolframalpha',
        ]
        for extension_name in extension_names:
            await self.load_extension(extension_name)


def main():
    log.info(f'wormgas {__version__}')
    config_file = os.getenv('CONFIG_FILE', '/opt/wormgas/_config.json')
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = Wormgas(config_path=pathlib.Path(config_file).resolve(), command_prefix='!', pm_help=True, intents=intents)
    bot.db.migrate()
    token = bot.config.get('discord:token')
    bot.db.config_set('discord:token', token)
    bot.run(token, log_handler=None)
