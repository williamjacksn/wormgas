import logging

import discord.ext

import wormgas.wormgas

log = logging.getLogger(__name__)


class WolframAlphaCog(discord.ext.commands.Cog, name="Wolfram|Alpha"):
    def __init__(self, bot: wormgas.wormgas.Wormgas) -> None:
        self.bot = bot

    async def _wa(self, query: str) -> str:
        api_key = self.bot.db.config_get("wolframalpha:key")
        if api_key is None:
            return "Wolfram|Alpha API key not configured, cannot use /wa"

        log.info(f"Looking up {query!r}")

        url = "https://api.wolframalpha.com/v1/result"
        params = {
            "appid": api_key,
            "i": query,
        }
        async with self.bot.session.get(url, params=params) as response:
            content = await response.text()
            log.debug(f"{response.status} {content}")
            if response.status in (200, 501):
                return await response.text()
            else:
                return "There was a problem."

    @discord.ext.commands.command(name="wa")
    async def bang_wa(self, ctx: discord.ext.commands.Context, *, query: str) -> None:
        """Send a query to Wolfram|Alpha"""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        async with ctx.typing():
            await ctx.send(await self._wa(query))


async def setup(bot: wormgas.wormgas.Wormgas) -> None:
    await bot.add_cog(WolframAlphaCog(bot))
