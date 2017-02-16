class GreetHandler:
    cmds = ['!greet']
    admin = True
    help_topic = 'greet'
    help_text = [
        'Use \x02!greet add <nick> <message>\x02 to register a greeting.',
        'Whenever <nick> joins the channel (and auto-greeting is on), I will send <message> to the channel.',
        'If <message> starts with \'/me\' I will perform the action.',
        'Use \x02!greet drop <nick>\x02 to remove the greeting for <nick>',
        'Use \x02!greet list\x02 to see all the currently registered greetings.',
        'Use \x02!greet send <nick> to send the greeting for <nick> to the channel.',
        'Use \x02!greet auto [<on|off>]\x02 to turn on or off automatic greeting.'
    ]

    def __init__(self, sbot):
        @sbot.ee.on('JOIN')
        def auto_greet(message, bot):
            if bot.c.get('greet::auto', 'on').lower() == 'off':
                return
            tokens = message.split()
            source = tokens[0].lstrip(':')
            nick, _, _ = bot.parse_hostmask(source)
            self.send_greeting(nick, bot)

    def send_help(self, target, bot):
        for line in self.help_text:
            bot.send_privmsg(target, line)

    @staticmethod
    def send_greeting(nick, bot):
        greeting = bot.c.get('greet:{}'.format(nick.lower()))
        channel = bot.c.get('irc:channel')
        if greeting is not None:
            if greeting.startswith('/me '):
                bot.send_action(channel, greeting.split(maxsplit=1)[1])
            else:
                bot.send_privmsg(channel, greeting)

    def handle(self, sender, _, tokens, bot):
        if len(tokens) > 1:
            action = tokens[1].lower()
        else:
            self.send_help(sender, bot)
            return

        if action == 'add':
            if len(tokens) < 4:
                self.send_help(sender, bot)
                return
            nick = tokens[2].lower()
            greeting = ' '.join(tokens[3:])
            bot.c['greet:{}'.format(nick)] = greeting
            m = 'I added a greeting for {}: {}'.format(nick, greeting)
            bot.send_privmsg(sender, m)

        elif action == 'drop':
            if len(tokens) < 3:
                self.send_help(sender, bot)
                return
            nick = tokens[2].lower()
            bot.c.remove('greet:{}'.format(nick))
            m = 'I removed the greeting for {}.'.format(nick)
            bot.send_privmsg(sender, m)

        elif action == 'list':
            for key in sorted(bot.c.keys()):
                if key.startswith('greet:') and not key.startswith('greet::'):
                    m = '{}: {}'.format(key[6:], bot.c.get(key))
                    bot.send_privmsg(sender, m)

        elif action == 'send':
            if len(tokens) < 3:
                self.send_help(sender, bot)
                return
            nick = tokens[2].lower()
            if 'greet:{}'.format(nick) in bot.c:
                self.send_greeting(nick, bot)

        elif action == 'auto':
            if len(tokens) > 2:
                switch = tokens[2].lower()
            else:
                switch = ''

            if switch == 'on':
                bot.c['greet::auto'] = 'on'
            elif switch == 'off':
                bot.c['greet::auto'] = 'off'

            auto = bot.c.get('greet::auto', 'on').upper()
            bot.send_privmsg(sender, 'Automatic greeting is {}'.format(auto))
