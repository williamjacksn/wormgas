import logging
import random

from discord import app_commands, Colour, Embed, Interaction
from discord.ext import commands

log = logging.getLogger(__name__)


class RandCog(commands.Cog):
    eight_ball_responses = [
        'As I see it, yes.',
        'Ask again later.',
        'Better not tell you now.',
        'Cannot predict now.',
        'Concentrate and ask again.',
        'Don\'t count on it.',
        'It is certain.',
        'It is decidedly so.',
        'Most likely.',
        'My reply is no.',
        'My sources say no.',
        'Outlook good.',
        'Outlook not so good.',
        'Reply hazy, try again.',
        'Signs point to yes.',
        'Very doubtful.',
        'Without a doubt.',
        'Yes.',
        'Yes - definitely.',
        'You may rely on it.'
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _eight_ball(self):
        return f':8ball: {random.choice(self.eight_ball_responses)}'

    @app_commands.command(name='8ball')
    async def slash_eight_ball(self, interaction: Interaction, question: str):
        """Ask a question of the magic 8ball"""
        title = await self._eight_ball()
        description = f'{interaction.user.mention} asked, {question!r}'
        embed = Embed(title=title, description=description, colour=Colour.default())
        await interaction.response.send_message(embed=embed)

    @commands.command(name='8ball')
    async def bang_eight_ball(self, ctx: commands.Context):
        async with ctx.typing():
            await ctx.send(await self._eight_ball())

    @staticmethod
    async def _flip():
        return f':coin: {random.choice(('Heads!', 'Tails!'))}'

    @app_commands.command(name='flip')
    async def slash_flip(self, interaction: Interaction):
        """Flip a coin"""
        title = await self._flip()
        embed = Embed(title=title, colour=Colour.gold())
        await interaction.response.send_message(embed=embed)

    @commands.command(name='flip')
    async def bang_flip(self, ctx: commands.Context):
        """Flip a coin"""
        async with ctx.typing():
            await ctx.send(await self._flip())

    @staticmethod
    async def _parse_die_spec(die_spec):
        dice = 1
        sides = 6
        dice_spec, _, sides_spec = die_spec.partition('d')
        if dice_spec.isdigit():
            dice = min(int(dice_spec), 100)
        if sides_spec.isdigit():
            sides = min(int(sides_spec), 10000)
        return dice, sides

    @staticmethod
    async def _roll(dice, sides):
        if sides == 0:
            return 'Who ever heard of a 0-sided :game_die:?'
        rolls = [random.randint(1, sides) for _ in range(dice)]
        m = ':game_die:'
        if 1 < dice < 11:
            m = f'{m} [{", ".join(map(str, rolls))}] ='
        m = f'{m} {sum(rolls)}'
        return m

    @app_commands.command(name='roll')
    @app_commands.describe(die_spec='<dice>d<sides>, default 1d6')
    async def slash_roll(self, interaction: Interaction, die_spec: str = '1d6'):
        """Roll some dice"""
        dice, sides = await self._parse_die_spec(die_spec)
        title = await self._roll(dice, sides)
        description = f'{interaction.user.mention} rolled {dice}d{sides}'
        embed = Embed(title=title, description=description, colour=Colour.red())
        await interaction.response.send_message(embed=embed)

    @commands.command(name='roll')
    async def bang_roll(self, ctx: commands.Context, die_spec: str = '1d6'):
        """Roll some dice"""
        async with ctx.typing():
            dice, sides = await self._parse_die_spec(die_spec)
            await ctx.send(await self._roll(dice, sides))


async def setup(bot: commands.Bot):
    await bot.add_cog(RandCog(bot))
