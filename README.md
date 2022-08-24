wormgas -- Discord bot for [Rainwave][]

wormgas is a command-processing Discord bot that enables using many Rainwave features from Discord. It requires Python
3.9 or higher.

The core bot requires the [discord.py][] library >= 2.0.0. Some extensions do have other dependencies:

*   The `chat` extension requires [stemming][]
*   The `wiki` plugin requires [wikipedia][]

The `chat` extension is powered by [cobe][], but this dependency is bundled.

[rainwave]: http://rainwave.cc
[discord.py]: https://pypi.org/project/discord.py/
[stemming]: http://pypi.python.org/pypi/stemming
[wikipedia]: https://wikipedia.readthedocs.org/en/latest/
[cobe]: https://github.com/pteichman/cobe/
