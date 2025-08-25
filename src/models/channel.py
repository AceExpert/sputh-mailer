import sqlite3

from dataclasses import dataclass
from typing import Any

@dataclass
class Channel:
    client: Any = None
    user: str = None
    session_token: str = None
    auth: bool = False
    pub_key: bytes = None
    current_key: bytes = None
    stale_timer: None = None
    hb_timer: None = None
    info = None
    manager: Any = None

@dataclass
class DnsRecord:
    host: str
    value: str
    label: str
    priority: int
    ttl: int

class EmailDB:
    db: sqlite3.Connection = None
    cursor: sqlite3.Cursor = None

    def __init__(self, path: str = None, make_table: bool = True):
        self.db = sqlite3.connect(path)
        self.cursor = self.db.cursor()
        self.table_exists = False
        self.path = path
        self._count = None
        if make_table:
            self.check_table()
            self.count()

    def check_table(self):
        self.cursor.execute("CREATE TABLE IF NOT EXISTS emails(srno, from_addr, to_addr, to_real, subject, date, message_id, return_path, sign, body, attachments, raw, m_id, is_tls);")
        self.table_exists = True

    def count(self):
        if self._count is None:
            (self._count,) = self.cursor.execute("SELECT COUNT(*) from emails;").fetchone();
        return self._count
    
class AttachmentDB:
    db: sqlite3.Connection = None
    cursor: sqlite3.Cursor = None

    def __init__(self, path: str = None, make_table: bool = True):
        self.db = sqlite3.connect(path)
        self.cursor = self.db.cursor()
        self.table_exists = False
        self.path = path
        self._count = None
        self.count_cache: dict[str, int] = {}
        if make_table:
            self.check_table()
            self.total_count()

    def check_table(self):
        self.cursor.execute("CREATE TABLE IF NOT EXISTS attachments(srno, attachment_id, m_id, content_type, content_transfer, content_id, filename, folder, size);")
        self.table_exists = True

    def total_count(self):
        if self._count is None:
            (self._count,) = self.cursor.execute("SELECT COUNT(*) from attachments;").fetchone();
        return self._count
    
    def get_count(self, m_id: str):
        if cnt := self.count_cache.get(m_id, None):
            return cnt
        else:
            (self.count_cache[m_id],) = self.cursor.execute("SELECT COUNT(*) from attachments WHERE m_id=?;", (m_id,)).fetchone();
            return self.count_cache[m_id]
        
    def get_attachments(self, m_id: str):
        return self.cursor.execute("SELECT attachment_id, content_type, content_transfer, content_id, filename, folder, m_id, size FROM attachments WHERE m_id=?;", (m_id,)).fetchall()