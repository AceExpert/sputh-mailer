import dkim

from email.message import EmailMessage

from utils import gen_token

class MailComposer:
    
    def __init__(self, name, user, domain, to, cc = [], bcc = [], subject = None, content = None):
        self.message = EmailMessage()
        self._subj = subject
        self.message.add_header("From", f'{name} <{user}@{domain}>')
        self.message.add_header("To", f'{to.split("@")[0]} <{to}>')
        self.message
        if subject:
            self.message.add_header("Subject", subject)
        self._bds = [gen_token(5)]
        self.message.add_header("Content-Type", "multipart/alternative", boundary=f'"{self._bds[0]}"')
        self.content = None
        self.html = None
        if content:
            self.set_content(content)

    def set_content(self, content: str):
        if content:
            self.content = EmailMessage()
            self.content.add_header("Content-Type", "text/plain", charset="UTF-8")
            self.content.add_header("Content-Transfer-Encoding", "quoted-printable")
            self.content.set_payload(content)
        self.message.attach(self.content)
        return self

    def set_html(self, content: 'str | None'):
        if content:
            self.html = EmailMessage()
            self.html.add_header("Content-Type", "text/html", charset="UTF-8")
            self.html.add_header("Content-Transfer-Encoding", "quoted-printable")
            self.html.set_payload(f"<div>{content}</div>")
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
                include_headers = [b'From', b'To', b'Message-ID'] + ([b'Subject'] if self._subj else [])
            )
            self.message.add_header('DKIM-Signature', sgn[16:].decode())

    def get_bytes(self):
        return self.message.as_bytes()
    
    def get_str(self):
        return self.message.as_string()