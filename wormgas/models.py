import datetime
import fort

class Database(fort.SQLiteDatabase):
    _version: int = None

    @property
    def version(self) -> int:
        if self._version is None:
            if self._table_exists('schema_versions'):
                sql = '''
                    select schema_version
                    from schema_versions
                    order by migration_applied_at desc
                    limit 1
                '''
                self._version = self.q_val(sql) or 0
            else:
                self._version = 0
        return self._version

    @version.setter
    def version(self, version: int):
        sql = '''
            insert into schema_versions (
                schema_version, migration_applied_at
            ) values (
                :schema_version, :migration_applied_at
            )
        '''
        params = {
            'migration_applied_at': datetime.datetime.now(tz=datetime.UTC).isoformat(),
            'schema_version': version,
        }
        self.u(sql, params)
        self._version = version

    def command_log_insert(self, discord_user_id: int, command: str, message: str):
        sql = '''
            insert into command_log (
                occurred_at, discord_user_id, command, message
            ) values (
                :occurred_at, :discord_user_id, :command, :message
            )
        '''
        params = {
            'occurred_at': datetime.datetime.now(tz=datetime.UTC).isoformat(),
            'discord_user_id': discord_user_id,
            'command': command,
            'message': message,
        }
        self.u(sql, params)

    def config_delete(self, key: str):
        sql = '''
            delete from config
            where key = :key
        '''
        params = {
            'key': key,
        }
        self.u(sql, params)

    def config_get(self, key: str) -> str:
        sql = '''
            select value from config where key = :key
        '''
        params = {
            'key': key,
        }
        return self.q_val(sql, params)

    def config_list_keys(self) -> list[str]:
        sql = '''
            select key
            from config
            order by key
        '''
        return [r['key'] for r in self.q(sql)]

    def config_set(self, key: str, value: str):
        sql = '''
            insert into config (key, value) values (:key, :value)
            on conflict (key) do update set value = excluded.value
        '''
        params = {
            'key': key,
            'value': value,
        }
        self.u(sql, params)

    def events_get(self, rw_event_id: int):
        sql = '''
            select rw_event_id, discord_event_id
            from events
            where rw_event_id = :rw_event_id
        '''
        params = {
            'rw_event_id': rw_event_id,
        }
        return self.q_one(sql, params)

    def events_insert(self, rw_event_id: int, discord_event_id: int):
        sql = '''
            insert into events (rw_event_id, discord_event_id) values (:rw_event_id, :discord_event_id)
        '''
        params = {
            'rw_event_id': rw_event_id,
            'discord_event_id': discord_event_id,
        }
        self.u(sql, params)

    def migrate(self):
        self.log.info(f'Database schema version is {self.version}')
        if self.version < 1:
            self.log.info('Migrating to database schema version 1')
            self.u('''
                create table schema_versions (
                    schema_version int,
                    migration_applied_at text
                )
            ''')
            self.version = 1
        if self.version < 2:
            self.log.info('Migrating to database schema version 2')
            self.u('''
                create table config (
                    key text primary key,
                    value text
                )
            ''')
            self.version = 2
        if self.version < 3:
            self.log.info('Migrating to database schema version 3')
            self.u('''
                create table rps_stats (
                    user_id text primary key,
                    rock int default 0,
                    paper int default 0,
                    scissors int default 0,
                    wins int default 0,
                    draws int default 0,
                    losses int default 0,
                    reset_code text
                )
            ''')
            self.version = 3
        if self.version < 4:
            self.log.info('Migrating to database schema version 4')
            self.u('''
                create table topic_control (
                    channel_id text
                )
            ''')
            self.version = 4
        if self.version < 5:
            self.log.info('Migrating to database schema version 5')
            self.u('''
                create table rw_api_keys (
                    discord_user_id text primary key,
                    rw_api_key text
                )
            ''')
            self.version = 5
        if self.version < 6:
            self.log.info('Migrating to database schema version 6')
            self.u('''
                create table events (
                    rw_event_id integer primary key,
                    discord_event_id integer
                )
            ''')
            self.version = 6
        if self.version < 7:
            self.log.info('Migrating to database schema version 7')
            self.u('''
                create table command_log (
                    occurred_at text,
                    discord_user_id integer,
                    command text,
                    message text
                )
            ''')
            self.version = 7

    def rps_delete(self, user_id: str):
        sql = '''
            delete from rps_stats
            where user_id = :user_id
        '''
        params = {
            'user_id': user_id,
        }
        self.u(sql, params)

    def rps_get(self, user_id: str) -> dict:
        sql = '''
            select user_id, rock, paper, scissors, wins, draws, losses, reset_code
            from rps_stats
            where user_id = :user_id
        '''
        params = {
            'user_id': user_id,
        }
        r = self.q_one(sql, params)
        if r:
            return {
                'user_id': r['user_id'],
                'rock': r['rock'],
                'paper': r['paper'],
                'scissors': r['scissors'],
                'wins': r['wins'],
                'draws': r['draws'],
                'losses': r['losses'],
                'reset_code': r['reset_code'],
            }
        return {
            'user_id': user_id
        }

    def rps_set(self, params: dict):
        sql = '''
            insert into rps_stats (
                user_id, rock, paper, scissors, wins, draws, losses, reset_code
            ) values (
                :user_id, :rock, :paper, :scissors, :wins, :draws, :losses, :reset_code
            ) on conflict (user_id) do update set
                rock = excluded.rock, paper = excluded.paper, scissors = excluded.scissors, wins = excluded.wins,
                draws = excluded.draws, losses = excluded.losses, reset_code = excluded.reset_code
        '''
        for key in ('rock', 'paper', 'scissors', 'wins', 'draws', 'losses'):
            if key not in params:
                params[key] = 0
        if 'reset_code' not in params:
            params['reset_code'] = None
        self.u(sql, params)

    def rw_api_keys_delete(self, discord_user_id: int):
        sql = '''
            delete from rw_api_keys
            where discord_user_id = :discord_user_id
        '''
        params = {
            'discord_user_id': str(discord_user_id),
        }
        self.u(sql, params)

    def rw_api_keys_get(self, discord_user_id: int):
        sql = '''
            select rw_api_key
            from rw_api_keys
            where discord_user_id = :discord_user_id
        '''
        params = {
            'discord_user_id': str(discord_user_id),
        }
        return self.q_val(sql, params)

    def rw_api_keys_set(self, discord_user_id: int, rw_api_key: str):
        sql = '''
            insert into rw_api_keys (
                discord_user_id, rw_api_key
            ) values (
                :discord_user_id, :rw_api_key
            ) on conflict (discord_user_id) do update set
                rw_api_key = excluded.rw_api_key
        '''
        params = {
            'discord_user_id': str(discord_user_id),
            'rw_api_key': rw_api_key,
        }
        self.u(sql, params)

    def topic_control_delete(self, channel_id: str):
        sql = '''
            delete from topic_control
            where channel_id = :channel_id
        '''
        params = {
            'channel_id': channel_id,
        }
        self.u(sql, params)

    def topic_control_insert(self, channel_id: str):
        sql = '''
            insert into topic_control (channel_id) values (:channel_id)
        '''
        params = {
            'channel_id': channel_id,
        }
        self.u(sql, params)

    def topic_control_list(self) -> list[int]:
        sql = '''
            select distinct channel_id
            from topic_control
        '''
        return [int(r['channel_id']) for r in self.q(sql)]

    def _table_exists(self, table_name):
        sql = '''
            select name
            from sqlite_master
            where type = 'table'
                and name = :name
        '''
        params = {
            'name': table_name,
        }
        t = self.q_val(sql, params)
        if t and t == table_name:
            return True
        return False
