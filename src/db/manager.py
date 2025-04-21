import sqlite3
import re

from typing import Any
from datetime import datetime
from dataclasses import dataclass
from email.message import EmailMessage
from email.parser import BytesParser
from ws import Object

from models import EmailDB
from utils import get_folder_path, get_name_from_header, get_email

@dataclass
class SimpleEmail:
    from_name: str
    from_addr: str
    to_name: str
    to_addr: str
    return_path: str
    to_real: str
    message_id: str
    index: int
    sign: str
    subject: str = None
    date: datetime = None
    attachments: list[Any] = None
    body: str = None

    @classmethod
    def from_mail(cls, data):
        return dict(
            index = data[0], from_addr = data[1], to_addr = data[2], to_real = data[3], subject = data[4],
            date = data[5], message_id = data[6], return_path = data[7], sign = data[8], body = data[9],
            from_name = SimpleEmail.resolve_name(data[1]),
            to_name = SimpleEmail.resolve_name(data[2]),
            domain = data[7].split('@')[1]
        )
    
    @classmethod
    def resolve_name(cls, header):
        from_name = get_name_from_header(header) or get_email(header)
        if isinstance(from_name, list):
            if from_name:
                from_name = from_name[0].split('@')[0]
            else:
                from_name = ''
        return from_name
        
@dataclass
class SimpleEmailBody:
    content_type: str
    content_transfer: str
    content: str

class EmailManager:
    
    def __init__(self, user: str):
        self.user = user
        self.folders = Object({
            'inbox': EmailDB(get_folder_path(user, 'inbox')),
            'sent': EmailDB(get_folder_path(user, 'sent')),
            'draft': EmailDB(get_folder_path(user, 'draft')),
            'spam': EmailDB(get_folder_path(user, 'spam')),
            'bin': EmailDB(get_folder_path(user, 'bin')),
        })
        self.email_parser = BytesParser()

    def add_mail(self, folder: str, mail: EmailMessage, return_path: str, to_real: str):
        bodies = []
        self.get_body(mail, bodies)
        fbody: str = None
        
        for body in bodies:
            if body.content_type == 'text/html':
                fbody = body.content
                break

        if not fbody and bodies:
            fbody = bodies[0].content

        cursor: sqlite3.Cursor = self.folders[folder].cursor
        cursor.execute(
            """INSERT INTO table VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""", 
            (self.folders[folder].count() + 1, 
             mail.get('From', None), mail.get('To', None), to_real,
             mail.get("Subject", None), mail.get("Date", None), mail.get("Message-ID", None), 
             return_path, ", ".join(self.get_sign(mail)), fbody, None, mail.as_bytes()
             )
        )
        self.folders[folder].db.commit()
        self.folders[folder]._count += 1
    
    def get_mails(self, folder: str, limit: int = 50, offset: int = 0):
        data = self.folders[folder].cursor.execute(
            """SELECT * from emails ORDER BY srno DESC LIMIT ? OFFSET ?;""", (50, 0)
        ).fetchall()

        return [*map(SimpleEmail.from_mail, data)]

    def get_sign(self, email: EmailMessage):
        _sign_doms = []
        for signs in email.get_all('DKIM-Signature'):
            dom = re.findall(r"[\s\n\t]d=(.+?);?[\s\n\t]", ' '+signs+' ')
            if dom:
                _sign_doms.append(dom[0].strip())

        return _sign_doms
    
    def get_body(self, email: EmailMessage, _bodies: list[SimpleEmailBody] = []) -> list[SimpleEmailBody]:
        bodies: list[SimpleEmailBody] = _bodies
        if email.get_content_type() not in ['text/plain', 'text/html']:
            for payload in email.get_payload():
                self.get_body(payload, bodies)
        
        else:
            bodies.append(SimpleEmailBody(
                    content = email.get_payload()[-1] if email.get_payload() else None,
                    content_type = email.get_content_type(),
                    content_transfer = email.get('Content-Transfer-Encoding', None)
                )
            )