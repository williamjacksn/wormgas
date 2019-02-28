import discord.ext.commands as cmds
import logging
import random

log = logging.getLogger(__name__)


class RandCog(cmds.Cog):
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

    def __init__(self, bot: cmds.Bot):
        self.bot = bot

    def eight_ball_response(self):
        return ':8ball: ' + random.choice(self.eight_ball_responses)

    @cmds.command(name='8ball', aliases=['\U0001F3B1'])
    @cmds.cooldown(1, 180, cmds.BucketType.channel)
    async def eight_ball(self, ctx: cmds.Context):
        """Ask a question of the magic 8ball."""
        await ctx.send(self.eight_ball_response())

    @staticmethod
    def flip_response():
        return random.choice(('Heads!', 'Tails!'))

    @cmds.command()
    @cmds.cooldown(1, 60, cmds.BucketType.channel)
    async def flip(self, ctx: cmds.Context):
        """Flip a coin."""
        await ctx.send(self.flip_response())

    @staticmethod
    def parse_die_spec(die_spec):
        dice = 1
        sides = 6
        dice_spec, _, sides_spec = die_spec.partition('d')
        if dice_spec.isdigit():
            dice = min(int(dice_spec), 100)
        if sides_spec.isdigit():
            sides = min(int(sides_spec), 100)
        return dice, sides

    @staticmethod
    def roll_response(dice, sides):
        if sides == 0:
            return 'Who ever heard of a 0-sided :game_die:?'
        rolls = [random.randint(1, sides) for _ in range(dice)]
        m = f'{dice}d{sides}:'
        if 1 < dice < 11:
            m = f'{m} [{", ".join(map(str, rolls))}] ='
        m = f'{m} {sum(rolls)}'
        return m

    @cmds.command(name='roll', aliases=['\U0001F3B2'])
    @cmds.cooldown(1, 60, cmds.BucketType.channel)
    async def roll(self, ctx: cmds.Context, die_spec: str = '1d6'):
        """Roll a ^-sided die # times."""
        dice, sides = self.parse_die_spec(die_spec)
        await ctx.send(self.roll_response(dice, sides))

    @eight_ball.error
    @flip.error
    @roll.error
    async def command_on_cooldown(self, ctx: cmds.Context, err: cmds.CommandOnCooldown):
        if isinstance(err, cmds.CommandOnCooldown):
            if not ctx.guild:
                await ctx.reinvoke()
                return
            cd_msg = f'{ctx.command.name} is on cooldown. Try again in {int(err.retry_after)} seconds.'
            await ctx.author.send(cd_msg)


def setup(bot: cmds.Bot):
    bot.add_cog(RandCog(bot))
