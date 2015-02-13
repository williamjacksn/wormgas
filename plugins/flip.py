import random
import time


class FlipHandler:
    cmds = ['!flip']
    admin = False
    help_topic = 'flip'
    help_text = ['Use \x02!flip\x02 to flip a coin.']

    @classmethod
    def handle(cls, sender, target, tokens, bot):
        flip = random.choice(['Heads!', 'Tails!'])

        if not bot.is_irc_channel(target):
            bot.send_privmsg(sender, flip)
            return

        now = int(time.time())
        last = int(bot.c.get('flip:last', 0))
        wait = int(bot.c.get('flip:wait', 0))
        if last < now - wait:
            bot.send_privmsg(target, '{}: {}'.format(sender, flip))
            bot.c['flip:last'] = now
        else:
            bot.send_privmsg(sender, flip)
            remaining = last + wait - now
            m = u'I am cooling down. You cannot use {}'.format(tokens[0])
            m = u'{} in {} for another'.format(m, target)
            m = u'{} {} seconds.'.format(m, remaining)
            bot.send_privmsg(sender, m)
