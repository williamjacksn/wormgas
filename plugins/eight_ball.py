import random
import time


class EightBallHandler:
    cmds = ['!8ball']
    admin = False
    help_topic = '8ball'
    help_text = ['Use \x02!8ball\x02 to ask a question of the magic 8ball.']

    RESPONSES = [
        'As I see it, yes.',
        'Ask again later.',
        'Better not tell you now.',
        'Cannot predict now.',
        'Concentrate and ask again.',
        'Don\'t count on it.',
        'It is certain.',
        'It is decidedly so.',
        'Most likely.',
        'My reply is no.',
        'My sources say no.',
        'Outlook good.',
        'Outlook not so good.',
        'Reply hazy, try again.',
        'Signs point to yes.',
        'Very doubtful.',
        'Without a doubt.',
        'Yes.',
        'Yes - definitely.',
        'You may rely on it.'
    ]

    def handle(self, sender, target, tokens, bot):
        response = random.choice(self.RESPONSES)

        if not bot.is_irc_channel(target):
            bot.send_privmsg(sender, response)
            return

        now = int(time.time())
        last = int(bot.c.get('8ball:last', 0))
        wait = int(bot.c.get('8ball:wait', 0))
        if last < now - wait:
            bot.send_privmsg(target, '{}: {}'.format(sender, response))
            if 'again' not in response:
                bot.c['8ball:last'] = now
        else:
            bot.send_privmsg(sender, response)
            remaining = last + wait - now
            m = 'I am cooling down. You cannot use {}'.format(tokens[0])
            m = '{} in {} for another'.format(m, target)
            m = '{} {} seconds.'.format(m, remaining)
            bot.send_privmsg(sender, m)
