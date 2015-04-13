class SetHandler:
    cmds = ['!set']
    admin = True
    help_topic = 'set'
    help_text = [('Use \x02!set [<id>] [<value>]\x02 to display or change '
                  'configuration settings.'),
                 'Leave off <value> to see the current setting.',
                 ('Leave off <id> and <value> to see a list of all available '
                  'config ids.')]

    @staticmethod
    def handle(sender, target, tokens, bot):
        if len(tokens) > 2:
            value = ' '.join(tokens[2:])
            key = tokens[1]
            bot.c[key] = value
            bot.send_privmsg(sender, '{} = {}'.format(key, value))
        elif len(tokens) > 1:
            key = tokens[1]
            value = bot.c.get(key)
            if value is None:
                bot.send_privmsg(sender, '{} is not set.'.format(key))
            else:
                bot.send_privmsg(sender, '{} = {}'.format(key, value))
        else:
            config_ids = sorted(bot.c.keys())
            max_length = int(bot.c.get('config:max_length', 10))
            while len(config_ids) > max_length:
                config_list = config_ids[:max_length]
                config_ids[0:max_length] = []
                bot.send_privmsg(sender, ', '.join(config_list))
            bot.send_privmsg(sender, ', '.join(config_ids))


class UnsetHandler:
    cmds = ['!unset']
    admin = True
    help_topic = 'unset'
    help_text = ['Use \x02!unset <id>\x02 to remove a configuration setting.']

    def handle(self, sender, target, tokens, bot):
        if len(tokens) > 1:
            key = tokens[1]
            bot.c.remove(key)
            bot.send_privmsg(sender, '{} has been unset.'.format(key))
        else:
            bot.send_privmsg(sender, self.help_text)
