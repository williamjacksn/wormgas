import logging
import textwrap

import discord.ext
import wikipedia

import wormgas.wormgas

log = logging.getLogger(__name__)


class WikiCog(discord.ext.commands.Cog, name="Wikipedia"):
    def __init__(self, bot: wormgas.wormgas.Wormgas) -> None:
        self.bot = bot

    @discord.ext.commands.command()
    async def wiki(self, ctx: discord.ext.commands.Context, *, search_terms: str) -> None:
        """Look up information on Wikipedia."""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        try:
            page = wikipedia.page(search_terms, auto_suggest=False)
        except wikipedia.exceptions.DisambiguationError as err:
            await ctx.author.send("Your query returned a disambiguation page.")
            if len(err.options) < 6:
                opts_list = "; ".join(err.options)
                await ctx.author.send(f"Options: {opts_list}")
            else:
                opts_list = "; ".join(err.options[:6])
                await ctx.author.send(f"Some options: {opts_list} ...")
            return
        except wikipedia.exceptions.PageError as err:
            await ctx.author.send(str(err))
            return

        summary = textwrap.shorten(page.summary, width=300, placeholder=" ...")
        await ctx.send(f"{page.title} // {summary} [ {page.url} ]")


async def setup(bot: wormgas.wormgas.Wormgas) -> None:
    await bot.add_cog(WikiCog(bot))
