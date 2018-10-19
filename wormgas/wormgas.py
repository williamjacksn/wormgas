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


def version():
    """Read version from Dockerfile"""
    dockerfile = pathlib.Path(__file__).resolve().parent.parent / 'Dockerfile'
    with open(dockerfile) as f:
        for line in f:
            if 'org.label-schema.version' in line:
                return line.strip().split('=', maxsplit=1)[1]
    return 'unknown'


def main():
    log_format = os.getenv('LOG_FORMAT', '%(levelname)s [%(name)s] %(message)s')
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    logging.basicConfig(level='DEBUG', format=log_format, stream=sys.stdout)
    logging.debug(f'wormgas {version()}')
    logging.debug(f'Changing log level to {log_level}')
    logging.getLogger().setLevel(log_level)
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
