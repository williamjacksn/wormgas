wormgas -- Discord bot for [Rainwave][]

wormgas is a command-processing Discord bot that enables using many Rainwave features from Discord. It requires Python
3.6.

The core bot requires the [discord.py][] library >= 1.0.0a (commonly known as `rewrite`). Some extensions do have other
dependencies:

*   The `chat` extension requires [stemming][]
*   The `rainwave` extension requires [pytz][]
*   The `wiki` plugin requires [wikipedia][]

The `chat` extension is powered by [cobe][], but this dependency is bundled.

[rainwave]: http://rainwave.cc
[stemming]: http://pypi.python.org/pypi/stemming
[discord.py]: https://github.com/Rapptz/discord.py/tree/rewrite
[pytz]: https://pypi.python.org/pypi/pytz
[wikipedia]: https://wikipedia.readthedocs.org/en/latest/
[cobe]: https://github.com/pteichman/cobe/
