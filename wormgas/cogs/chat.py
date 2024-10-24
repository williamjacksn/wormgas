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
