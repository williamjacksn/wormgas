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
