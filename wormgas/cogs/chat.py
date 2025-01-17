import discord.ext
import logging
import os
import pathlib
import re
import random
import time
import wormgas.wormgas
import wormgas.cogs.cobe.brain

log = logging.getLogger(__name__)


class ChatCog(discord.ext.commands.Cog):
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

    def __init__(self, bot: wormgas.wormgas.Wormgas):
        self.bot = bot
        brain_file = pathlib.Path(os.getenv('BRAIN_FILE', '/etc/wormgas/_brain.sqlite'))
        self.brain = wormgas.cogs.cobe.brain.Brain(str(brain_file))

    @discord.ext.commands.command()
    async def mention(self, ctx: discord.ext.commands.Context, channel: discord.TextChannel, *, watch_text: str):
        normalized_watch_text = watch_text.lower()
        self.bot.db.watch_words_insert(channel.id, ctx.author.id, normalized_watch_text)
        await ctx.author.send(f'Okay, I will ping you whenever I see a message in {channel} that contains {normalized_watch_text!r}')

    @discord.ext.commands.Cog.listener('on_message')
    async def listen_for_mentions(self, message: discord.Message):
        if not isinstance(message.channel, discord.TextChannel):
            log.debug('Ignoring message that is not in a TextChannel')
            return

        if message.author == self.bot.user:
            log.debug('Ignoring message from myself')
            return

        watch_words = self.bot.db.watch_words_list(message.channel.id)
        pinged_users = message.mentions
        for ww in watch_words:
            user = self.bot.get_user(ww['discord_user_id'])
            watch_text = ww['watch_text']
            if user == message.author:
                # Do not ping the person who sent the message
                continue
            if user in pinged_users:
                # Do not ping a user more than once for the same message
                continue
            if watch_text in message.clean_content.lower():
                pinged_users.append(user)
                await user.send(f'{message.author} mentioned {watch_text} in {message.channel}: {message.jump_url}')

    @discord.ext.commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages from myself.
        if message.author == self.bot.user:
            return

        # Ignore messages that contain commands.
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            log.info('Ignoring message because it contains a command.')
            return

        # Clean up message and generate response.
        text = message.clean_content
        text = text.replace(f'@{self.bot.user.display_name}', '')
        log.debug(f'Generating reply for {text!r}')
        response = await self.reply(text)

        # Always respond to direct messages
        now = int(time.time())
        if not message.guild:
            await message.author.send(response)
            return

        # If I was not mentioned, do not reply.
        if self.bot.user.id not in [u.id for u in message.mentions]:
            return

        last = int(self.bot.db.config_get(f'chat:last_time_respond:{message.channel.id}') or 0)
        wait = int(self.bot.db.config_get('chat:wait_respond') or 0)
        if last < now - wait:
            await message.channel.send(f'{message.author.mention}: {response}')
            self.bot.db.config_set(f'chat:last_time_respond:{message.channel.id}', now)
        else:
            await message.author.send(response)
            remaining = last + wait - now
            m = f'I am cooling down. I cannot respond in {message.channel.mention} for another {remaining} seconds.'
            await message.author.send(m)

    async def reply(self, text, learn=True):
        ignore = self.bot.db.config_get('chat:ignore')
        if ignore is not None and re.search(ignore, text, re.IGNORECASE):
            log.debug(f'Ignoring {text!r}')
            return random.choice(self.quotes)
        to_brain = text
        if learn:
            log.debug(f'Learning {to_brain!r}')
            self.brain.learn(to_brain)
        return self.brain.reply(to_brain)


async def setup(bot: wormgas.wormgas.Wormgas):
    await bot.add_cog(ChatCog(bot))
