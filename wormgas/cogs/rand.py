import discord
import logging
import random

from discord import app_commands
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

    @app_commands.command(name='8ball')
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        """Ask a question of the magic 8ball."""
        title = f':8ball: {random.choice(self.eight_ball_responses)}'
        description = f'{interaction.user.mention} asked, {question!r}'
        embed = discord.Embed(title=title, description=description, colour=discord.Colour.default())
        await interaction.response.send_message(embed=embed)

    @app_commands.command()
    async def flip(self, interaction: discord.Interaction):
        """Flip a coin."""
        title = f':coin: {random.choice(('Heads!', 'Tails!'))}'
        embed = discord.Embed(title=title, colour=discord.Colour.gold())
        await interaction.response.send_message(embed=embed)

    @staticmethod
    def parse_die_spec(die_spec):
        dice = 1
        sides = 6
        dice_spec, _, sides_spec = die_spec.partition('d')
        if dice_spec.isdigit():
            dice = min(int(dice_spec), 100)
        if sides_spec.isdigit():
            sides = min(int(sides_spec), 10000)
        return dice, sides

    @staticmethod
    def roll_response(dice, sides):
        if sides == 0:
            return 'Who ever heard of a 0-sided :game_die:?'
        rolls = [random.randint(1, sides) for _ in range(dice)]
        m = ':game_die:'
        if 1 < dice < 11:
            m = f'{m} [{", ".join(map(str, rolls))}] ='
        m = f'{m} {sum(rolls)}'
        return m

    @app_commands.command()
    @app_commands.describe(die_spec='<dice>d<sides>, default 1d6')
    async def roll(self, interaction: discord.Interaction, die_spec: str = '1d6'):
        """Roll some dice."""
        dice, sides = self.parse_die_spec(die_spec)
        title = self.roll_response(dice, sides)
        description = f'{interaction.user.mention} rolled {dice}d{sides}'
        embed = discord.Embed(title=title, description=description, colour=discord.Colour.red())
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(RandCog(bot))
