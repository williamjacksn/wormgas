import textwrap
import time
import wikipedia


class WikipediaHandler:
    cmds = [u'!wiki']
    admin = False
    help_topic = 'wiki'
    help_text = [('Use \x02!wiki <search terms>\x02 to look up information on '
                  'Wikipedia.')]

    def handle(self, sender, target, tokens, bot):
        if len(tokens) < 2:
            for line in self.help_text:
                bot.send_privmsg(sender, line)
            return

        search_title = ' '.join(tokens[1:])
        try:
            page = wikipedia.page(search_title)
        except wikipedia.exceptions.DisambiguationError as err:
            m = 'Your query returned a disambiguation page.'
            bot.send_privmsg(sender, m)
            if len(err.options) < 6:
                m = 'Options: {}'.format(u'; '.join(err.options))
                bot.send_privmsg(sender, m)
            else:
                opts_list = u'; '.join(err.options[:6])
                m = 'Some options: {} ...'.format(opts_list)
                bot.send_privmsg(sender, m)
            return
        except wikipedia.exceptions.PageError as err:
            bot.send_privmsg(sender, str(err))
            return

        summ = textwrap.shorten(page.summary, width=300, placeholder=' ...')
        m = '{} // {} [ {} ]'.format(page.title, summ, page.url)

        if not bot.is_irc_channel(target):
            bot.send_privmsg(sender, m)
            return

        now = int(time.time())
        last = int(bot.c.get('wiki:last', 0))
        wait = int(bot.c.get('wiki:wait', 0))
        if last < now - wait:
            bot.send_privmsg(target, m)
            bot.c.set('wiki:last', now)
        else:
            bot.send_privmsg(sender, m)
            remaining = last + wait - now
            m = 'I am cooling down. You cannot use {}'.format(tokens[0])
            m = '{} in {} for another'.format(m, target)
            m = '{} {} seconds.'.format(m, remaining)
            bot.send_privmsg(sender, m)
