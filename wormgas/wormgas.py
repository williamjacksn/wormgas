import aiohttp
import discord
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
        self.session = aiohttp.ClientSession(loop=self.loop, timeout=(aiohttp.ClientTimeout(total=10)))


def version():
    return os.getenv('APP_VERSION', 'unknown')


def main():
    log_format = os.getenv('LOG_FORMAT', '%(levelname)s [%(name)s] %(message)s')
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    logging.basicConfig(level='DEBUG', format=log_format, stream=sys.stdout)
    logging.debug(f'wormgas {version()}')
    logging.debug(f'Changing log level to {log_level}')
    logging.getLogger().setLevel(log_level)
    for logger in ('discord.client', 'discord.gateway', 'websockets.protocol'):
        logging.getLogger(logger).setLevel(logging.INFO)
    config_file = os.getenv('CONFIG_FILE', '/opt/wormgas/_config.json')
    intents = discord.Intents.default()
    intents.members = True
    bot = Wormgas(config_path=pathlib.Path(config_file).resolve(), command_prefix='!', pm_help=True, intents=intents)
    bot.load_extension('wormgas.cogs.chat')
    bot.load_extension('wormgas.cogs.config')
    bot.load_extension('wormgas.cogs.rainwave')
    bot.load_extension('wormgas.cogs.rand')
    bot.load_extension('wormgas.cogs.rps')
    bot.load_extension('wormgas.cogs.wiki')
    bot.load_extension('wormgas.cogs.wolframalpha')
    token = bot.config.get('discord:token')
    if token in (None, 'TOKEN'):
        bot.config.set('discord:token', 'TOKEN')
        logging.critical(f'Before you can run for the first time, edit {config_file} and set discord:token')
    else:
        bot.run(bot.config.get('discord:token'))
