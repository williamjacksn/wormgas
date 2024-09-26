import discord
import logging
import urllib.parse
import urllib.request

from discord import app_commands
from discord.ext import commands
from wormgas.wormgas import Wormgas

log = logging.getLogger(__name__)


class WolframAlphaCog(commands.Cog):
    def __init__(self, bot: Wormgas):
        self.bot = bot

    async def _wa(self, query: str):
        api_key = self.bot.db.config_get('wolframalpha:key')
        if api_key is None:
            return 'Wolfram|Alpha API key not configured, cannot use /wa'

        log.info(f'Looking up {query!r}')

        url = 'https://api.wolframalpha.com/v1/result'
        params = {
            'appid': api_key,
            'i': query,
        }
        data = urllib.parse.urlencode(params).encode()
        response = urllib.request.urlopen(url, data=data)
        if response.status == 200:
            return response.read().decode()
        else:
            return 'There was a problem.'

    @commands.command(name='wa')
    async def bang_wa(self, ctx: commands.Context, *, query: str):
        """Send a query to Wolfram|Alpha"""
        async with ctx.typing():
            await ctx.send(await self._wa(query))

    @app_commands.command(name='wa')
    async def slash_wa(self, interaction: discord.Interaction, query: str):
        """Send a query to Wolfram|Alpha"""

        title = await self._wa(query)
        description = f'{interaction.user.mention} asked {query!r}'
        embed = discord.Embed(title=title, description=description)
        await interaction.response.send_message(embed=embed)


async def setup(bot: Wormgas):
    await bot.add_cog(WolframAlphaCog(bot))
