import dkim
import quopri

from email.message import EmailMessage

from utils import gen_token

class MailComposer:
    
    def __init__(self, name, user, domain, to: str, cc = [], bcc = [], subject = None, content = None):
        self.message = EmailMessage()
        self._subj = subject
        self._cont = content.strip() if content else ''
        self.message.add_header("From", f'{name} <{user}@{domain}>')
        self.message.add_header("To", to)
        self.message.add_header("Message-ID", f"<{gen_token(10)}@{domain}>")
        if subject:
            self.message.add_header("Subject", subject)
        self._bds = [gen_token(5)]
        self.message.add_header("Content-Type", "multipart/alternative", boundary=f'{self._bds[0]}')
        self.content = None
        self.html = None
        if content:
            self.set_content(self._cont)

    def set_content(self, content: str):
        if content:
            self._cont = content.strip()
            self.content = EmailMessage()
            self.content.add_header("Content-Type", "text/plain", charset="UTF-8")
            self.content.add_header("Content-Transfer-Encoding", "quoted-printable")
            self.content.set_payload(quopri.encodestring(self._cont.encode()).decode())
        self.message.attach(self.content)
        return self

    def set_html(self, content: 'str | None', watermark: bool = True):
        if content:
            self.html = EmailMessage()
            self.html.add_header("Content-Type", "text/html", charset="UTF-8")
            self.html.add_header("Content-Transfer-Encoding", "quoted-printable")
            self.html.set_payload(quopri.encodestring(
                ('''<div><div><div>''' + content + '''</div>''' + ('<br/><br/><div><p style="color:mediumpurple;margin:5px 0px;">Sent using Sputh Mail by Sayutel</p></div>' if watermark else '') + '</div></div>').encode()
            ).decode())
        self.message.attach(self.html)
        return self
    
    def sign(self, domain: str, selector: str, identity: 'str | None' = None):
        with open('/home/keys/key0/rsa.private', 'r') as keyfile:
            key = keyfile.read()
            sgn = dkim.sign(
                self.get_bytes(), 
                selector.encode(), 
                domain.encode(), 
                privkey = key.encode(), 
                identity = identity.encode() if identity else None,
                include_headers = [b'From', b'To', b'Message-ID'] + ([b'Subject'] if self._subj else []),
                linesep=b' '
            )
            self.message.add_header('DKIM-Signature', sgn[16:].decode())

    def get_bytes(self):
        return self.message.as_bytes()
    
    def get_str(self):
        return self.message.as_string()