wormgas -- IRC bot for [Rainwave][]

wormgas is a command-processing IRC bot that enables using most Rainwave
features from within IRC. It requires Python 3.4.

There are no external dependencies for the core bot, but some plugins do have
dependencies:

*   The `chat` plugin requires [stemming][] >= 1.0
*   The `rainwave` and `wolframalpha` plugins require [requests][] >= 1.1.0
*   The `wiki` plugin requires [wikipedia][] >= 1.4.0

The `chat` plugin is powered by [cobe][], but this dependency is bundled.

[rainwave]: http://rainwave.cc
[stemming]: http://pypi.python.org/pypi/stemming
[requests]: http://docs.python-requests.org/en/latest/
[wikipedia]: https://wikipedia.readthedocs.org/en/latest/
[cobe]: https://github.com/pteichman/cobe/
