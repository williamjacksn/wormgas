from setuptools import find_packages, setup

setup(
    name='wormgas',
    version='2.0.3',
    author='William Jackson',
    author_email='william@subtlecoolness.com',
    url='https://github.com/williamjacksn/wormgas',
    description='Wonderfully Optimistic Rainwave Music Guide and Automated Servant',
    license='MIT License',
    packages=find_packages(),
    install_requires=['aiohttp>=2.0.0,<2.3.0', 'discord.py', 'pytz', 'stemming', 'wikipedia'],
    entry_points={
        'console_scripts': [
            'wormgas = wormgas.wormgas:main'
        ]
    }
)
