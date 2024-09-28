import discord.ext.commands
import logging
import wormgas.wormgas

log = logging.getLogger(__name__)


class ConfigCog(discord.ext.commands.Cog):
    def __init__(self, bot: wormgas.wormgas.Wormgas):
        self.bot = bot

    @discord.app_commands.command(name='command-stats')
    async def slash_command_stats(self, interaction: discord.Interaction):
        """Show simple statistics about how often commands are used"""

        self.bot.db.command_log_insert(interaction.user.id, interaction.command.name, str(interaction.data))

        results = self.bot.db.command_log_list()
        message = ', '.join([f'{r['command']} ({r['usage_count']})' for r in results])
        # noinspection PyUnresolvedReferences
        await interaction.response.send_message(message)

    @discord.ext.commands.command(name='set')
    @discord.ext.commands.is_owner()
    async def _set(self, ctx: discord.ext.commands.Context, *tokens):
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

    @discord.ext.commands.command()
    @discord.ext.commands.is_owner()
    async def unset(self, ctx: discord.ext.commands.Context, key: str):
        """Remove a configuration setting."""

        self.bot.db.command_log_insert(ctx.author.id, ctx.invoked_with, ctx.message.content)

        self.bot.db.config_delete(key)
        await ctx.author.send(f'{key} has been unset.')


async def setup(bot: wormgas.wormgas.Wormgas):
    await bot.add_cog(ConfigCog(bot))
