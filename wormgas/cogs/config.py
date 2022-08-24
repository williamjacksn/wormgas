import discord.ext.commands as cmds
import logging

from wormgas.wormgas import Wormgas

log = logging.getLogger(__name__)


class ConfigCog(cmds.Cog):
    def __init__(self, bot: Wormgas):
        self.bot = bot

    @cmds.command(name='set')
    @cmds.is_owner()
    async def _set(self, ctx: cmds.Context, *tokens):
        """Display or change configuration settings.

        Use "!set [<id>] [<value>]" to display or change configuration settings.
        Leave off <value> to see the current setting.
        Leave off <id> and <value> to see a list of all available config ids.
        """

        if len(tokens) > 1:
            value = ' '.join(tokens[1:])
            key = tokens[0]
            self.bot.config[key] = value
            await ctx.author.send(f'{key} = {value}')
        elif len(tokens) > 0:
            key = tokens[0]
            value = self.bot.config.get(key)
            if value is None:
                await ctx.author.send(f'{key} is not set.')
            else:
                await ctx.author.send(f'{key} = {value}')
        else:
            config_ids = sorted(self.bot.config.keys())
            max_length = int(self.bot.config.get('config:max_length', 10))
            while len(config_ids) > max_length:
                config_list = config_ids[:max_length]
                config_ids[0:max_length] = []
                await ctx.author.send(', '.join(config_list))
            await ctx.author.send(', '.join(config_ids))

    @cmds.command()
    @cmds.is_owner()
    async def unset(self, ctx: cmds.Context, key: str):
        """Remove a configuration setting."""

        self.bot.config.remove(key)
        await ctx.author.send(f'{key} has been unset.')


async def setup(bot: Wormgas):
    await bot.add_cog(ConfigCog(bot))
