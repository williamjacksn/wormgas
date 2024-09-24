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
