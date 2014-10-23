import time
import wikipedia


def is_irc_channel(s):
    return s and s[0] == u'#'


class WikipediaHandler(object):
    cmds = [u'!wiki']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        search_title = u' '.join(tokens[1:])
        try:
            page = wikipedia.page(search_title)
        except wikipedia.exceptions.DisambiguationError as err:
            private.append(u'Your query returned a disambiguation page.')
            if len(err.options) < 6:
                private.append(u'Options: {}'.format(u'; '.join(err.options)))
            else:
                opts_list = u'; '.join(err.options[:6])
                private.append(u'Some options: {} ...'.format(opts_list))
            return public, private
        except wikipedia.exceptions.PageError as err:
            private.append(str(err))
            return public, private

        summ = u' '.join(page.summary[:200].splitlines())
        m = u'{} // {}... [ {} ]'.format(page.title, summ, page.url)

        if not is_irc_channel(target):
            private.append(m)
            return public, private

        now = int(time.time())
        last = int(config.get(u'wiki:last', 0))
        wait = int(config.get(u'wiki:wait', 0))
        if last < now - wait:
            public.append(m)
            config.set(u'wiki:last', now)
        else:
            private.append(m)
            remaining = last + wait - now
            m = u'I am cooling down. You cannot use {}'.format(tokens[0])
            m = u'{} in {} for another'.format(m, target)
            m = u'{} {} seconds.'.format(m, remaining)
            private.append(m)

        return public, private
