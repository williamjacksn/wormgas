#!/usr/bin/python
"""
dbaccess -- wrapper around Rainwave and Config DB calls for wormgas
https://github.com/subtlecoolness/wormgas
"""

import sqlite3
import time
from os import path

_logpath = "%s.log" % path.splitext(path.abspath(__file__))[0]

def print_to_log(msg):
    """Print to the log file.

    Arguments:
        msg: string, the message to print to the log file (timestamp and
             newline are not required)"""

    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    with open(_logpath, "a") as logfile:
        logfile.write("%s -- %s\n" % (now, msg))

try:
    import psycopg2
except:
    psycopg2 = None
    print_to_log("[WARN] psycopg2 unavailable -- RW db access turned off.")

class Config(object):
    """Connects to, retrieves from, and sets values in the local sqlite db."""

    def __del__(self):
        try:
            self.cdbh.close()
        except AttributeError: pass # Never opened the db; no handle to close.

    def open(self, path):
        """Open local database for reading and writing."""
        connstr = "%s/config.sqlite" % path
        self.cdbh = sqlite3.connect(connstr, isolation_level=None)
        self.ccur = self.cdbh.cursor()

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
            mlcl = int(self.get("maxlength:configlist"))
            while len(cids) > mlcl:
                clist = cids[:mlcl]
                cids[0:mlcl] = []
                rs.append(", ".join(clist))
            rs.append(", ".join(cids))

        return(rs)

    def get(self, id):
        """Read a value from the configuration database.

        Arguments:
            id: the config_id that you want to read

        Returns: the config_value, or -1 if the config_id does not exist"""

        config_value = -1
        sql = "select config_value from botconfig where config_id = ?"
        self.ccur.execute(sql, (id,))
        for r in self.ccur:
            config_value = r[0]
        print_to_log("[INFO] get_config(): %s = %s" % (id, config_value))
        return(config_value)

    def set(self, id, value):
        """Set a configuration value in the database.

        Arguments:
            id: the config_id to set
            value: the value to set it to"""

        cur_config_value = self.get(id)
        if value in (-1, "-1"):
            sql = "delete from botconfig where config_id = ?"
            self.ccur.execute(sql, (id,))
        elif cur_config_value in (-1, "-1"):
            sql = ("insert into botconfig (config_id, config_value) values "
                "(?, ?)")
            self.ccur.execute(sql, (id, value))
        else:
            sql = "update botconfig set config_value = ? where config_id = ?"
            self.ccur.execute(sql, (value, id))
        print_to_log("[INFO] set_config: %s = %s" % (id, value))

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

    def add_id_to_nick(self, id, nick):
        sql = "update user_keys set user_id = ? where user_nick = ?"
        self.ccur.execute(sql, (id, nick))

    def drop_id_for_nick(self, nick):
        sql = "update user_keys set user_id = null where user_nick = ?"
        self.ccur.execute(sql, (nick,))

    def get_id_for_nick(self, nick):
        """Return stored Rainwave ID for nick, or None if no ID is stored."""
        stored_id = None
        sql = "select user_id from user_keys where user_nick = ?"
        self.ccur.execute(sql, (nick,))
        for r in self.ccur:
            stored_id = r[0]
        return stored_id

    def add_key_to_nick(self, key, nick):
        sql = "update user_keys set user_key = ? where user_nick = ?"
        self.ccur.execute(sql, (key, nick))

    def drop_key_for_nick(self, nick):
        sql = "update user_keys set user_key = null where user_nick = ?"
        self.ccur.execute(sql, (nick,))

    def get_key_for_nick(self, nick):
        """Return stored API key for nick, or None if no key is stored."""
        stored_id = None
        sql = "select user_key from user_keys where user_nick = ?"
        self.ccur.execute(sql, (nick,))
        for r in self.ccur:
            stored_id = r[0]
        return stored_id

    def log_rps(self, nick, challenge, response):
        """Record an RPS game in the database"""
        sql = ("insert into rps_log (timestamp, user_nick, challenge, "
            "response) values (datetime('now'), ?, ?, ?)")
        self.ccur.execute(sql, (nick, challenge, response))

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

    def reset_rps_record(self, nick):
        """Reset the RPS record and delete game history for nick"""
        sql = "delete from rps_log where user_nick = ?"
        self.ccur.execute(sql, (nick,))

    def get_rps_players(self):
        """Get all players in the RPS history"""
        players = []
        sql = "select distinct user_nick from rps_log order by user_nick"
        self.ccur.execute(sql)
        rows = self.ccur.fetchall()
        for r in rows:
            players.append(r[0])
        return players

class RainwaveDatabaseUnavailableError(IOError):
    """Raised if the Rainwave database or PostgreSQL module is missing."""

class RainwaveDatabase(object):
    """Calls Rainwave DB functions while managing the database handles."""

    def __init__(self, config):
        """Instantiate a RainwaveDatabase object.

        Args:
            config: dbaccess.Config, stores required connection params."""
        self.config = config

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

    def get_id_for_nick(self, nick):
        """Return user_id if this nick is a registered Rainwave account."""
        user_id = None
        sql = "select user_id from phpbb_users where username = %s"
        self.rcur.execute(sql, (nick,))
        rows = self.rcur.fetchall()
        for r in rows:
            user_id = r[0]
        return user_id

    def search_songs(self, sid, text, limit=10):
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
        self.rcur.execute(sql, (sid, "%%%s%%" % text))
        rows = self.rcur.fetchall()
        results = []
        for row in rows[:limit]:
            results.append({
                "album_name": row[0], "song_title": row[1], "song_id": row[2]})
        unreported_results = max(len(rows) - limit, 0)
        return results, unreported_results

    def search_albums(self, sid, text, limit=10):
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
        self.rcur.execute(sql, (sid, "%%%s%%" % text))
        rows = self.rcur.fetchall()
        results = []
        for row in rows[:limit]:
            results.append({"album_name": row[0], "album_id": row[1]})
        unreported_results = max(len(rows) - limit, 0)
        return results, unreported_results

    def get_listener_stats(self, sid):
        """Return (registered user count, guest count) for the station."""
        regd = 0
        guest = 0

        sql = "select sid, user_id from rw_listeners where list_purge is false"
        self.rcur.execute(sql)
        rows = self.rcur.fetchall()
        for row in rows:
            if sid in (0, row[0]):
                if row[1] > 1:
                    regd = regd + 1
                else:
                    guest = guest + 1
        return regd, guest

    def get_listener_chart_data(self, days):
        """Yields (sid, guest_count, registered_count) tuples over the range."""
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
