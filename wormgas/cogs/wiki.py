import discord.ext.commands as cmds
import logging
import textwrap
import wikipedia

log = logging.getLogger(__name__)


class WikiCog(cmds.Cog):
    def __init__(self, bot: cmds.Bot):
        self.bot = bot

    @cmds.command()
    async def wiki(self, ctx: cmds.Context, *, search_terms: str):
        """Look up information on Wikipedia."""

        try:
            page = wikipedia.page(search_terms)
        except wikipedia.exceptions.DisambiguationError as err:
            await ctx.author.send('Your query returned a disambiguation page.')
            if len(err.options) < 6:
                opts_list = '; '.join(err.options)
                await ctx.author.send(f'Options: {opts_list}')
            else:
                opts_list = '; '.join(err.options[:6])
                await ctx.author.send(f'Some options: {opts_list} ...')
            return
        except wikipedia.exceptions.PageError as err:
            await ctx.author.send(str(err))
            return

        summary = textwrap.shorten(page.summary, width=300, placeholder=' ...')
        await ctx.send(f'{page.title} // {summary} [ {page.url} ]')


def setup(bot: cmds.Bot):
    bot.add_cog(WikiCog(bot))
