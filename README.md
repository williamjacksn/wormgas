wormgas -- IRC bot for [Rainwave][]

wormgas is a command-processing IRC bot that enables using most Rainwave
features from within IRC. It requires Python 3.4.

The core bot requires the [humphrey][] IRC library. Some plugins do have other
dependencies:

*   The `chat` plugin requires [stemming][] >= 1.0
*   The `rainwave` plugin requires [pytz][] >= 2016.4
*   The `wiki` plugin requires [wikipedia][] >= 1.4.0

The `chat` plugin is powered by [cobe][], but this dependency is bundled.

[rainwave]: http://rainwave.cc
[humphrey]: https://pypi.python.org/pypi/humphrey
[stemming]: http://pypi.python.org/pypi/stemming
[pytz][]: https://pypi.python.org/pypi/pytz
[wikipedia]: https://wikipedia.readthedocs.org/en/latest/
[cobe]: https://github.com/pteichman/cobe/
