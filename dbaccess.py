#!/usr/bin/python
"""
dbaccess -- wrapper around Rainwave and Config DB calls for wormgas
https://github.com/subtlecoolness/wormgas
"""

import logging
import sqlite3

log = logging.getLogger("wormgas")

try:
    import psycopg2
except:
    psycopg2 = None
    log.warning("psycopg2 unavailable -- RW db access turned off.")

class Config(object):
    """Connects to, retrieves from, and sets values in the local sqlite db."""

    default_bot_config = {
        # A regex that prevents matching words from being learned by the brain.
        # Special case: empty string will match no input and learn all words.
        "msg:ignore": "",

        # IRC channel the bot should join.
        "irc:channel": "#testgas",

        # IRC "real name" the bot should use.
        "irc:name": "wormgas",

        # IRC nick the bot should use.
        "irc:nick": "testgas",

        # IRC network URL.
        "irc:server": "irc.synirc.net",

        # Wait values are in seconds and represent cooldowns for specific
        # commands.
        "wait:8ball": 90,
    }

    def __init__(self, path):
        self.cdbh = sqlite3.connect(path, isolation_level=None,
            check_same_thread=False)
        self.ccur = self.cdbh.cursor()

        tables = {
            "botconfig": "(config_id, config_value)",
            "known_users": "(user_nick, user_userhost)",
            "rps_log": "(timestamp, user_nick, challenge, response)",
            "user_keys": "(user_nick, user_id, user_key)"
        }

        tsql = "select name from sqlite_master where name = ?"

        # Add any missing tables.
        for t_name, t_def in tables.iteritems():
            self.ccur.execute(tsql, (t_name,))
            existing = self.ccur.fetchall()
            if len(existing) < 1:
                csql = "create table %s %s" % (t_name, t_def)
                self.ccur.execute(csql)

        # Add any missing default bot config values.
        for key, value in self.default_bot_config.iteritems():
            if self.get(key) == None:
                self.set(key, value)

    def __del__(self):
        try:
            self.cdbh.close()
        except AttributeError: pass # Never opened the db; no handle to close.

    def add_id_to_nick(self, id, nick):
        sql = "update user_keys set user_id = ? where user_nick = ?"
        self.ccur.execute(sql, (id, nick))

    def add_key_to_nick(self, key, nick):
        sql = "update user_keys set user_key = ? where user_nick = ?"
        self.ccur.execute(sql, (key, nick))

    def drop_id_for_nick(self, nick):
        sql = "update user_keys set user_id = null where user_nick = ?"
        self.ccur.execute(sql, (nick,))

    def drop_key_for_nick(self, nick):
        sql = "update user_keys set user_key = null where user_nick = ?"
        self.ccur.execute(sql, (nick,))

    def get(self, id):
        """Read a value from the configuration database.

        Arguments:
            id: the config_id that you want to read

        Returns: the config_value, or None if the config_id does not exist"""

        config_value = None
        sql = "select config_value from botconfig where config_id = ?"
        self.ccur.execute(sql, (id,))
        for r in self.ccur:
            config_value = r[0]
        log.debug("Current value of %s is %s" % (id, config_value))
        return config_value

    def get_bot_config(self):
        """Return a dict of all botconfig values."""
        results = {}
        sql = "select config_id, config_value from botconfig"
        self.ccur.execute(sql)
        for r in self.ccur:
            results[r[0]] = r[1]
        return results

    def get_id_for_nick(self, nick):
        """Return stored Rainwave ID for nick, or None if no ID is stored."""
        stored_id = None
        sql = "select user_id from user_keys where user_nick = ?"
        self.ccur.execute(sql, (nick,))
        for r in self.ccur:
            stored_id = r[0]
        return stored_id

    def get_key_for_nick(self, nick):
        """Return stored API key for nick, or None if no key is stored."""
        stored_id = None
        sql = "select user_key from user_keys where user_nick = ?"
        self.ccur.execute(sql, (nick,))
        for r in self.ccur:
            stored_id = r[0]
        return stored_id

    def get_rps_challenge_totals(self, nick):
        """Returns total times a player has challenged with each option"""
        challenge_totals = [0, 0, 0]
        sql = "select challenge, response from rps_log where user_nick = ?"
        self.ccur.execute(sql, (nick,))
        rows = self.ccur.fetchall()
        for r in rows:
            challenge_totals[int(r[0])] += 1

        return challenge_totals

    def get_rps_players(self):
        """Get all players in the RPS history"""
        players = []
        sql = "select distinct user_nick from rps_log order by user_nick"
        self.ccur.execute(sql)
        rows = self.ccur.fetchall()
        for r in rows:
            players.append(r[0])
        return players

    def get_rps_record(self, nick):
        """Get the current RPS record for a particular nick. If nick is
        "!global", aggregate the record for all nicks.

        Returns: the tuple (wins, draws, losses)"""

        w = 0
        d = 0
        l = 0

        sql = "select challenge, response from rps_log"
        if nick != "!global":
            sql += " where user_nick = ?"
            self.ccur.execute(sql, (nick,))
        else:
            self.ccur.execute(sql)

        games = self.ccur.fetchall()
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

    def handle(self, id=None, value=None):
        """View or change config values.

        Arguments:
            id: the config_id you want to view or change (leave empty to show
                all available config_ids)
            value: the value to change config_id to (leave empty to view current
                value)

        Returns: a list of strings"""

        rs = []

        if id and value:
            self.set(id, value)
            rs.append("%s = %s" % (id, value))
        elif id:
            rs.append("%s = %s" % (id, self.get(id)))
        else:
            cids = []
            sql = "select distinct config_id from botconfig"
            self.ccur.execute(sql)
            for r in self.ccur:
                cids.append(r[0])
            cids.sort()
            mlcl = int(self.get("maxlength:configlist"))
            while len(cids) > mlcl:
                clist = cids[:mlcl]
                cids[0:mlcl] = []
                rs.append(", ".join(clist))
            rs.append(", ".join(cids))

        return(rs)

    def log_rps(self, nick, challenge, response):
        """Record an RPS game in the database"""
        sql = ("insert into rps_log (timestamp, user_nick, challenge, "
            "response) values (datetime('now'), ?, ?, ?)")
        self.ccur.execute(sql, (nick, challenge, response))

    def rename_rps_player(self, old, new):
        """Change the nick in RPS history, useful for merging two nicks"""
        sql = "update rps_log set user_nick = ? where user_nick = ?"
        self.ccur.execute(sql, (new, old))

    def reset_rps_record(self, nick):
        """Reset the RPS record and delete game history for nick"""
        sql = "delete from rps_log where user_nick = ?"
        self.ccur.execute(sql, (nick,))

    def set(self, id, value):
        """Set a configuration value in the database.

        Arguments:
            id: the config_id to set
            value: the value to set it to"""

        cur_config_value = self.get(id)
        if cur_config_value is None:
            sql = ("insert into botconfig (config_id, config_value) values "
                "(?, ?)")
            self.ccur.execute(sql, (id, value))
        else:
            sql = "update botconfig set config_value = ? where config_id = ?"
            self.ccur.execute(sql, (value, id))
        log.debug("New value of %s is %s" % (id, value))

    def store_nick(self, nick):
        """Store this nick in user_keys for later use."""
        stored_nick = None
        sql = "select distinct user_nick from user_keys where user_nick = ?"
        self.ccur.execute(sql, (nick,))
        for r in self.ccur:
            stored_nick = r[0]
        if not stored_nick:
            sql = "insert into user_keys (user_nick) values (?)"
            self.ccur.execute(sql, (nick,))
    
    def unset(self, id):
        """Unset (remove) a configuration value from the database.
        
        Arguments:
            id: the config_id to unset"""
        
        sql = "delete from botconfig where config_id = ?"
        self.ccur.execute(sql, (id,))
        log.debug("Unset %s" % id)

class RainwaveDatabaseUnavailableError(IOError):
    """Raised if the Rainwave database or PostgreSQL module is missing."""

class RainwaveDatabase(object):
    """Calls Rainwave DB functions while managing the database handles."""

    def __init__(self, config):
        """Instantiate a RainwaveDatabase object.

        Args:
            config: dbaccess.Config, stores required connection params."""
        self.config = config

    def add_album_to_cdg(self, album_id, cdg_name):
        """Add all songs in an album to a cooldown group"""

        for song_id in self.get_album_songs(album_id):
            self.add_song_to_cdg(song_id, cdg_name)

        cid = self.get_album_cid(album_id)
        if cid is None:
            return 1, "Invalid album_id: %s" % album_id

        return 0, (cid, self.get_album_name(album_id), cdg_name)

    def add_song_to_cdg(self, song_id, cdg_name):
        """Add a song to a cooldown group, return a tuple describing the result
        of the operation:

        (0, (cid, album_name, song_title, cdg_name))
        (1, "Error message")"""

        # Get channel id for this song_id

        cid = self.get_song_cid(song_id)

        if cid is None:
            return 1, "Invalid song_id: %s" % song_id

        # Get the cdg_id for this cdg_name

        cdg_id = None

        # Look for an existing, verified cooldown group

        sql = ("select oac_id from rw_oa_categories where sid = %s and "
            "oac_name = %s and oac_verified is true limit 1")
        self.rcur.execute(sql, (cid, cdg_name))
        for r in self.rcur.fetchall():
            cdg_id = r[0]

        # Look for an existing, unverified cooldown group

        if cdg_id is None:
            sql = ("select oac_id from rw_oa_categories where sid = %s and "
                "oac_name = %s and oac_verified is false limit 1")
            self.rcur.execute(sql, (cid, cdg_name))
            for r in self.rcur.fetchall():
                cdg_id = r[0]
                sql = ("update rw_oa_categories set oac_verified = true where "
                    "oac_id = %s")
                self.rcur.execute(sql, (cdg_id,))

        # Create a new cooldown group

        if cdg_id is None:
            sql = ("insert into rw_oa_categories (sid, oac_name) values "
                "(%s, %s)")
            self.rcur.execute(sql, (cid, cdg_name))
            sql = ("select oac_id from rw_oa_categories where sid = %s and "
                "oac_name = %s and oac_verified is true limit 1")
            self.rcur.execute(sql, (cid, cdg_name))
            for r in self.rcur.fetchall():
                cdg_id = r[0]

        sql = ("insert into rw_song_oa_cat (oac_id, song_id) values (%s, %s)")
        self.rcur.execute(sql, (cdg_id, song_id))

        song_info = self.get_song_info(song_id)
        return 0, song_info + (cdg_name,)

    def connect(self):
        if not psycopg2:
            raise RainwaveDatabaseUnavailableError("No psycopg2 available.")
        psql_conn_args = []
        psql_conn_args.append(self.config.get("db:name"))
        psql_conn_args.append(self.config.get("db:user"))
        psql_conn_args.append(self.config.get("db:pass"))

        connstr = "dbname='%s' user='%s' password='%s'" % tuple(psql_conn_args)
        try:
            self.rdbh = psycopg2.connect(connstr)
        except psycopg2.OperationalError:
            raise RainwaveDatabaseUnavailableError("Could not connect to DB.")

        autocommit = psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
        self.rdbh.set_isolation_level(autocommit)
        self.rcur = self.rdbh.cursor()

    def drop_album_from_all_cdgs(self, album_id):
        """Remove all songs in an album from all cooldown groups"""

        for song_id in self.get_album_songs(album_id):
            self.drop_song_from_all_cdgs(song_id)

        cid = self.get_album_cid(album_id)
        if cid is None:
            return 1, "Invalid album_id: %s" % album_id

        return 0, (cid, self.get_album_name(album_id))

    def drop_album_from_cdg_by_name(self, album_id, cdg_name):
        """Remove all songs in an album from a cooldown group"""

        for song_id in self.get_album_songs(album_id):
            self.drop_song_from_cdg_by_name(song_id, cdg_name)

        cid = self.get_album_cid(album_id)
        if cid is None:
            return 1, "Invalid album_id: %s" % album_id

        return 0, (cid, self.get_album_name(album_id), cdg_name)

    def drop_empty_cdgs(self):
        """Clean up the database by removing cooldown groups that contain
        no songs"""

        sql = ("delete from rw_oa_categories where oac_id in (select oac_id "
            "from rw_oa_categories left join rw_song_oa_cat using (oac_id) "
            "where song_id is null)")
        self.rcur.execute(sql)

    def drop_song_from_all_cdgs(self, song_id):
        """Remove a song from all cooldown groups"""

        cid = self.get_song_cid(song_id)

        if cid is None:
            return 1, "Invalid song_id: %s" % song_id

        sql = ("delete from rw_song_oa_cat where song_id = %s")
        self.rcur.execute(sql, (song_id,))

        self.drop_empty_cdgs()

        return 0, self.get_song_info(song_id)

    def drop_song_from_cdg_by_name(self, song_id, cdg_name):
        """Remove a song from a cooldown group"""

        cid = self.get_song_cid(song_id)

        if cid is None:
            return 1, "Invalid song_id: %s" % song_id

        for cdg_id in self.get_cdg_id(cid, cdg_name):
            sql = ("delete from rw_song_oa_cat where song_id = %s and "
                "oac_id = %s")
            self.rcur.execute(sql, (song_id, cdg_id))

        self.drop_empty_cdgs()

        song_info = self.get_song_info(song_id)
        return 0, song_info + (cdg_name,)

    def get_album_cid(self, album_id):
        """Returns the channel id for given album"""

        sql = "select sid from rw_albums where album_id = %s"
        self.rcur.execute(sql, (album_id,))
        for r in self.rcur.fetchall():
            return r[0]
        return None

    def get_album_name(self, album_id):
        """Return the name of the album"""

        sql = "select album_name from rw_albums where album_id = %s"
        self.rcur.execute(sql, (album_id,))
        for r in self.rcur.fetchall():
            return r[0]
        return None

    def get_album_songs(self, album_id):
        """Yields song_ids in an album"""

        sql = ("select song_id from rw_songs where album_id = %s and "
            "song_verified is true")
        self.rcur.execute(sql, (album_id,))
        for r in self.rcur.fetchall():
            yield r[0]

    def get_cdg_id(self, cid, cdg_name):
        """Given a channel id and cooldown group name, get the cdg id"""

        sql = ("select oac_id from rw_oa_categories where sid = %s and "
            "oac_name = %s")
        self.rcur.execute(sql, (cid, cdg_name))
        for r in self.rcur.fetchall():
            yield r[0]

    def get_current_channel(self, uid):
        """Return id of channel that uid is currently listening to, or None"""

        cur_chan = None
        sql = ("select sid from rw_listeners where list_purge is false and "
            "user_id = %s")
        self.rcur.execute(sql, (uid,))
        rows = self.rcur.fetchall()
        for row in rows:
            cur_chan = row[0]
        return cur_chan

    def get_forum_post_info(self, post_id=None):
        """Return a string of information and a url for a forum post, default
        to the latest public post"""

        if post_id:
            sql = ("select forum_name, post_subject, username, post_id from "
                "phpbb_posts join phpbb_forums using (forum_id) join "
                "phpbb_users on (phpbb_posts.poster_id = phpbb_users.user_id) "
                "where post_id = %s")
            self.rcur.execute(sql, (post_id,))
        else:
            sql = ("select forum_name, post_subject, username, post_id from "
                "phpbb_posts join phpbb_forums using (forum_id) join "
                "phpbb_users on (phpbb_posts.poster_id = phpbb_users.user_id) "
                "join phpbb_acl_groups using (forum_id) where "
                "phpbb_acl_groups.group_id = 1 and auth_role_id != 16 order by "
                "post_time desc limit 1")
            self.rcur.execute(sql)

        rows = self.rcur.fetchall()
        for row in rows:
            url = ("http://rainwave.cc/forums/viewtopic.php?p=%s#p%s" %
                (row[3], row[3]))
            r = "%s / %s by %s" % (row[0], row[1], row[2])
            return r.decode("utf-8"), url

    def get_history(self, cid):
        """Yield information about the last several songs that played"""

        sql = ("select timestamp with time zone 'epoch' + sched_starttime * "
            "interval '1 second' as start, album_name, album_id, song_title, "
            "song_id from rw_schedule join rw_elections using (sched_id) join "
            "rw_songs using (song_id) join rw_albums using (album_id) where "
            "elec_position = 0 and sched_used > 0 and rw_songs.sid = %s order "
            "by start desc limit 12")
        self.rcur.execute(sql, (cid,))
        for r in self.rcur.fetchall():
            yield r

    def get_id_for_nick(self, nick):
        """Return user_id if this nick is a registered Rainwave account."""
        user_id = None
        sql = "select user_id from phpbb_users where username = %s"
        self.rcur.execute(sql, (nick,))
        rows = self.rcur.fetchall()
        for r in rows:
            user_id = r[0]
        return user_id

    def get_listener_chart_data(self, days):
        """Yields (cid, guest_count, registered_count) tuples over the range."""
        sql = ("select sid, extract(hour from timestamp with time zone "
            "'epoch' + lstats_time * interval '1 second') as hour, "
            "round(avg(lstats_guests), 2), round(avg(lstats_regd), 2) from "
            "rw_listenerstats where lstats_time > extract(epoch from "
            "current_timestamp) - %s group by hour, sid order by sid, hour")
        seconds = 86400 * days
        self.rcur.execute(sql, (seconds,))
        rows = self.rcur.fetchall()
        for row in rows:
            yield row[0], row[2], row[3]

    def get_listener_stats(self, cid):
        """Return (registered user count, guest count) for the station."""
        regd = 0
        guest = 0

        sql = "select sid, user_id from rw_listeners where list_purge is false"
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
        """Return id of latest public forum post"""
        post_id = 0
        sql = ("select max(post_id) from phpbb_posts join phpbb_acl_groups "
            "using (forum_id) where group_id = 1 and auth_role_id != 16")
        self.rcur.execute(sql)
        rows = self.rcur.fetchall()
        for row in rows:
            post_id = row[0]
        return post_id

    def get_max_song_id(self, cid):
        """Return song_id of newest song on a channel"""
        song_id = 0
        sql = ("select max(song_id) from rw_songs where song_verified is true "
            "and sid = %s")
        self.rcur.execute(sql, (cid,))
        rows = self.rcur.fetchall()
        for row in rows:
            song_id = row[0]
        return song_id

    def get_new_song_info(self, cid):
        """Return a list of tuples (song_info, url) for new songs on this
        channel up to three"""

        rs = []
        maxid = self.config.get("maxid:%s" % cid)
        sql = ("select song_id, album_name, song_title, song_url from rw_songs "
            "join rw_albums using (album_id) where song_id > %s and "
            "song_verified is true and rw_songs.sid = %s order by song_id desc "
            "limit 3")
        self.rcur.execute(sql, (maxid, cid))
        rows = self.rcur.fetchall()
        for row in rows:
            r = "%s / %s by " % (row[1], row[2])
            artists = []
            sql = ("select artist_name from rw_song_artist join rw_artists "
                "using (artist_id) where song_id = %s")
            self.rcur.execute(sql, (row[0],))
            arows = self.rcur.fetchall()
            for arow in arows:
                artists.append(arow[0])
            r += ", ".join(artists)
            rs.append((r.decode("utf-8"), row[3]))
        return rs

    def get_pending_refresh_jobs(self):
        """Return a list of channel ids that have a pending playlist refresh
        job"""

        cids = []
        sql = "select sid from rw_commands where command_return = 0"
        self.rcur.execute(sql)
        for row in self.rcur.fetchall():
            cids.extend(row)

        return cids

    def get_radio_stats(self, cid):
        """Return songs, albums, hours of music for one or all channel"""
        sql = ("select count(song_id), count(distinct album_id), "
            "round(sum(song_secondslong) / 3600.0, 2) from rw_songs where "
            "song_verified is true")
        if cid > 0:
            sql += " and sid = %s"
            self.rcur.execute(sql, (cid,))
        else:
            sql += " and sid < 5"
            self.rcur.execute(sql)
        rows = self.rcur.fetchall()
        for r in rows:
            return r[0], r[1], r[2]

    def get_running_refresh_jobs(self):
        """Return a list of channel codes that have a running playlist refresh
        job"""

        ccodes = []

        import subprocess
        ps_cmd = ["ps","-A","-o","ni,args"]
        p = subprocess.Popen(ps_cmd, stdout=subprocess.PIPE)
        ps_out_str = p.communicate()[0]
        ps_out_list = ps_out_str.splitlines()
        for ps_out in ps_out_list:
            ps_out = ps_out.strip()
            ps_out_tokens = ps_out.split()
            if (ps_out_tokens[0] == "10") and ("orpheus-" in ps_out_tokens[1]):
                index = ps_out_tokens[1].find("orpheus-")
                channel_code = ps_out_tokens[1][index + 8:]
                ccodes.append(channel_code)

        return ccodes

    def get_song_cdg_ids(self, song_id):
        """Get ids of all cooldown groups a particular song is in"""

        sql = "select oac_id from rw_song_oa_cat where song_id = %s"
        self.rcur.execute(sql, (song_id,))
        for r in self.rcur.fetchall():
            yield r[0]

    def get_song_cid(self, song_id):
        """Returns the channel id for given song"""

        sql = ("select sid from rw_songs where song_id = %s and song_verified "
            "is true")
        self.rcur.execute(sql, (song_id,))
        for r in self.rcur.fetchall():
            return r[0]
        return None

    def get_song_info(self, song_id):
        """Return a tuple (cid, album_name, song_title) for the given song_id"""

        sql = ("select rw_songs.sid, album_name, song_title from rw_songs join "
            "rw_albums using (album_id) where song_id = %s")
        self.rcur.execute(sql, (song_id,))
        for r in self.rcur.fetchall():
            return r

    def get_unrated_songs(self, user_id, cid, num=None):
        """Get unrated songs

        Returns: a list of tuples (cid, message)"""

        log.info("Getting unrated songs for user %s on channel %s with "
            "limit %s" % (user_id, cid, num))
        rs = []

       # Get list of albums that have available unrated songs

        albums_unrated_available = []
        sql = ("select distinct album_id from rw_songs left join (select "
            "user_id, song_rating_id, song_rating from rw_songratings where "
            "user_id = %s) as r using (song_rating_id) where song_verified is "
            "true and song_available is true and song_rating is null")
        if cid > 0:
            sql += " and sid = %s"
            self.rcur.execute(sql, (user_id, cid))
        else:
            sql += " and sid < 5"
            self.rcur.execute(sql, (user_id,))
        for r in self.rcur:
            albums_unrated_available.append(r[0])

       # Get list of albums that have unavailable unrated songs, exclude any
       # albums already in the first list

        albums_unrated_unavailable = []
        sql = ("select album_id, min(song_releasetime) as rt from rw_songs "
            "left join (select user_id, song_rating_id, song_rating from "
            "rw_songratings where user_id = %s) as r using (song_rating_id) "
            "where song_verified is true and song_available is false and "
            "song_rating is null")
        if cid > 0:
            sql += " and sid = %s"
        else:
            sql += " and sid < 5"
        for a in albums_unrated_available:
            sql += " and album_id != %s"
        sql += " group by album_id order by rt desc"
        if cid > 0:
            params = [user_id, cid]
        else:
            params = [user_id]
        params.extend(albums_unrated_available)
        self.rcur.execute(sql, tuple(params))
        for r in self.rcur:
            albums_unrated_unavailable.append(r[0])

        # If everything has been rated, bail out now

        if len(albums_unrated_available) + len(albums_unrated_unavailable) == 0:
            rs.append((cid, "No unrated songs."))
            return(rs)

        # The number of songs returned cannot exceed the number requested or the
        # maximum allowed

        limit = min(num, int(self.config.get("maxlength:unrated")))

        while limit > 0:

            # Report available songs first

            if len(albums_unrated_available) > 0:
                aa = albums_unrated_available.pop()
                sql = ("select rw_songs.sid, album_name, song_title, song_id "
                    "from rw_songs left join (select user_id, song_rating_id, "
                    "song_rating from rw_songratings where user_id = %s) as r "
                    "using (song_rating_id) join rw_albums using (album_id) "
                    "where song_verified is true and song_available is true "
                    "and song_rating is null and album_id = %s")
                if cid > 0:
                    sql += " and rw_songs.sid = %s"
                else:
                    sql += " and rw_songs.sid < 6"
                sql += " order by song_releasetime limit 1"
                if cid > 0:
                    self.rcur.execute(sql, (user_id, aa, cid))
                else:
                    self.rcur.execute(sql, (user_id, aa))
                rows = self.rcur.fetchall()
                for row in rows:
                    rs.append((row[0], "%s / %s [%s]" % row[1:]))

            elif len(albums_unrated_unavailable) > 0:
                au = albums_unrated_unavailable.pop()
                sql = ("select rw_songs.sid, album_name, song_title, song_id, "
                    "(song_releasetime - extract(epoch from "
                    "current_timestamp)::integer) * interval '1 second' from "
                    "rw_songs left join (select user_id, song_rating_id, "
                    "song_rating from rw_songratings where user_id = %s) as r "
                    "using (song_rating_id) join rw_albums using (album_id) "
                    "where song_verified is true and song_available is false "
                    "and song_rating is null and album_id = %s")
                if cid > 0:
                    sql += " and rw_songs.sid = %s"
                else:
                    sql += " and rw_songs.sid < 6"
                sql += " order by song_releasetime limit 1"
                if cid > 0:
                    self.rcur.execute(sql, (user_id, au, cid))
                else:
                    self.rcur.execute(sql, (user_id, au))
                rows = self.rcur.fetchall()
                for row in rows:
                    rs.append((row[0], "%s / %s [%s] (available in %s)" %
                        row[1:]))

            else:
                rs.append((cid, "No more albums with unrated songs."))
                return(rs)

            limit -= 1

        # How many albums were not specifically reported?

        albums_left = (len(albums_unrated_available) +
            len(albums_unrated_unavailable))

        if albums_left > 0:
            r = "%s more album" % albums_left
            if albums_left > 1:
                r += "s"
            r += " with unrated songs."
            rs.append((cid, r))

        return rs

    def request_playlist_refresh(self, cid):
        """Request a playlist refresh for a channel"""

        # If a playlist refresh is already pending, do not request a new one
        pending = self.get_pending_refresh_jobs()
        if cid in pending:
            pass
        else:
            sql = "insert into rw_commands (sid, command_name) values (%s, %s)"
            self.rcur.execute(sql, (int(cid), "regenplaylist"))
        return

    def search_songs(self, cid, text, limit=10):
        """Search for songs by title.

        Returns:
            the tuple ([song dicts], unreported results), where:
                a song dict is: {
                    "album_name": string
                    "song_title": string
                    "song_id": string
                }
                unreported results: int, number of results over the limit.
        """
        sql = ("select album_name, song_title, song_id from rw_songs join "
            "rw_albums using (album_id) where song_verified is true and "
            "rw_songs.sid = %s and song_title ilike %s order by "
            "album_name, song_title")
        self.rcur.execute(sql, (cid, "%%%s%%" % text))
        rows = self.rcur.fetchall()
        results = []
        for row in rows[:limit]:
            results.append({
                "album_name": row[0], "song_title": row[1], "song_id": row[2]})
        unreported_results = max(len(rows) - limit, 0)
        return results, unreported_results

    def search_albums(self, cid, text, limit=10):
        """Search for albums by title.

        Returns:
            the tuple ([album dicts], unreported results), where:
                an album dict is: {
                    "album_name": string
                    "album_id": string
                }
                unreported results: int, number of results over the limit.
        """
        sql = ("select album_name, album_id from rw_albums where "
            "album_verified is true and sid = %s and album_name ilike %s "
            "order by album_name")
        self.rcur.execute(sql, (cid, "%%%s%%" % text))
        rows = self.rcur.fetchall()
        results = []
        for row in rows[:limit]:
            results.append({"album_name": row[0], "album_id": row[1]})
        unreported_results = max(len(rows) - limit, 0)
        return results, unreported_results
