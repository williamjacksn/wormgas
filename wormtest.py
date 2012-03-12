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

    def testSetUp(self):
        """Ensure that merely constructing wormgas succeeds."""
        pass

    def test8BallPublic(self):
        output = wormgas.Output("public")
        self.wormgas.handle_8ball(self.nick, self.channel, output)
        self.assertEquals(len(output.rs), 1)
        self.assertTrue(output.rs[0] in wormgas.wormgas.answers_8ball)

    def test8BallPrivate(self):
        output = wormgas.Output("private")
        self.wormgas.handle_8ball(self.nick, wormgas.PRIVMSG, output)
        self.assertEquals(len(output.privrs), 1)
        self.assertTrue(output.privrs[0] in wormgas.wormgas.answers_8ball)

    def test8BallTimeout(self):
        timeout_set = False
        while not timeout_set:
            output = wormgas.Output("public")
            self.wormgas.handle_8ball(self.nick, self.channel, output)
            timeout_set = "again" not in output.rs[0]
        output = wormgas.Output("public")
        self.wormgas.handle_8ball(self.nick, self.channel, output)
        self.assertEquals(output.rs, [])
        self.assertEquals(len(output.privrs), 2)
        self.assertTrue(output.privrs[0] in wormgas.wormgas.answers_8ball)
        self.assertTrue("cooling down" in output.privrs[1])

if __name__ == "__main__":
    unittest.main()
