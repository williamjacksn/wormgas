import re
import random
import time

from .cobe import brain


class ChatHandler:
    cmds = []
    admin = False

    quotes = [
        ('Attack the evil that is within yourself, rather than attacking the '
         'evil that is in others.'),
        'Before you embark on a journey of revenge, dig two graves.',
        'Better a diamond with a flaw than a pebble without.',
        'Everything has beauty, but not everyone sees it.',
        'He who knows all the answers has not been asked all the questions.',
        ('He who learns but does not think, is lost! He who thinks but does '
         'not learn is in great danger.'),
        'I hear and I forget. I see and I remember. I do and I understand.',
        ('If what one has to say is not better than silence, then one should '
         'keep silent.'),
        ('If you make a mistake and do not correct it, this is called a '
         'mistake.'),
        'Ignorance is the night of the mind but a night without moon and star.',
        ('Music produces a kind of pleasure which human nature cannot do '
         'without.'),
        'Only the wisest and stupidest of men never change.',
        ('Our greatest glory is not in never falling, but in rising every time '
         'we fall.'),
        'Respect yourself and others will respect you.',
        'Silence is a true friend who never betrays.',
        ('The hardest thing of all is to find a black cat in a dark room, '
         'especially if there is no cat.'),
        ('The man who asks a question is a fool for a minute, the man who does '
         'not ask is a fool for life.'),
        'The superior man is modest in his speech, but exceeds in his actions.',
        'To be wronged is nothing, unless you continue to remember it.',
        ('To see what is right and not to do it, is want of courage or of '
         'principle.'),
        ('What you know, you know, what you do not know, you do not know. This '
         'is true wisdom.')
    ]

    anon_names = ['someone', 'somebody', 'anyone', 'anybody',
                  'no one', 'nobody', 'everyone', 'everybody']

    def __init__(self, sbot):
        brain_file = sbot.c.path.with_name('_brain.sqlite')
        self.brain = brain.Brain(str(brain_file))

        @sbot.ee.on('PING')
        def handle_ping(message, bot):
            now = int(time.time())
            last = int(bot.c.get('chat:last_time_public_message', 0))
            wait = int(bot.c.get('chat:wait_revive', 3600))
            if last < now - wait:
                if not bot.in_channel:
                    if bot.debug:
                        m = '** Would revive chat, but not currently in channel'
                        bot.log(m)
                    return
                if bot.debug:
                    bot.log('** Reviving chat')
                last_message = bot.c.get('chat:last_message', '')
                response = self.reply(last_message, bot, learn=False)
                target = bot.c.get('irc:channel')
                bot.send_privmsg(target, response)
                bot.c['chat:last_time_respond'] = now
                bot.c['chat:last_time_public_message'] = now
            else:
                remaining = last + wait - now
                if bot.debug:
                    m = '** Will revive chat in {} seconds'.format(remaining)
                    bot.log(m)

        @sbot.ee.on('PRIVMSG')
        def handle_privmsg(message, bot):
            tokens = message.split()
            source = tokens[0].lstrip(':')
            source_nick, _, _ = bot.parse_hostmask(source)
            target = tokens[2]
            cmd = tokens[3].lstrip(':').lower()
            builtin_commands = {'!load', '!help'}
            public_commands = set(bot.plug_commands.keys())
            admin_commands = set(bot.plug_commands_admin.keys())
            all_commands = builtin_commands | public_commands | admin_commands
            if cmd in all_commands:
                return

            text = message.split(' :', maxsplit=1)[1]
            if bot.debug:
                bot.log('** Responding to {!r}'.format(text))
            response = self.reply(text, bot)

            now = int(time.time())

            if not bot.is_irc_channel(target):
                bot.send_privmsg(source_nick, response)
                return
            else:
                bot.c['chat:last_time_public_message'] = now

            if not re.search(bot.c.get('irc:nick'), text, flags=re.IGNORECASE):
                return

            last = int(bot.c.get('chat:last_time_respond', 0))
            wait = int(bot.c.get('chat:wait_respond', 0))
            if last < now - wait:
                bot.send_privmsg(target, '{}: {}'.format(source_nick, response))
                bot.c['chat:last_time_respond'] = now
            else:
                bot.send_privmsg(source_nick, response)
                remaining = last + wait - now
                m = 'I am cooling down. I cannot respond in {}'.format(target)
                m = '{} for another {} seconds.'.format(m, remaining)
                bot.send_privmsg(source_nick, m)

    def reply(self, text, bot, learn=True):
        ignore = bot.c.get('chat:ignore')
        if ignore is not None and re.search(ignore, text, re.IGNORECASE):
            if bot.debug:
                bot.log('** Ignoring {!r}'.format(text))
            return random.choice(self.quotes)
        bot.c['chat:last_message'] = text
        to_brain = text
        for member in bot.members:
            anon_name = random.choice(self.anon_names)
            to_brain = to_brain.replace(member, anon_name)
        if learn:
            if bot.debug:
                bot.log('** Learning {!r}'.format(to_brain))
            self.brain.learn(to_brain)
        return self.brain.reply(to_brain)
