import logging

import discord.ext

import wormgas.wormgas

log = logging.getLogger(__name__)


class ConfigCog(discord.ext.commands.Cog, name="Bot configuration"):
    def __init__(self, bot: wormgas.wormgas.Wormgas) -> None:
        self.bot = bot

    @discord.ext.commands.command(name="command-stats")
    async def command_stats(self, ctx: discord.ext.commands.Context) -> None:
        """Show simple statistics about how often commands are used"""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        results = self.bot.db.command_log_list()
        embed = discord.Embed(title="Command stats")
        commands = "\n".join([r["command"] for r in results])
        embed.add_field(name="Command", value=commands, inline=True)
        invocations = "\n".join([str(r["usage_count"]) for r in results])
        embed.add_field(name="Invocations", value=invocations, inline=True)
        await ctx.send(embed=embed)

    @discord.ext.commands.command(name="set")
    @discord.ext.commands.is_owner()
    async def _set(self, ctx: discord.ext.commands.Context, *tokens: list[str]) -> None:
        """Display or change configuration settings.

        Use "!set [<key>] [<value>]" to display or change configuration settings.
        Leave off <value> to see the current setting.
        Leave off <key> and <value> to see a list of all currently set config keys.
        """

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        if len(tokens) > 1:
            value = " ".join(tokens[1:])
            key = tokens[0]
            self.bot.db.config_set(key, value)
            await ctx.author.send(f"{key} = {value}")
        elif len(tokens) > 0:
            key = tokens[0]
            value = self.bot.db.config_get(key)
            if value is None:
                await ctx.author.send(f"{key} is not set.")
            else:
                await ctx.author.send(f"{key} = {value}")
        else:
            config_keys = self.bot.db.config_list_keys()
            max_length = int(self.bot.db.config_get("config:max_length") or 10)
            while len(config_keys) > max_length:
                config_list = config_keys[:max_length]
                config_keys[0:max_length] = []
                await ctx.author.send(", ".join(config_list))
            await ctx.author.send(", ".join(config_keys))

    @discord.ext.commands.command()
    @discord.ext.commands.is_owner()
    async def unset(self, ctx: discord.ext.commands.Context, key: str) -> None:
        """Remove a configuration setting."""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        self.bot.db.config_delete(key)
        await ctx.author.send(f"{key} has been unset.")


async def setup(bot: wormgas.wormgas.Wormgas) -> None:
    await bot.add_cog(ConfigCog(bot))
