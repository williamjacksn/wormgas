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

        Use "!set [<key>] [<value>]" to display or change configuration settings.
        Leave off <value> to see the current setting.
        Leave off <key> and <value> to see a list of all currently set config keys.
        """

        self.bot.db.command_log_insert(ctx.author.id, ctx.invoked_with, ctx.message.content)

        if len(tokens) > 1:
            value = ' '.join(tokens[1:])
            key = tokens[0]
            self.bot.db.config_set(key, value)
            await ctx.author.send(f'{key} = {value}')
        elif len(tokens) > 0:
            key = tokens[0]
            value = self.bot.db.config_get(key)
            if value is None:
                await ctx.author.send(f'{key} is not set.')
            else:
                await ctx.author.send(f'{key} = {value}')
        else:
            config_keys = self.bot.db.config_list_keys()
            max_length = int(self.bot.db.config_get('config:max_length') or 10)
            while len(config_keys) > max_length:
                config_list = config_keys[:max_length]
                config_keys[0:max_length] = []
                await ctx.author.send(', '.join(config_list))
            await ctx.author.send(', '.join(config_keys))

    @cmds.command()
    @cmds.is_owner()
    async def unset(self, ctx: cmds.Context, key: str):
        """Remove a configuration setting."""

        self.bot.db.command_log_insert(ctx.author.id, ctx.invoked_with, ctx.message.content)

        self.bot.db.config_delete(key)
        await ctx.author.send(f'{key} has been unset.')


async def setup(bot: Wormgas):
    await bot.add_cog(ConfigCog(bot))
