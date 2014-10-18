#!/usr/bin/python
'''
dbaccess -- wrapper around Rainwave and Config DB calls for wormgas
https://github.com/subtlecoolness/wormgas
'''

import datetime
import logging
import time
import util

log = logging.getLogger(u'wormgas')


class Config(object):
    '''Connects to, retrieves from, and sets values in the local sqlite db.'''

    default_config = {
        # A regex that prevents matching words from being learned by the brain.
        # Special case: empty string will match no input and learn all words.
        u'msg:ignore': u'',

        # IRC channel the bot should join.
        u'irc:channel': u'#testgas',

        # IRC 'real name' the bot should use.
        u'irc:name': u'wormgas',

        # IRC nick the bot should use.
        u'irc:nick': u'testgas',

        # IRC network URL.
        u'irc:server': u'irc.synirc.net',

        # Wait values are in seconds and represent cooldowns for specific
        # commands.
        u'wait:8ball': 180,
        u'wait:flip': 60,
        u'wait:lstats': 2,
        u'wait:respond': 300,
        u'wait:roll': 90,
        u'wait:rps': 180,
        u'wait:stats': 300,
        u'wait:ustats': 180
    }

    def __init__(self, config_path, rps_path, apikeys_path):
        self.config = util.PersistentDict(config_path)
        self.rps = util.PersistentList(rps_path)
        self.apikeys = util.PersistentDict(apikeys_path)

        # Add any missing default config values.
        for key, value in self.default_config.iteritems():
            if self.config.get(key) is None:
                self.config.set(key, value)

    def add_id_to_nick(self, _id, nick):
        record = self.apikeys.get(nick, [None, None])
        record[0] = _id
        self.apikeys.set(nick, record)

    def add_key_to_nick(self, key, nick):
        record = self.apikeys.get(nick, [None, None])
        record[1] = key
        self.apikeys.set(nick, record)

    def drop_id_for_nick(self, nick):
        record = self.apikeys.get(nick, [None, None])
        record[0] = None
        if all(x is None for x in record):
            self.apikeys.remove(nick)
        else:
            self.apikeys.set(nick, record)

    def drop_key_for_nick(self, nick):
        record = self.apikeys.get(nick, [None, None])
        record[1] = None
        if all(x is None for x in record):
            self.apikeys.remove(nick)
        else:
            self.apikeys.set(nick, record)

    def get(self, _id, default=None):
        '''Read a value from the configuration database.

        Arguments:
            _id: the config_id that you want to read
            default: the return value if the config_id does not exist

        Returns: the config_value, or default if the config_id does not
            exist'''

        return self.config.get(_id, default)

    def get_bot_config(self):
        '''Return a dict of all botconfig values.'''
        return self.config.data

    def get_id_for_nick(self, nick):
        '''Return stored Rainwave ID for nick, or None if no ID is stored.'''
        return self.apikeys.get(nick, (None, None))[0]

    def get_key_for_nick(self, nick):
        '''Return stored API key for nick, or None if no key is stored.'''
        return self.apikeys.get(nick, (None, None))[1]

    def get_rps_challenge_totals(self, nick):
        '''Returns total times a player has challenged with each option'''
        challenge_totals = [0, 0, 0]
        for record in self.rps.data:
            if record[1] == nick:
                challenge_totals[int(record[2])] += 1

        return challenge_totals

    def get_rps_players(self):
        '''Get all players in the RPS history'''
        return sorted(set([x[1] for x in self.rps.data]))

    def get_rps_record(self, nick):
        '''Get the current RPS record for a particular nick. If nick is
        '!global', aggregate the record for all nicks.

        Returns: the tuple (wins, draws, losses)'''

        w = 0
        d = 0
        l = 0

        if nick == u'!global':
            games = [(x[2], x[3]) for x in self.rps.data]
        else:
            games = [(x[2], x[3]) for x in self.rps.data if x[1] == nick]

        for g in games:
            c = int(g[0])
            r = int(g[1])
            if c == (r + 1) % 3:
                w += 1
            elif c == r:
                d += 1
            elif c == (r + 2) % 3:
                l += 1

        return w, d, l

    def handle(self, _id=None, value=None):
        '''View or change config values.

        Arguments:
            _id: the config_id you want to view or change (leave empty to show
                all available config_ids)
            value: the value to change config_id to (leave empty to view
                current value)

        Returns: a list of strings'''

        rs = []

        if _id is not None and value is not None:
            self.set(_id, value)
            rs.append(u'{} = {}'.format(_id, value))
        elif _id is not None:
            rs.append(u'{} = {}'.format(_id, self.get(_id)))
        else:
            cids = sorted(self.config.keys())
            mlcl = int(self.get(u'maxlength:configlist', 10))
            while len(cids) > mlcl:
                clist = cids[:mlcl]
                cids[0:mlcl] = []
                rs.append(u', '.join(clist))
            rs.append(u', '.join(cids))

        return(rs)

    def log_rps(self, nick, challenge, response):
        '''Record an RPS game in the database'''
        now = str(datetime.datetime.utcnow())
        self.rps.append([now, nick, challenge, response])

    def rename_rps_player(self, old, new):
        '''Change the nick in RPS history, useful for merging two nicks'''
        new_list = list()
        for record in self.rps.data:
            if record[1] == old:
                new_list.append([record[0], new, record[2], record[3]])
            else:
                new_list.append(record)
        self.rps.replace(new_list)

    def reset_rps_record(self, nick):
        '''Reset the RPS record and delete game history for nick'''
        new_list = list()
        for record in self.rps.data:
            if record[1] != nick:
                new_list.append(record)
        self.rps.replace(new_list)

    def set(self, _id, value):
        '''Set a configuration value in the database.

        Arguments:
            _id: the config_id to set
            value: the value to set it to'''

        self.config.set(_id, value)

    def unset(self, _id):
        '''Unset (remove) a configuration value from the database.

        Arguments:
            _id: the config_id to unset'''

        self.config.remove(_id)
