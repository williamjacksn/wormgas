import random
import time


def is_irc_channel(s):
    return s and s[0] == u'#'


RESPONSES = [
    u'As I see it, yes.',
    u'Ask again later.',
    u'Better not tell you now.',
    u'Cannot predict now.',
    u'Concentrate and ask again.',
    u'Don\'t count on it.',
    u'It is certain.',
    u'It is decidedly so.',
    u'Most likely.',
    u'My reply is no.',
    u'My sources say no.',
    u'Outlook good.',
    u'Outlook not so good.',
    u'Reply hazy, try again.',
    u'Signs point to yes.',
    u'Very doubtful.',
    u'Without a doubt.',
    u'Yes.',
    u'Yes - definitely.',
    u'You may rely on it.'
]


class EightBallHandler(object):
    cmds = [u'!8ball']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()
        response = random.choice(RESPONSES)

        if not is_irc_channel(target):
            private.append(response)
            return public, private

        now = int(time.time())
        last = int(config.get(u'8ball:last', 0))
        wait = int(config.get(u'8ball:wait', 0))
        if last < now - wait:
            public.append(response)
            if u'again' not in response:
                config.set(u'8ball:last', now)
        else:
            private.append(response)
            remaining = last + wait - now
            m = u'I am cooling down. You cannot use {}'.format(tokens[0])
            m = u'{} in {} for another'.format(m, target)
            m = u'{} {} seconds.'.format(m, remaining)
            private.append(m)

        return public, private
