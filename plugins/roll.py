import random
import time


def is_irc_channel(s):
    return s and s[0] == u'#'


class RollHandler(object):
    cmds = [u'!roll']
    admin = False

    @staticmethod
    def parse_die_spec(die_spec):
        dice = 1
        sides = 6

        dice_spec, _, sides_spec = die_spec.partition(u'd')
        if dice_spec.isdigit():
            dice = min(int(dice_spec), 100)
        if sides_spec.isdigit():
            sides = min(int(sides_spec), 100)

        return dice, sides

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        die_spec = u'1d6'
        if len(tokens) > 1:
            die_spec = tokens[1]
        dice, sides = cls.parse_die_spec(die_spec)

        if sides == 0:
            private.append(u'Who ever heard of a 0-sided die?')
            return public, private

        rolls = [random.randint(1, sides) for _ in range(dice)]

        m = u'{}d{}:'.format(dice, sides)
        if 1 < dice < 11:
            m = u'{} [{}] ='.format(m, u', '.join(map(str, rolls)))
        m = u'{} {}'.format(m, sum(rolls))

        if not is_irc_channel(target):
            private.append(m)
            return public, private

        now = int(time.time())
        last = int(config.get(u'roll:last', 0))
        wait = int(config.get(u'roll:wait', 0))
        if last < now - wait:
            public.append(m)
            config.set(u'roll:last', now)
        else:
            private.append(m)
            remaining = last + wait - now
            m = u'I am cooling down. You cannot use {}'.format(tokens[0])
            m = u'{} in {} for another'.format(m, target)
            m = u'{} {} seconds.'.format(m, remaining)
            private.append(m)

        return public, private
