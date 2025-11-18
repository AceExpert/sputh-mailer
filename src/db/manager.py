import sqlite3
import re
import quopri
import base64
import os

from typing import Any
from datetime import datetime
from dataclasses import dataclass
from email.message import EmailMessage, Message
from email.parser import BytesParser
from ws import Object

from models import EmailDB, AttachmentDB
from utils import get_folder_path, get_name_from_header, get_email, gen_token

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
    raw: bytes = None
    mail_id: str = None

    @classmethod
    def from_mail(cls, data):
        return dict(
            index = data[0], from_addr = data[1], to_addr = data[2], to_real = data[3], subject = data[4],
            date = data[5], message_id = data[6], return_path = data[7], sign = data[8], body = data[9],
            from_name = SimpleEmail.resolve_name(data[1]),
            to_name = SimpleEmail.resolve_name(data[2]),
            domain = data[7].split('@')[1],
            mail_id = data[12],
            is_tls = data[13],
            extras = SimpleEmail.get_extras(data[11]),
            attachments = [*map(SimpleEmail.from_attachment, data[14])] if data[14] else []
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
    
    @classmethod
    def from_attachment(cls, data):
        return dict(
            attachment_id = data[1],
            content_type = data[3],
            content_transfer = data[4],
            content_id = data[5],
            filename = data[6],
            folder = data[7],
            size = data[8]
        )
    
    @classmethod
    def get_extras(cls, raw_data: bytes):
        extras = {}
        mail = BytesParser().parsebytes(raw_data, True)
        extras['references'] = mail.get("references")
        extras['in_reply_to'] = mail.get("in-reply-to")
        return extras 
        
@dataclass
class SimpleEmailBody:
    content_type: str
    content_transfer: str
    content: str

@dataclass
class Attachment:
    content_type: str
    content_transfer: str
    content_id: str
    name: str
    filename: str
    data: str
    a_id: str
    size: int
    raw_data: bytes = None

class EmailManager:
    
    def __init__(self, user: str):
        self.user = user
        self.folders = Object({
            'inbox': EmailDB(get_folder_path(user, 'inbox')),
            'sent': EmailDB(get_folder_path(user, 'sent')),
            'draft': EmailDB(get_folder_path(user, 'draft')),
            'spam': EmailDB(get_folder_path(user, 'spam')),
            'bin': EmailDB(get_folder_path(user, 'bin')),
            'attachments': AttachmentDB(get_folder_path(user, 'inbox', True) + 'attachments.db'),
        })
        self.email_parser = BytesParser()

    def add_raw_mail(self, folder: str, mail_data: bytes, return_path: str, to_real: str, is_tls: bool = True, parsed_mail: Message = None):
        mail = parsed_mail or self.email_parser.parsebytes(mail_data)
        return self.add_mail(folder, mail, return_path, to_real, is_tls)

    def to_readable_content(self, body: SimpleEmailBody):
        fbody = body.content

        if body.content_transfer:
            if body.content_transfer.lower() == 'quoted-printable':
                fbody = quopri.decodestring(body.content).decode()
            elif body.content_transfer.lower() == 'base64':
                fbody = base64.b64decode(body.content).decode()
            else:
                fbody = body.content
        else:
            fbody = body.content

        return fbody

    def add_mail(self, folder: str, mail: EmailMessage, return_path: str, to_real: str, is_tls: bool = True):
        bodies = []
        attachments: list[Attachment] = self.get_attachments(mail)
        self.get_body(mail, bodies)
        
        fbody: str = None
        
        for body in bodies:
            if body.content_type == 'text/html':
                fbody = self.to_readable_content(body)
                break

        if not fbody and bodies:
            fbody = self.to_readable_content(bodies[0])

        mail_id: str = gen_token(10)

        insert_data: tuple = (self.folders[folder].count() + 1, 
            mail.get('From', None), mail.get('To', None), to_real,
            mail.get("Subject", None), mail.get("Date", None), mail.get("Message-ID", None), 
            return_path, ", ".join(self.get_sign(mail)), fbody, ",".join(map(lambda a: a.a_id, attachments)), mail.as_bytes(), mail_id, is_tls
        )

        cursor: sqlite3.Cursor = self.folders[folder].cursor
        cursor.execute(
            """INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""", 
            insert_data
        )
        self.folders[folder].db.commit()
        self.folders[folder]._count += 1

        attach_folder_path = get_folder_path(self.user, 'inbox', True)

        compl_data = (*insert_data, [])

        if attachments:
            os.mkdir(attach_folder_path + mail_id)

        for att in attachments:
            f = open(attach_folder_path + mail_id + '/' + att.a_id, 'wb')
            f.write(att.raw_data)
            f.close()

            attach_ins_data: tuple = (
                self.folders['attachments'].total_count() + 1, att.a_id, mail_id, 
                att.content_type, att.content_transfer, att.content_id, 
                att.filename, folder, att.size
            )

            cursor: sqlite3.Cursor = self.folders['attachments'].cursor
            cursor.execute(
                """INSERT INTO attachments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                attach_ins_data
            )
            self.folders['attachments'].db.commit()
            self.folders['attachments']._count += 1

            compl_data[14].append(attach_ins_data)

        return compl_data
    
    def get_mails(self, folder: str, limit: int = 50, offset: int = 0):
        data = self.folders[folder].cursor.execute(
            """SELECT * from emails ORDER BY srno DESC LIMIT ? OFFSET ?;""", (50, 0)
        ).fetchall()

        new_data = []

        for mail in data:
            ins_tup = (*mail, [])
            for att in self.folders['attachments'].get_attachments(mail[12]):
                ins_tup[14].append((0, att[0], mail[12], att[1], att[2], att[3], att[4], att[5], att[7]))
            new_data.append(ins_tup)

        return [*map(SimpleEmail.from_mail, new_data)]

    def get_sign(self, email: EmailMessage):
        _sign_doms = []
        for signs in email.get_all('DKIM-Signature'):
            dom = re.findall(r"[\s\n\t]d=(.+?);?[\s\n\t]", ' '+signs+' ')
            if dom:
                _sign_doms.append(dom[0].strip())

        return _sign_doms
    
    def get_body(self, email: EmailMessage, _bodies: list[SimpleEmailBody] = []) -> list[SimpleEmailBody]:
        bodies: list[SimpleEmailBody] = _bodies
        if not isinstance(email, (EmailMessage, Message)): return
        if email.get_content_type() not in ['text/plain', 'text/html']:
            if payl := email.get_payload():
                if type(payl) == list:
                    for payload in payl:
                        self.get_body(payload, bodies)
                else:
                    self.get_body(payl, bodies)
        
        else:
            bodies.append(SimpleEmailBody(
                    content = email.get_payload() if email.get_payload() else None,
                    content_type = email.get_content_type(),
                    content_transfer = email.get('Content-Transfer-Encoding', None)
                )
            )

    def get_attachments(self, email: EmailMessage):
        attach: list[Attachment] = []
        if not isinstance(email, (EmailMessage, Message)): return attach
        if not email.get_content_disposition() or email.get_content_disposition().lower() != 'attachment':
            if payl := email.get_payload():
                if type(payl) == list:
                    for payload in payl:
                        for a in self.get_attachments(payload):
                            attach.append(a)
                else:
                    for a in self.get_attachments(payl):
                        attach.append(a)
            return attach
        
        else:
            attachment = Attachment(
                content_type = email.get_content_type(),
                content_transfer = email.get('Content-Transfer-Encoding', None),
                content_id = email.get('Content-ID', None),
                filename = email.get_filename(),
                name = email.get_filename(),
                data = email.get_payload(),
                raw_data = email.get_payload(decode = True),
                a_id = gen_token(10),
                size = None
            )
            
            '''
            if email.get_payload() and attachment.content_transfer:
                if attachment.content_transfer.lower() == 'base64':
                    attachment.raw_data = base64.b64decode(email.get_payload())
                elif attachment.content_transfer.lower() == 'quoted-printable':
                    attachment.raw_data = quopri.decodestring(email.get_payload())
            '''

            attachment.size = len(attachment.raw_data)
            email.set_payload(None)

            attach.append(attachment)
            return attach