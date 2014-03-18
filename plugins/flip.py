import random
import time


def is_irc_channel(s):
    return s and s[0] == u'#'


class FlipHandler(object):
    cmds = [u'!flip']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()
        flip = random.choice([u'Heads!', u'Tails!'])

        if not is_irc_channel(target):
            private.append(flip)
            return public, private

        now = int(time.time())
        last = int(config.get(u'flip:last', 0))
        wait = int(config.get(u'flip:wait', 0))
        if last < now - wait:
            public.append(flip)
            config.set(u'flip:last', now)
        else:
            private.append(flip)
            remaining = last + wait - now
            m = u'I am cooling down. You cannot use {}'.format(tokens[0])
            m = u'{} in {} for another'.format(m, target)
            m = u'{} {} seconds.'.format(m, remaining)
            private.append(m)

        return public, private
