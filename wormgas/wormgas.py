import aiohttp
import discord.ext.commands as cmds
import logging
import os
import pathlib
import sys

from wormgas.config import ConfigManager


class Wormgas(cmds.Bot):

    def __init__(self, config_path: pathlib.Path, command_prefix, **options):
        super().__init__(command_prefix, **options)
        self.config = ConfigManager(config_path)
        self.session = aiohttp.ClientSession(loop=self.loop)


def main():
    log_format = os.getenv('LOG_FORMAT', '%(asctime)s | %(name)s | %(levelname)s | %(message)s')
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    logging.basicConfig(level=log_level, format=log_format, stream=sys.stdout)
    config_file = os.getenv('CONFIG_FILE', '/opt/wormgas/_config.json')
    bot = Wormgas(config_path=pathlib.Path(config_file).resolve(), command_prefix='!', pm_help=True)
    bot.load_extension('wormgas.cogs.chat')
    bot.load_extension('wormgas.cogs.config')
    bot.load_extension('wormgas.cogs.rainwave')
    bot.load_extension('wormgas.cogs.rand')
    bot.load_extension('wormgas.cogs.rps')
    bot.load_extension('wormgas.cogs.wiki')
    bot.load_extension('wormgas.cogs.wolframalpha')
    bot.run(bot.config.get('discord:token'))
