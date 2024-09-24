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

    def __init__(self, command_prefix, **options):
        super().__init__(command_prefix, **options)
        self.config = ConfigManager(pathlib.Path(os.getenv('CONFIG_FILE', '/etc/wormgas/_config.json')))
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
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = Wormgas(command_prefix='!', pm_help=True, intents=intents)
    bot.db.migrate()
    rps_conf = ConfigManager(pathlib.Path('/etc/wormgas/_rps.json'))
    for key in rps_conf.keys():
        rps_dict = rps_conf[key]
        rps_dict['user_id'] = key
        bot.db.rps_set(rps_dict)
    token = bot.db.config_get('discord:token')
    bot.run(token, log_handler=None)
