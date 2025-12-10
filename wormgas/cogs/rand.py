import logging
import secrets

import discord.ext

import wormgas.wormgas

log = logging.getLogger(__name__)


class RandCog(discord.ext.commands.Cog, name="Randomness"):
    def __init__(self, bot: wormgas.wormgas.Wormgas) -> None:
        self.bot = bot
        self.eight_ball_responses: list[str] = [
            "As I see it, yes.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            "Don't count on it.",
            "It is certain.",
            "It is decidedly so.",
            "Most likely.",
            "My reply is no.",
            "My sources say no.",
            "Outlook good.",
            "Outlook not so good.",
            "Reply hazy, try again.",
            "Signs point to yes.",
            "Very doubtful.",
            "Without a doubt.",
            "Yes.",
            "Yes - definitely.",
            "You may rely on it.",
        ]

    async def _eight_ball(
        self, user: discord.User, question: str | None = None
    ) -> discord.Embed:
        title = f":8ball: {secrets.choice(self.eight_ball_responses)}"
        if question is None:
            description = f"{user.mention} did not ask a question"
        else:
            description = f"{user.mention} asked, {question!r}"
        return discord.Embed(
            title=title, description=description, colour=discord.Colour.default()
        )

    @discord.ext.commands.command(name="8ball")
    async def bang_eight_ball(
        self, ctx: discord.ext.commands.Context, *, question: str | None = None
    ) -> None:
        """Ask a question of the magic 8ball"""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        async with ctx.typing():
            embed = await self._eight_ball(ctx.author, question)
            await ctx.send(embed=embed)

    @staticmethod
    async def _flip() -> discord.Embed:
        result: str = secrets.choice(("Heads!", "Tails!"))
        title = f":coin: {result}"
        return discord.Embed(title=title, colour=discord.Colour.gold())

    @discord.ext.commands.command(name="flip")
    async def bang_flip(self, ctx: discord.ext.commands.Context) -> None:
        """Flip a coin"""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        async with ctx.typing():
            embed = await self._flip()
            await ctx.send(embed=embed)

    @staticmethod
    async def _parse_die_spec(die_spec: str) -> tuple[int, int]:
        dice = 1
        sides = 6
        dice_spec, _, sides_spec = die_spec.partition("d")
        if dice_spec.isdigit():
            dice = min(int(dice_spec), 100)
        if sides_spec.isdigit():
            sides = min(int(sides_spec), 10000)
        return dice, sides

    @staticmethod
    async def _roll(dice: int, sides: int) -> str:
        if sides == 0:
            return "Who ever heard of a 0-sided :game_die:?"
        rolls = [secrets.randbelow(sides - 1) + 1 for _ in range(dice)]
        m = ":game_die:"
        if 1 < dice < 11:
            m = f"{m} [{', '.join(map(str, rolls))}] ="
        m = f"{m} {sum(rolls)}"
        return m

    @discord.ext.commands.command(name="roll")
    async def bang_roll(
        self, ctx: discord.ext.commands.Context, die_spec: str = "1d6"
    ) -> None:
        """Roll some dice"""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        async with ctx.typing():
            dice, sides = await self._parse_die_spec(die_spec)
            await ctx.send(await self._roll(dice, sides))


async def setup(bot: wormgas.wormgas.Wormgas) -> None:
    await bot.add_cog(RandCog(bot))
