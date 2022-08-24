import asyncio
import discord
import discord.ext.commands as cmds
import logging
import re
import random
import time

from .cobe import brain
from wormgas.util import to_bool
from wormgas.wormgas import Wormgas

log = logging.getLogger(__name__)


class ChatCog(cmds.Cog):
    quotes = [
        'Attack the evil that is within yourself, rather than attacking the evil that is in others.',
        'Before you embark on a journey of revenge, dig two graves.',
        'Better a diamond with a flaw than a pebble without.',
        'Everything has beauty, but not everyone sees it.',
        'He who knows all the answers has not been asked all the questions.',
        'He who learns but does not think, is lost! He who thinks but does not learn is in great danger.',
        'I hear and I forget. I see and I remember. I do and I understand.',
        'If what one has to say is not better than silence, then one should keep silent.',
        'If you make a mistake and do not correct it, this is called a mistake.',
        'Ignorance is the night of the mind but a night without moon and star.',
        'Music produces a kind of pleasure which human nature cannot do without.',
        'Only the wisest and stupidest of men never change.',
        'Our greatest glory is not in never falling, but in rising every time we fall.',
        'Respect yourself and others will respect you.',
        'Silence is a true friend who never betrays.',
        'The hardest thing of all is to find a black cat in a dark room, especially if there is no cat.',
        'The man who asks a question is a fool for a minute, the man who does not ask is a fool for life.',
        'The superior man is modest in his speech, but exceeds in his actions.',
        'To be wronged is nothing, unless you continue to remember it.',
        'To see what is right and not to do it, is want of courage or of principle.',
        'What you know, you know, what you do not know, you do not know. This is true wisdom.'
    ]

    def __init__(self, bot: Wormgas):
        self.bot = bot
        brain_file = bot.config.path.with_name('_brain.sqlite')
        self.brain = brain.Brain(str(brain_file))
        self.revive_task = self.bot.loop.create_task(self.revive_chat())

    @cmds.command()
    @cmds.has_permissions(manage_channels=True)
    async def revive(self, ctx: cmds.Context, on_off: to_bool = None):
        """Turn chat revive on or off."""
        if isinstance(ctx.channel, discord.TextChannel):
            revive_list = self.bot.config.get('chat:revive_channels', [])
            if ctx.channel.id in revive_list:
                revive_list.remove(ctx.channel.id)
            if on_off:
                revive_list.append(ctx.channel.id)
                await ctx.author.send(f'Chat revive is ON for {ctx.channel.mention}')
            else:
                await ctx.author.send(f'Chat revive is OFF for {ctx.channel.mention}')
            self.bot.config['chat:revive_channels'] = revive_list

    async def revive_chat(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = int(time.time())
            for channel_id in self.bot.config.get('chat:revive_channels', []):
                channel = self.bot.get_channel(channel_id)
                last = int(self.bot.config.get(f'chat:last_time_public_message:{channel.id}', 0))
                wait = int(self.bot.config.get('chat:wait_revive', 3600))
                if last < now - wait:
                    log.info(f'Reviving chat in {channel.id} (#{channel.name})')
                    last_message = self.bot.config.get('chat:last_message', '')
                    response = await self.reply(last_message, learn=False)
                    await channel.send(response)
                    self.bot.config[f'chat:last_time_respond:{channel.id}'] = now
                    self.bot.config['chat:last_time_public_message:{channel.id}'] = now
                else:
                    remaining = last + wait - now
                    log.info(f'{channel.id} (#{channel.name}): will revive chat in {remaining} seconds')
            await asyncio.sleep(120)

    @cmds.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages from myself.
        if message.author == self.bot.user:
            return

        # Ignore messages that contain commands.
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            log.info('Ignoring message because it contains a command.')
            return

        # Do not learn from messages from ignored users.
        learn = True
        if message.author.id in self.bot.config.get('chat:ignore_users', []):
            log.info(f'{message.author.display_name} is in the chat:ignore_users list')
            learn = False

        # Clean up message and generate response.
        text = message.clean_content
        text = text.replace(f'@{self.bot.user.display_name}', '')
        log.info(f'Generating reply for {text!r}')
        response = await self.reply(text, learn=learn)

        # Always respond to direct messages, and record the time for public messages.
        now = int(time.time())
        if not message.guild:
            await message.author.send(response)
            return
        else:
            self.bot.config[f'chat:last_time_public_message:{message.channel.id}'] = now

        # If I was not mentioned, do not reply.
        if self.bot.user.id not in [u.id for u in message.mentions]:
            return

        last = int(self.bot.config.get(f'chat:last_time_respond:{message.channel.id}', 0))
        wait = int(self.bot.config.get('chat:wait_respond', 0))
        if last < now - wait:
            await message.channel.send(f'{message.author.mention}: {response}')
            self.bot.config[f'chat:last_time_respond:{message.channel.id}'] = now
        else:
            await message.author.send(response)
            remaining = last + wait - now
            m = f'I am cooling down. I cannot respond in {message.channel.mention} for another {remaining} seconds.'
            await message.author.send(m)

    async def reply(self, text, learn=True):
        ignore = self.bot.config.get('chat:ignore')
        if ignore is not None and re.search(ignore, text, re.IGNORECASE):
            log.info(f'Ignoring {text!r}')
            return random.choice(self.quotes)
        self.bot.config['chat:last_message'] = text
        to_brain = text
        if learn:
            log.info(f'Learning {to_brain!r}')
            self.brain.learn(to_brain)
        return self.brain.reply(to_brain)


async def setup(bot: Wormgas):
    await bot.add_cog(ChatCog(bot))
