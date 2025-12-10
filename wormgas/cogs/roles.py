import discord.ext

import wormgas.wormgas


class RolesCog(discord.ext.commands.Cog):
    def __init__(self, bot: wormgas.wormgas.Wormgas) -> None:
        self.bot = bot

    @discord.ext.commands.Cog.listener(name="on_raw_reaction_add")
    @discord.ext.commands.Cog.listener(name="on_raw_reaction_remove")
    async def _handle_reaction_change(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        notification_signup_message_id = int(
            self.bot.db.config_get("discord:messages:notification-signup")
        )
        if payload.message_id == notification_signup_message_id:
            config_role_id = self.bot.db.config_get(
                f"discord:roles:notify:{payload.emoji}"
            )
            if config_role_id:
                target_role_id = int(config_role_id)
                guild = self.bot.get_guild(payload.guild_id)
                member = guild.get_member(payload.user_id)
                target_role = guild.get_role(target_role_id)
                if payload.event_type == "REACTION_ADD":
                    await member.add_roles(target_role)
                    await member.send(f"I added you to the {target_role} role.")
                elif payload.event_type == "REACTION_REMOVE":
                    await member.remove_roles(target_role)
                    await member.send(f"I removed you from the {target_role} role.")


async def setup(bot: wormgas.wormgas.Wormgas) -> None:
    await bot.add_cog(RolesCog(bot))
