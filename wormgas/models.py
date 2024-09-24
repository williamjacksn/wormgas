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

    def migrate(self):
        if self.version < 1:
            self.log.info('Migrating to database schema version 1')
            self.u('''
                create table schema_versions (
                    schema_version int,
                    migration_applied_at text
                ) strict
            ''')
            self.version = 1

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
