import discord.ext.commands as cmds
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree

from wormgas.wormgas import Wormgas

log = logging.getLogger(__name__)


class WolframAlphaCog(cmds.Cog):
    def __init__(self, bot: Wormgas):
        self.bot = bot

    @cmds.command()
    async def wa(self, ctx: cmds.Context, *, query: str):
        """Send a query to Wolfram Alpha."""

        log.info(f'Looking up {query!r}')
        result = await self._aux_wa(query)
        for line in result:
            await ctx.send(line)

    async def _aux_wa(self, query):
        api_key = self.bot.config.get('wolframalpha:key')
        if api_key is None:
            return ['Wolfram Alpha API key not configured, cannot use !wa.']
        try:
            url = 'http://api.wolframalpha.com/v2/query'
            params = {
                'appid': api_key,
                'input': query,
                'format': 'plaintext'
            }
            data = urllib.parse.urlencode(params).encode()
            response = urllib.request.urlopen(url, data=data)
            if response.status == 200:
                body = response.read().decode()
            else:
                raise RuntimeError
            root = xml.etree.ElementTree.fromstring(body)
            if root.get('success') != 'true':
                return ['Wolfram Alpha found no answer.']
            plaintext = root.find('./pod[@primary="true"]/subpod/plaintext')
            if plaintext is None:
                for pod in root.findall('./pod'):
                    if pod.get('title') != 'Input interpretation':
                        plaintext = pod.find('./subpod/plaintext')
                        if plaintext is not None:
                            break
            if plaintext is None:
                return ['Error: could not find response.']
            if plaintext.text is None:
                return ['Error: empty response.']
            return plaintext.text.splitlines()
        except xml.etree.ElementTree.ParseError:
            return ['Error: could not parse response.']


async def setup(bot: Wormgas):
    await bot.add_cog(WolframAlphaCog(bot))
