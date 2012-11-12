#!/usr/bin/python
"""
Tests for wormgas.
https://github.com/subtlecoolness/wormgas
"""

import os
import unittest
import wormgas

class TestCommands(unittest.TestCase):
    config_db = "test.sqlite"
    nick = "TestNick"
    channel = "#testchannel"

    # In case setUp breaks, this will prevent the first test we run from
    # using an old test config DB.
    try:
        os.remove(config_db)
    except OSError:
        pass # Test DB doesn't exist, mission accomplished.

    def setUp(self):
        self.wormgas = wormgas.wormgas(config_db=self.config_db, log_file=None)

    def tearDown(self):
        self.wormgas.stop()
        os.remove(self.config_db)

    def test8BallPublic(self):
        output = wormgas.Output("public")
        self.wormgas.handle_8ball(self.nick, self.channel, output)
        self.assertEquals(len(output.rs), 1)
        self.assertTrue(output.rs[0] in wormgas.wormgas.answers_8ball)

    def test8BallPrivate(self):
        output = wormgas.Output("private")
        self.wormgas.handle_8ball(self.nick, wormgas.PRIVMSG, output)
        self.assertEquals(len(output.rs), 0)
        self.assertEquals(len(output.privrs), 1)
        self.assertTrue(output.privrs[0] in wormgas.wormgas.answers_8ball)

    def test8BallTimeout(self):
        # 8-Ball timeout is only set if the response doesn't say 'try again'.
        # Loop until we're sure.
        timeout_set = False
        while not timeout_set:
            output = wormgas.Output("public")
            self.wormgas.handle_8ball(self.nick, self.channel, output)
            timeout_set = "again" not in output.rs[0]

        # Cooldown is set, now test it.
        output = wormgas.Output("public")
        self.wormgas.handle_8ball(self.nick, self.channel, output)
        self.assertEquals(output.rs, [])
        self.assertEquals(len(output.privrs), 2)
        self.assertTrue(output.privrs[0] in wormgas.wormgas.answers_8ball)
        self.assertTrue("cooling down" in output.privrs[1])

    def testFlipPublic(self):
        output = wormgas.Output("public")
        self.wormgas.handle_flip(self.nick, self.channel, output)
        self.assertEquals(len(output.rs), 1)

    def testFlipPrivate(self):
        output = wormgas.Output("private")
        self.wormgas.handle_flip(self.nick, wormgas.PRIVMSG, output)
        self.assertEquals(len(output.rs), 0)
        self.assertEquals(len(output.privrs), 1)

    def testFlipTimeout(self):
        output = wormgas.Output("public")
        self.wormgas.handle_flip(self.nick, self.channel, output)
        # Cooldown is set, now test it.
        output = wormgas.Output("public")
        self.wormgas.handle_flip(self.nick, self.channel, output)
        self.assertEquals(output.rs, [])
        self.assertEquals(len(output.privrs), 2)
        self.assertTrue("cooling down" in output.privrs[1])

    def testSetNotAllowed(self):
        output = wormgas.Output("public")
        self.wormgas.handle_set(self.nick, self.channel, output,
            id="test:key", value="test:value")
        self.assertEquals(output.rs, [])
        self.assertEquals(self.wormgas.config.get("test:key"), None)

    def testSetNew(self):
        output = wormgas.Output("public")
        self.wormgas._is_admin = lambda nick: nick is self.nick
        self.wormgas.handle_set(self.nick, self.channel, output,
            id="test:key", value="test:value")
        self.assertEquals(output.rs, [])
        self.assertEquals(self.wormgas.config.get("test:key"), "test:value")

    def testSetExisting(self):
        output = wormgas.Output("public")
        self.wormgas._is_admin = lambda nick: nick is self.nick
        self.wormgas.config.set("test:key", "test:oldvalue")
        self.wormgas.handle_set(self.nick, self.channel, output,
            id="test:key", value="test:value")
        self.assertEquals(output.rs, [])
        self.assertEquals(self.wormgas.config.get("test:key"), "test:value")

    def testUnset(self):
        output = wormgas.Output("public")
        self.wormgas._is_admin = lambda nick: nick is self.nick
        self.wormgas.handle_unset(self.nick, self.channel, output,
            id="test:key")
        self.assertEquals(output.rs, [])
        self.assertEquals(self.wormgas.config.get("test:key"), None)

if __name__ == "__main__":
    unittest.main()
