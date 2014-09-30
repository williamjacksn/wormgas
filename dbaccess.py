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

try:
    import psycopg2
except:
    psycopg2 = None
    log.warning(u'psycopg2 unavailable -- RW db access turned off.')


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

        Returns: the config_value, or default if the config_id does not exist'''

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
            value: the value to change config_id to (leave empty to view current
                value)

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


class RainwaveDatabaseUnavailableError(IOError):
    '''Raised if the Rainwave database or PostgreSQL module is missing.'''


class RainwaveDatabase(object):
    '''Calls Rainwave DB functions while managing the database handles.'''

    def __init__(self, config):
        '''Instantiate a RainwaveDatabase object.

        Args:
            config: dbaccess.Config, stores required connection params.'''
        self.config = config
        self.song_info_cache = {}

    def connect(self):
        if not psycopg2:
            raise RainwaveDatabaseUnavailableError(u'No psycopg2 available.')
        conn_args = []
        conn_args.append(self.config.get(u'db:name'))
        conn_args.append(self.config.get(u'db:user'))
        conn_args.append(self.config.get(u'db:pass'))

        connstr = u'dbname=\'{}\' user=\'{}\' password=\'{}\''.format(*conn_args)
        try:
            self.rdbh = psycopg2.connect(connstr)
        except psycopg2.OperationalError:
            raise RainwaveDatabaseUnavailableError(u'Could not connect to DB.')

        autocommit = psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
        self.rdbh.set_isolation_level(autocommit)
        self.rcur = self.rdbh.cursor()

    def get_current_channel(self, uid):
        '''Return id of channel that uid is currently listening to, or None'''

        cur_chan = None
        sql = (u'select sid from rw_listeners where list_purge is false and '
            u'user_id = %s')
        self.rcur.execute(sql, (uid,))
        rows = self.rcur.fetchall()
        for row in rows:
            cur_chan = row[0]
        return cur_chan

    def get_fav_songs(self, user_id, cid):
        '''Get favourite songs'''

        m = u'Getting favourite songs for user {} on channel {}'
        log.info(m.format(user_id, cid))

        faves = list()
        sql = (
            u'select song_id, album_id, song_available, song_releasetime, '
            u'album_electionblock or coalesce(oac_electionblock, false) from '
            u'rw_songfavourites join rw_songs using (song_rating_id) join '
            u'rw_albums using (album_id) left join rw_song_oa_cat using '
            u'(song_id) left join rw_oa_categories using (oac_id) where '
            u'song_verified is true and rw_songs.sid = %s and user_id = %s')
        self.rcur.execute(sql, (cid, user_id))
        for r in self.rcur:
            faves.append({
                u'id': int(r[0]),
                u'album_id': int(r[1]),
                u'available': bool(r[2]),
                u'release_time': int(r[3]),
                u'blocked': bool(r[4])
            })
        return faves

    def get_forum_post_info(self, post_id=None):
        '''Return a string of information and a url for a forum post, default
        to the latest public post'''

        if post_id:
            sql = (u'select forum_name, post_subject, username, post_id from '
                u'phpbb_posts join phpbb_forums using (forum_id) join '
                u'phpbb_users on (phpbb_posts.poster_id = phpbb_users.user_id) '
                u'where post_id = %s')
            self.rcur.execute(sql, (post_id,))
        else:
            sql = (u'select forum_name, post_subject, username, post_id from '
                u'phpbb_posts join phpbb_forums using (forum_id) join '
                u'phpbb_users on (phpbb_posts.poster_id = phpbb_users.user_id) '
                u'join phpbb_acl_groups using (forum_id) where '
                u'phpbb_acl_groups.group_id = 1 and auth_role_id != 16 order by '
                u'post_time desc limit 1')
            self.rcur.execute(sql)

        rows = self.rcur.fetchall()
        for row in rows:
            url = u'http://rainwave.cc/forums/viewtopic.php?p={3}#p{3}'.format(*row)
            forum_name = row[0].decode(u'utf-8')
            post_subject = row[1].decode(u'utf-8')
            username = row[2].decode(u'utf-8')
            r = u'{} / {} by {}'.format(forum_name, post_subject, username)
            return r, url

    def get_history(self, cid):
        '''Yield information about the last several songs that played'''

        sql = (u'select timestamp with time zone \'epoch\' + sched_starttime * '
            u'interval \'1 second\' as start, album_name, album_id, song_title, '
            u'song_id from rw_schedule join rw_elections using (sched_id) join '
            u'rw_songs using (song_id) join rw_albums using (album_id) where '
            u'elec_position = 0 and sched_used > 0 and rw_songs.sid = %s order '
            u'by start desc limit 12')
        self.rcur.execute(sql, (cid,))
        for r in self.rcur.fetchall():
            yield r

    def get_id_for_nick(self, nick):
        '''Return user_id if this nick is a registered Rainwave account.'''
        user_id = None
        sql = u'select user_id from phpbb_users where username = %s'
        self.rcur.execute(sql, (nick,))
        rows = self.rcur.fetchall()
        for r in rows:
            user_id = r[0]
        return user_id

    def get_listener_chart_data(self, days):
        '''Yields (cid, guest_count, registered_count) tuples over the range.'''
        sql = (u'select sid, extract(hour from timestamp with time zone '
            u'\'epoch\' + lstats_time * interval \'1 second\') as hour, '
            u'round(avg(lstats_guests), 2), round(avg(lstats_regd), 2) from '
            u'rw_listenerstats where lstats_time > extract(epoch from '
            u'current_timestamp) - %s group by hour, sid order by sid, hour')
        seconds = 86400 * days
        self.rcur.execute(sql, (seconds,))
        rows = self.rcur.fetchall()
        for row in rows:
            yield row[0], row[2], row[3]

    def get_listener_stats(self, cid):
        '''Return (registered user count, guest count) for the station.'''
        regd = 0
        guest = 0

        sql = u'select sid, user_id from rw_listeners where list_purge is false'
        self.rcur.execute(sql)
        rows = self.rcur.fetchall()
        for row in rows:
            if cid in (0, row[0]):
                if row[1] > 1:
                    regd = regd + 1
                else:
                    guest = guest + 1
        return regd, guest

    def get_max_forum_post_id(self):
        '''Return id of latest public forum post'''
        post_id = 0
        sql = (u'select max(post_id) from phpbb_posts join phpbb_acl_groups '
            u'using (forum_id) where group_id = 1 and auth_role_id != 16')
        self.rcur.execute(sql)
        rows = self.rcur.fetchall()
        for row in rows:
            post_id = row[0]
        return post_id

    def get_max_song_id(self, cid):
        '''Return song_id of newest song on a channel'''
        song_id = 0
        sql = (u'select max(song_id) from rw_songs where song_verified is true '
            u'and sid = %s')
        self.rcur.execute(sql, (cid,))
        rows = self.rcur.fetchall()
        for row in rows:
            song_id = row[0]
        return song_id

    def get_new_song_info(self, cid):
        '''Return a list of tuples (song_info, url) for new songs on this
        channel up to three'''

        rs = []
        maxid = self.config.get(u'maxid:{}'.format(cid), 0)
        sql = (u'select song_id, album_name, song_title, song_url from rw_songs '
            u'join rw_albums using (album_id) where song_id > %s and '
            u'song_verified is true and rw_songs.sid = %s order by song_id desc '
            u'limit 3')
        self.rcur.execute(sql, (maxid, cid))
        rows = self.rcur.fetchall()
        for row in rows:
            urow = (x.decode(u'utf-8') for x in row[1:])
            r = u'{} / {} by '.format(*urow)
            artists = []
            sql = (u'select artist_name from rw_song_artist join rw_artists '
                u'using (artist_id) where song_id = %s')
            self.rcur.execute(sql, (row[0],))
            arows = self.rcur.fetchall()
            for arow in arows:
                artists.append(arow[0].decode(u'utf-8'))
            r += u', '.join(artists)
            rs.append((r, row[3]))
        return rs

    def get_radio_stats(self, cid):
        '''Return songs, albums, hours of music for one or all channel'''
        sql = (u'select count(song_id), count(distinct album_id), '
            u'round(sum(song_secondslong) / 3600.0, 2) from rw_songs where '
            u'song_verified is true')
        if cid > 0:
            sql += u' and sid = %s'
            self.rcur.execute(sql, (cid,))
        else:
            sql += u' and sid < 5'
            self.rcur.execute(sql)
        rows = self.rcur.fetchall()
        for r in rows:
            return r[0], r[1], r[2]

    def get_song_info(self, song_id):
        '''Return a dictionary of info for the given song_id'''

        song_id = int(song_id)
        if song_id in self.song_info_cache:
            if self.song_info_cache[song_id][u'release_time'] > time.time():
                log.debug(u'Song info cache hit for {}'.format(song_id))
                return self.song_info_cache[song_id]
            else:
                log.debug(u'Song info cache expire for {}'.format(song_id))
                del self.song_info_cache[song_id]

        sql = (u'select rw_songs.sid, album_id, song_title, song_genre, '
            u'song_comment, song_secondslong, song_rating_avg, song_rating_count, '
            u'song_url, album_name, song_available, song_releasetime from rw_songs '
            u'join rw_albums using (album_id) where song_id = %s')
        self.rcur.execute(sql, (song_id,))
        for r in self.rcur.fetchall():
            log.debug(u'Song info cache miss for {}'.format(song_id))
            return self.song_info_cache.setdefault(song_id, {
                u'id': int(song_id),
                u'chan_id': int(r[0]),
                u'album_id': int(r[1]),
                u'title': r[2].decode(u'utf-8'),
                u'genre': r[3].decode(u'utf-8'),
                u'comment': r[4].decode(u'utf-8'),
                u'length': int(r[5]),
                u'rating_avg': float(r[6]),
                u'rating_count': int(r[7]),
                u'url': r[8].decode(u'utf-8'),
                u'album': r[9].decode(u'utf-8'),
                u'available': bool(r[10]),
                u'release_time': int(r[11])
            })
