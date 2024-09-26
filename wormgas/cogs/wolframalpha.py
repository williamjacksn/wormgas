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

    @app_commands.command()
    async def wa(self, interaction: discord.Interaction, query: str):
        """Send a query to Wolfram|Alpha"""

        api_key = self.bot.db.config_get('wolframalpha:key')
        if api_key is None:
            await interaction.response.send_message('Wolfram|Alpha API key not configured, cannot use /wa', ephemeral=True)
            return

        log.info(f'Looking up {query!r}')

        url = 'https://api.wolframalpha.com/v1/result'
        params = {
            'appid': api_key,
            'i': query,
        }
        data = urllib.parse.urlencode(params).encode()
        response = urllib.request.urlopen(url, data=data)
        if response.status == 200:
            title = response.read().decode()
        else:
            title = 'There was a problem.'

        description = f'{interaction.user.mention} asked {query!r}'
        embed = discord.Embed(title=title, description=description)
        await interaction.response.send_message(embed=embed)


async def setup(bot: Wormgas):
    await bot.add_cog(WolframAlphaCog(bot))
