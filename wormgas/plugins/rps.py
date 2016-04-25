import random
import time


class RpsGameHandler:
    cmds = ['!paper', '!rock', '!scissors']
    admin = False
    help_topic = 'rps'
    help_text = [('Use \x02!rock\x02, \x02!paper\x02, or \x02!scissors\x02 to '
                  'play a game.'),
                 ('Use \x02!rps record [<nick>]\x02 to see the record for '
                  '<nick>. Leave off <nick> to see your own record.'),
                 ('Use \x02!rps stats [<nick>]\x02 to see some statistics for '
                  '<nick>. Leave off <nick> to see your own statistics.'),
                 ('Use \x02!rps reset\x02 to reset your record and delete '
                  'your game history. There is no confirmation and this '
                  'cannot be undone.'),
                 'Use \x02!rps who\x02 to see a list of known players']

    @staticmethod
    def get_rps_config(bot):
        rps_config_path = bot.c.path.with_name('_rps.json')
        return bot.c.__class__(rps_config_path, pretty=True)

    def handle(self, sender, target, tokens, bot):
        action = tokens[0].lstrip('!').lower()
        rps_config = self.get_rps_config(bot)
        player_dict = rps_config.get(sender, {})
        global_dict = rps_config.get('!global', {})

        rps = ['rock', 'paper', 'scissors']
        challenge = rps.index(action)
        response = random.randint(0, 2)

        player_dict[action] = player_dict.get(action, 0) + 1
        global_dict[action] = global_dict.get(action, 0) + 1

        m = 'You challenge with {}. I counter with'.format(action)
        m = '{} {}.'.format(m, rps[response])

        if challenge == (response + 1) % 3:
            player_dict['wins'] = player_dict.get('wins', 0) + 1
            global_dict['wins'] = global_dict.get('wins', 0) + 1
            m = '{} You win!'.format(m)
        elif challenge == response:
            player_dict['draws'] = player_dict.get('draws', 0) + 1
            global_dict['draws'] = global_dict.get('draws', 0) + 1
            m = '{} We draw!'.format(m)
        elif challenge == (response + 2) % 3:
            player_dict['losses'] = player_dict.get('losses', 0) + 1
            global_dict['losses'] = global_dict.get('losses', 0) + 1
            m = '{} You lose!'.format(m)

        rps_config[sender] = player_dict
        rps_config['!global'] = global_dict

        w = player_dict.get('wins', 0)
        d = player_dict.get('draws', 0)
        l = player_dict.get('losses', 0)
        pw = int(float(w) / float(w + d + l) * 100)
        pd = int(float(d) / float(w + d + l) * 100)
        pl = int(float(l) / float(w + d + l) * 100)
        m = '{} Your current record is '.format(m)
        m = '{}{}-{}-{} or {}%-{}%-{}% (w-d-l).'.format(m, w, d, l, pw, pd, pl)

        if not bot.is_irc_channel(target):
            bot.send_privmsg(sender, m)
            return

        now = int(time.time())
        last = int(bot.c.get('rps:last', 0))
        wait = int(bot.c.get('rps:wait', 0))
        if last < now - wait:
            bot.send_privmsg(target, m)
            bot.c.set('rps:last', now)
        else:
            bot.send_privmsg(sender, m)
            remaining = last + wait - now
            m = 'I am cooling down. You cannot use {}'.format(tokens[0])
            m = '{} in {} for another {} seconds.'.format(m, target, remaining)
            bot.send_privmsg(sender, m)


class RpsUtilHandler:
    cmds = ['!rps']
    admin = False

    def handle(self, sender, target, tokens, bot):
        if len(tokens) > 1:
            action = tokens[1].lower()
        else:
            for line in RpsGameHandler.help_text:
                bot.send_privmsg(sender, line)
            return

        if action == 'record':
            if len(tokens) > 2:
                player = tokens[2]
            else:
                player = sender
            m = self.get_rps_record(player, bot)
        elif action == 'stats':
            if len(tokens) > 2:
                player = tokens[2]
            else:
                player = sender
            m = self.get_rps_stats(player, bot)
        elif action == 'reset':
            self.reset_rps_stats(sender, bot)
            m = 'I reset your RPS record and deleted your game history.'
            bot.send_privmsg(sender, m)
            return
        elif action == 'who':
            players = self.get_player_list(bot)
            max_length = int(bot.c.get('rps:max_length', 10))
            while len(players) > max_length:
                plist = players[:max_length]
                players[:max_length] = []
                m = 'RPS players: {}'.format(', '.join(plist))
                bot.send_privmsg(sender, m)
            m = 'RPS players: {}'.format(', '.join(players))
            bot.send_privmsg(sender, m)
            return
        else:
            for line in RpsGameHandler.help_text:
                bot.send_privmsg(sender, line)
            return

        if not bot.is_irc_channel(target):
            bot.send_privmsg(sender, m)
            return

        now = int(time.time())
        last = int(bot.c.get('rps:last', 0))
        wait = int(bot.c.get('rps:wait', 0))
        if last < now - wait:
            bot.send_privmsg(target, m)
            bot.c.set('rps:last', now)
        else:
            bot.send_privmsg(sender, m)
            remaining = last + wait - now
            m = 'I am cooling down. You cannot use {}'.format(tokens[0])
            m = '{} in {} for another {} seconds.'.format(m, target, remaining)
            bot.send_privmsg(sender, m)

    @staticmethod
    def get_player_list(bot):
        rps_config = RpsGameHandler.get_rps_config(bot)
        return sorted(rps_config.keys())

    @staticmethod
    def get_rps_record(player, bot):
        rps_config = RpsGameHandler.get_rps_config(bot)

        if player not in rps_config:
            return '{} does not play. :('.format(player)

        player_dict = rps_config.get(player)
        w = player_dict.get('wins', 0)
        d = player_dict.get('draws', 0)
        l = player_dict.get('losses', 0)
        t = w + d + l
        m = 'RPS record for {} ({} game'.format(player, t)
        if t != 1:
            m = '{}s'.format(m)
        m = '{}) is {}-{}-{} (w-d-l).'.format(m, w, d, l)
        return m

    @staticmethod
    def get_rps_stats(player, bot):
        rps_config = RpsGameHandler.get_rps_config(bot)

        if player not in rps_config:
            return '{} does not play. :('.format(player)

        player_dict = rps_config.get(player)
        r = player_dict.get('rock', 0)
        p = player_dict.get('paper', 0)
        s = player_dict.get('scissors', 0)
        t = r + p + s
        if t > 0:
            r_rate = r / float(t) * 100
            p_rate = p / float(t) * 100
            s_rate = s / float(t) * 100
            m = '{} challenges with rock/paper/scissors at'.format(player)
            m = '{} these rates: '.format(m)
            m = '{}{:3.1f}/{:3.1f}/{:3.1f}%.'.format(m, r_rate, p_rate, s_rate)
        else:
            m = u'{} does not play. :('.format(player)
        return m

    @staticmethod
    def reset_rps_stats(player, bot):
        rps_config = RpsGameHandler.get_rps_config(bot)
        if player in rps_config:
            player_dict = rps_config[player]
            global_dict = rps_config['!global']
            for key in player_dict:
                global_dict[key] = global_dict[key] - player_dict[key]
            rps_config.remove(player)
            rps_config['!global'] = global_dict


class RpsMvHandler:
    cmds = ['!rpsmv']
    admin = True
    help_topic = 'rpsmv'
    help_text = [('Use \x02!rpsmv <oldnick> <newnick>\x02 to reassign stats '
                  'and game history from one player to another.')]

    def handle(self, sender, _, tokens, bot):
        if len(tokens) < 3:
            for line in self.help_text:
                bot.send_privmsg(sender, line)
            return

        rps_config = RpsGameHandler.get_rps_config(bot)
        old_dict = rps_config.get(tokens[1], {})
        new_dict = rps_config.get(tokens[2], {})
        for key in old_dict:
            new_dict[key] = new_dict.get(key, 0) + old_dict[key]
        rps_config.remove(tokens[1])
        rps_config[tokens[2]] = new_dict
        m = 'I assigned RPS game history for {1} to {2}.'.format(*tokens)
        bot.send_privmsg(sender, m)
