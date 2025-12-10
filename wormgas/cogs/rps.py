import logging
import secrets

import discord.ext

import wormgas.wormgas

log = logging.getLogger(__name__)


class RpsCog(discord.ext.commands.Cog, name="Rock/Paper/Scissors"):
    def __init__(self, bot: wormgas.wormgas.Wormgas) -> None:
        self.bot = bot
        self.canonical_actions: dict[str, str] = {
            "rock": "rock",
            "paper": "paper",
            "scissors": "scissors",
            "\u2702": "scissors",
            "\ufe0f": "scissors",
        }

    async def get_rps_record(self, player: discord.Member) -> str:
        player_id = str(player.id)
        player_dict = self.bot.db.rps_get(player_id)
        if player_id is None:
            return f"{player.display_name} does not play. :("

        w = player_dict.get("wins", 0)
        d = player_dict.get("draws", 0)
        _l = player_dict.get("losses", 0)
        t = w + d + _l
        plural = "s"
        if t == 1:
            plural = ""
        return (
            f"RPS record for {player.display_name} "
            f"({t} game{plural}) is {w}-{d}-{_l} (w-d-l)."
        )

    async def get_rps_stats(self, player: discord.Member) -> str:
        player_id = str(player.id)
        player_dict = self.bot.db.rps_get(player_id)
        if player_id is None:
            return f"{player.display_name} does not play. :("

        r = player_dict.get("rock", 0)
        p = player_dict.get("paper", 0)
        s = player_dict.get("scissors", 0)
        t = r + p + s
        if t > 0:
            r_rate = r / float(t) * 100
            p_rate = p / float(t) * 100
            s_rate = s / float(t) * 100
            m = (
                f"{player.display_name} challenges with rock/paper/scissors "
                f"at these rates: "
            )
            m = f"{m}{r_rate:3.1f}/{p_rate:3.1f}/{s_rate:3.1f}%."
        else:
            m = f"{player.display_name} does not play. :("
        return m

    async def play_game(self, challenger: discord.User, action: str) -> str:
        challenger_id = str(challenger.id)
        action = self.canonical_actions[action]
        action_map = ["rock", "paper", "scissors"]
        challenge = action_map.index(action)
        response = secrets.randbelow(3)
        player_dict = self.bot.db.rps_get(challenger_id)
        global_dict = self.bot.db.rps_get("!global")
        player_dict[action] = player_dict.get(action, 0) + 1
        global_dict[action] = global_dict.get(action, 0) + 1

        m = (
            f"You challenge with **{action}**. "
            f"I counter with **{action_map[response]}**."
        )

        if challenge == (response + 1) % 3:
            player_dict["wins"] = player_dict.get("wins", 0) + 1
            global_dict["wins"] = global_dict.get("wins", 0) + 1
            m = m + " You win!"
        elif challenge == response:
            player_dict["draws"] = player_dict.get("draws", 0) + 1
            global_dict["draws"] = global_dict.get("draws", 0) + 1
            m = m + " We draw!"
        elif challenge == (response + 2) % 3:
            player_dict["losses"] = player_dict.get("losses", 0) + 1
            global_dict["losses"] = global_dict.get("losses", 0) + 1
            m = m + " You lose!"

        self.bot.db.rps_set(player_dict)
        self.bot.db.rps_set(global_dict)

        w = player_dict.get("wins", 0)
        d = player_dict.get("draws", 0)
        _l = player_dict.get("losses", 0)
        pw = int(float(w) / float(w + d + _l) * 100)
        pd = int(float(d) / float(w + d + _l) * 100)
        pl = int(float(_l) / float(w + d + _l) * 100)
        return m + f" Your current record is {w}-{d}-{_l} or {pw}%-{pd}%-{pl}% (w-d-l)."

    @discord.ext.commands.command(name="rock", aliases=["paper", "scissors", "\u2702"])
    async def rock(self, ctx: discord.ext.commands.Context) -> None:
        """Play a game of rock-paper-scissors."""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        await ctx.send(await self.play_game(ctx.author, ctx.invoked_with))

    @discord.ext.commands.group(name="rps")
    async def rps(self, ctx: discord.ext.commands.Context) -> None:
        """Administrative commands for rock-paper-scissors."""

    @rps.command()
    async def record(
        self, ctx: discord.ext.commands.Context, player: discord.Member = None
    ) -> None:
        """Request the record for a rock-paper-scissors player."""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        if player is None:
            player = ctx.author
        await ctx.send(await self.get_rps_record(player))

    @rps.command()
    async def stats(
        self, ctx: discord.ext.commands.Context, player: discord.Member = None
    ) -> None:
        """Request statistics for a rock-paper-scissors player."""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        if player is None:
            player = ctx.author
        await ctx.send(await self.get_rps_stats(player))

    @rps.command()
    async def reset(
        self, ctx: discord.ext.commands.Context, reset_code: str | None = None
    ) -> None:
        """Reset your record and delete your game history."""

        self.bot.db.command_log_insert(
            ctx.author.id, ctx.command.qualified_name, ctx.message.content
        )

        player_dict = self.bot.db.rps_get(str(ctx.author.id))
        if reset_code and reset_code == player_dict.get("reset_code"):
            self.bot.db.rps_delete(str(ctx.author.id))
            await ctx.author.send(
                "I reset your RPS record and deleted your game history."
            )
        else:
            reset_code = f"{secrets.randbelow(1000000):06d}"
            player_dict["reset_code"] = reset_code
            self.bot.db.rps_set(player_dict)
            await ctx.author.send(
                f"Use `!rps reset {reset_code}` to reset your RPS record "
                f"and delete your history."
            )


async def setup(bot: wormgas.wormgas.Wormgas) -> None:
    await bot.add_cog(RpsCog(bot))
