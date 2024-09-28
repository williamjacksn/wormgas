import logging
import random

from discord import app_commands, Colour, Embed, Interaction, User
from discord.ext import commands
from wormgas.wormgas import Wormgas

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

    def __init__(self, bot: Wormgas):
        self.bot = bot

    async def _eight_ball(self, user: User, question: str) -> Embed:
        title = f':8ball: {random.choice(self.eight_ball_responses)}'
        description = f'{user.mention} asked, {question!r}'
        return Embed(title=title, description=description, colour=Colour.default())

    @app_commands.command(name='8ball')
    async def slash_eight_ball(self, interaction: Interaction, question: str):
        """Ask a question of the magic 8ball"""

        self.bot.db.command_log_insert(interaction.user.id, interaction.command.name, str(interaction.data))

        embed = await self._eight_ball(interaction.user, question)
        await interaction.response.send_message(embed=embed)

    @commands.command(name='8ball')
    async def bang_eight_ball(self, ctx: commands.Context, *, question: str):
        """Ask a question of the magic 8ball"""

        self.bot.db.command_log_insert(ctx.author.id, ctx.invoked_with, ctx.message.content)

        async with ctx.typing():
            embed = await self._eight_ball(ctx.author, question)
            await ctx.send(embed=embed)

    @staticmethod
    async def _flip() -> Embed:
        title = f':coin: {random.choice(('Heads!', 'Tails!'))}'
        return Embed(title=title, colour=Colour.gold())

    @app_commands.command(name='flip')
    async def slash_flip(self, interaction: Interaction):
        """Flip a coin"""

        self.bot.db.command_log_insert(interaction.user.id, interaction.command.name, str(interaction.data))

        embed = await self._flip()
        await interaction.response.send_message(embed=embed)

    @commands.command(name='flip')
    async def bang_flip(self, ctx: commands.Context):
        """Flip a coin"""

        self.bot.db.command_log_insert(ctx.author.id, ctx.invoked_with, ctx.message.content)

        async with ctx.typing():
            embed = await self._flip()
            await ctx.send(embed=embed)

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

        self.bot.db.command_log_insert(interaction.user.id, interaction.command.name, str(interaction.data))

        dice, sides = await self._parse_die_spec(die_spec)
        title = await self._roll(dice, sides)
        description = f'{interaction.user.mention} rolled {dice}d{sides}'
        embed = Embed(title=title, description=description, colour=Colour.red())
        await interaction.response.send_message(embed=embed)

    @commands.command(name='roll')
    async def bang_roll(self, ctx: commands.Context, die_spec: str = '1d6'):
        """Roll some dice"""

        self.bot.db.command_log_insert(ctx.author.id, ctx.invoked_with, ctx.message.content)

        async with ctx.typing():
            dice, sides = await self._parse_die_spec(die_spec)
            await ctx.send(await self._roll(dice, sides))


async def setup(bot: Wormgas):
    await bot.add_cog(RandCog(bot))
