import random
import time


class RollHandler(object):
    cmds = ['!roll']
    admin = False
    help_topic = 'roll'
    help_text = ['Use \x02!roll [#d^]\x02 to roll a ^-sided die # times.']

    @staticmethod
    def parse_die_spec(die_spec):
        dice = 1
        sides = 6

        dice_spec, _, sides_spec = die_spec.partition('d')
        if dice_spec.isdigit():
            dice = min(int(dice_spec), 100)
        if sides_spec.isdigit():
            sides = min(int(sides_spec), 100)

        return dice, sides

    @classmethod
    def handle(cls, sender, target, tokens, bot):
        die_spec = '1d6'
        if len(tokens) > 1:
            die_spec = tokens[1]
        dice, sides = cls.parse_die_spec(die_spec)

        if sides == 0:
            bot.send_privmsg(sender, 'Who ever heard of a 0-sided die?')
            return

        rolls = [random.randint(1, sides) for _ in range(dice)]

        m = '{}d{}:'.format(dice, sides)
        if 1 < dice < 11:
            m = '{} [{}] ='.format(m, ', '.join(map(str, rolls)))
        m = '{} {}'.format(m, sum(rolls))

        if not bot.is_irc_channel(target):
            bot.send_privmsg(sender, m)
            return

        now = int(time.time())
        last = int(bot.c.get('roll:last', 0))
        wait = int(bot.c.get('roll:wait', 0))
        if last < now - wait:
            bot.send_privmsg(target, m)
            bot.c.set(u'roll:last', now)
        else:
            bot.send_privmsg(sender, m)
            remaining = last + wait - now
            m = u'I am cooling down. You cannot use {}'.format(tokens[0])
            m = u'{} in {} for another'.format(m, target)
            m = u'{} {} seconds.'.format(m, remaining)
            bot.send_privmsg(sender, m)
