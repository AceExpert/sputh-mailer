import asyncio
import ssl
import socket
import enum
import re
import smtplib

import dkim

from email.parser import BytesParser

from db import EmailManager
from utils import get_dns_record, get_email

sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
sslctx.load_cert_chain('/etc/letsencrypt/archive/sayutel.com/cert1.pem', '/etc/letsencrypt/archive/sayutel.com/privkey1.pem')

class CmdState(enum.Enum):
    START = 0
    MIDDLE = 1
    MULTILINE = 2
    MULTILINE_LAST = 3

class SMTPClientInfo:

    def __init__(self):
        self.ehlo_domain: str = None
        self.tls_attempt: bool = False
        self.is_tls: bool = False
        self.mail_from: str = None
        self.mail_data: bytes = b''
        self.rcpt_to: list[str] = []
        self.mail_size: int = 0

class SayutelMailServer:

    loop: asyncio.AbstractEventLoop
    server: asyncio.Server

    class ClientProtocol(asyncio.Protocol):

        def __init__(self, mailserver, transport):
            super().__init__()
            self.mailserver: SayutelMailServer = mailserver
            self.transport = transport
            transport.write(b"220 sayutel.com Sayutel ESMTPS Server\r\n")

            self.info = SMTPClientInfo()

            self.write_queue = []

            self.buff_list = []
            self.buff = b''
            self.cmds = []
            self.current_cmd = ''
            self.data_cmd = -1
            self.pending_size = 0
            self.bdat_last = False
            self.state = CmdState.START

            self.email_parser = BytesParser()
            
        def write_to_client(self, data: bytes):
            if self.info.tls_attempt and not self.info.is_tls:
                self.write_queue.append(data)
            elif not self.info.tls_attempt or (self.info.tls_attempt and self.info.is_tls):
                try:
                    self.transport.write(data)
                except Exception:
                    pass


        def connection_made(self, transport):
            pass
            
        def data_received(self, data: bytes):
            self.buff += data

            if self.data_cmd == 1:
                if len(self.buff) >= self.pending_size:
                    self.info.mail_data += self.buff[:self.pending_size]

                    if self.bdat_last:
                        asyncio.gather(self.process_mail_data(self.info.mail_data))
                    else:
                        self.write_to_client(b'250 next\r\n')

                    self.data_cmd = -1
                    self.buff = self.buff[self.pending_size:]
                    self.pending_size = 0

            elif self.data_cmd == 0:
                ind = self.buff.find(b'\r\n.\r\n')
                if ind > -1:
                    self.info.mail_data = self.buff[:ind]
                    self.data_cmd = -1
                    if ind + 5 <= len(self.buff) - 1:
                        self.buff = self.buff[ind + 5:]
                    else:
                        self.buff = b''
                    asyncio.gather(self.process_mail_data(self.info.mail_data))

            if self.data_cmd == -1:
                parts = self.buff.split(b'\r\n')
                i = 0
                for part in parts:
                    if i < len(parts) - 1:
                        
                        if len(part) >= 6 and not part[:4].lower() in [b'bdat', b'data']:
                            if part[:4].lower() == b'ehlo':
                                if 'ehlo' not in self.cmds:
                                    self.cmds.append('ehlo')
                                self.info.ehlo_domain = part[5:].strip().decode()
                                self.write_to_client(
                                    b'250-sayutel.com Hello ' + self.info.ehlo_domain.encode() + b'\r\n'
                                    b'250-SIZE 157286400\r\n'
                                    b'250-STARTTLS\r\n'
                                    b'250-PIPELINING\r\n'
                                    b'250-CHUNKING\r\n'
                                    b'250-SMTPUTF8\r\n'
                                    b'250 8BITMIME\r\n'
                                )
                            elif part.lower().strip() == b'starttls':
                                if 'starttls' not in self.cmds:
                                    self.cmds.append('starttls')
                                self.write_to_client(b"220 Yes go ahead\r\n")
                                self.info.tls_attempt = True
                                asyncio.gather(self.upgrade_to_tls())

                            elif b':' in part:
                                cmd, params = part.split(b':', 1)
                                cmd_normal = cmd.lower().strip()
                                if cmd_normal == b'mail from':
                                    if 'mailfrom' not in self.cmds:
                                        self.cmds.append('mailfrom')
                                    parsed = self.parse_envelope_cmd(params)
                                    self.info.mail_from = parsed['mail']
                                    self.write_to_client(b'250 Ok\r\n')
                                elif cmd_normal == b'rcpt to':
                                    if 'rcptto' not in self.cmds:
                                        self.cmds.append('rcptto')
                                    parsed = self.parse_envelope_cmd(params)
                                    self.info.rcpt_to.append(parsed['mail'])
                                    self.write_to_client(b'250 Ok\r\n')

                        else:
                            if len(part) >= 4:
                                if part[:4].lower() == b'quit':
                                    self.write_to_client(b'221 Bye\r\n')
                                    self.transport.close()
                                
                                elif part[:4].lower() == b'data':
                                    self.data_cmd = 0
                                    self.write_to_client(b'354 Send\r\n')

                                elif part[:4].lower() == b'bdat':
                                    self.data_cmd = 1

                                    for pa in part.split(b' '):
                                        if pa.strip():
                                            if pa.strip().lower() == b'last':
                                                self.bdat_last = True
                                            elif not self.pending_size and pa.strip().isdigit():
                                                self.pending_size = int(pa.strip().decode())


                                if part[:4].lower() in [b'data', b'bdat']:
                                    i += 1
                                    self.buff = b''
                                    while i < len(parts):
                                        self.buff += parts[i] + (b'\r\n' if i != (len(parts) - 1) else b'')
                                        i += 1
                                    
                                    if self.data_cmd == 1:
                                        if len(self.buff) >= self.pending_size:
                                            self.info.mail_data += self.buff[:self.pending_size]

                                            self.data_cmd = -1
                                            self.buff = self.buff[self.pending_size:]  
                                            self.pending_size = 0

                                            if self.bdat_last:
                                                asyncio.gather(self.process_mail_data(self.info.mail_data))
                                            else:
                                                self.write_to_client("250 next\r\n")

                                    elif self.data_cmd == 0:
                                        if self.buff.endswith(b'\r\n.\r\n'):
                                            self.info.mail_data = self.buff[:-5]
                                            self.data_cmd = -1
                                            asyncio.gather(self.process_mail_data(self.info.mail_data))
                                    break

                    else:
                        self.buff = part

                    i += 1

        async def upgrade_to_tls(self):
            self.transport = await self.mailserver.loop.start_tls(self.transport, self, sslcontext = sslctx, server_side = True)
            self.info.is_tls = True
            while len(self.write_queue):
                self.transport.write(self.write_queue.pop(0))

        async def process_mail_data(self, data: bytes):
            # print(data)
            # print()
            # print('Received from:', self.info.ehlo_domain)
            # print('Return-Path:', self.info.mail_from)
            # print('RCPT TO:', self.info.rcpt_to)
            # print('Encrypted:', self.info.is_tls)
            # print(data.decode())

            for user in self.info.rcpt_to:                
                db = EmailManager(user)
                ins_data: tuple = db.add_raw_mail('inbox', data, self.info.mail_from, user, self.info.is_tls)

                if user in ['anshul@sayutel.com', 'anshul@sputh.me']:
                    ndata = data
                    from_header_addrs = get_email(ins_data[1])

                    if from_header_addrs:
                        from_h_user, from_h_dom = from_header_addrs[0].split('@')
                        if from_h_dom not in ins_data[8].split(', '):
                            nmess = self.email_parser.parsebytes(ndata)
                            nmess.replace_header('From', ins_data[1].replace(from_header_addrs[0], from_header_addrs[0] + '.invalid'))
                            del nmess['dkim-signature']
                            nmess.add_header('Sender', ins_data[1])
                            nmess.add_header('Reply-To', ins_data[1])
                            ndata = nmess.as_bytes()

                            with open('/home/keys/key0/rsa.private', 'r') as keyfile:
                                key = keyfile.read()
                                sgn = dkim.sign(
                                    ndata, 
                                    b'dragon', 
                                    b'sayutel.com', 
                                    privkey = key.encode(),
                                    include_headers = [b'From', b'To', b'Message-ID'] + ([b'Subject'] if nmess.get('subject', None) else []),
                                    linesep=b' '
                                )
                                nmess.add_header('DKIM-Signature', sgn[16:].decode())
                            
                            ndata = nmess.as_bytes()

                    mx_record = get_dns_record('gmail.com', 'MX')
                    smtcl = smtplib.SMTP(local_hostname = self.info.ehlo_domain, host = min(mx_record, key = lambda rec: rec.priority).value[:-1]);
                    smtcl.sendmail('sayu@sayutel.com', 'very.anshul@gmail.com', ndata);
                    smtcl.close()

                for fns in self.mailserver.listeners:
                    try:
                        if self.mailserver.owner_obj:
                            await fns(self.mailserver.owner_obj, self.info, ins_data)
                        else:
                            await fns(self.info, ins_data)
                    except Exception as e:
                        print(e)

            self.write_to_client(b'250 Received Thank you\r\n')
            
        def parse_envelope_cmd(self, value: bytes):
            data = {
                'mail': '',
                'curr_param': '',
                'val_start': False,
                'params': {}
            }

            state = 0

            for ind, v in enumerate(value.decode()):

                if state == 0:

                    if not data['mail'] and v == '<':
                        state = 1
                
                elif state == 1:

                    if v == '>':
                        state = 2
                    else:
                        data['mail'] += v

                elif state == 2:

                    if v.isalnum():
                        state = 3
                        data['curr_param'] += v

                elif state == 3:

                    if v.isalnum():
                        data['curr_param'] += v
                    elif v == '=':
                        state = 4
                        data['curr_param'] = data['curr_param'].lower()
                        data['params'][data['curr_param']] = ''
                        data['val_start'] = True
                        
                elif state == 4:

                    if data['val_start'] and v not in [' ', '\n']:
                        data['params'][data['curr_param']] += v
                        data['val_start'] = False
                    elif not data['val_start'] and v in [' ', '\n']:
                        state = 2
                        data['curr_param'] = ''
                    elif not data['val_start'] and v not in [' ', '\n']:
                        data['params'][data['curr_param']] += v
            
            return data


        def eof_received(self):
            pass
        
        def connection_lost(self, exc: Exception):
            pass
    
    class ServerProtocol(asyncio.Protocol):

        def __init__(self, mailserver):
            super().__init__()
            self.mailserver: SayutelMailServer = mailserver

        def connection_made(self, transport):
            transport.set_protocol(self.mailserver.ClientProtocol(self.mailserver, transport))
        
        def data_received(self, data: bytes):
            pass
    
        def eof_received(self):
            pass
        
        def connection_lost(self, exc: Exception):
            pass
        
    def __init__(self, owner = None, loop = None):
        self.loop = loop or asyncio.new_event_loop()
        self.connections = []
        self.owner_obj = owner
        self.listeners = []

    async def start_server(self):
        self.server = await self.loop.create_server(
            lambda: self.ServerProtocol(self), 
            '0.0.0.0', 25, 
            family = socket.AF_INET, backlog = 4096
        )

        print("Sayutel ESMTPS Mail server active @ 0.0.0.0:25")
        
        await self.server.start_serving()
        await self.server.serve_forever()

    def add_listener(self, fn):
        self.listeners.append(fn)

    def remove_listener(self, fn):
        self.listeners.remove(fn)

    

if __name__ == '__main__':
    mailserver = SayutelMailServer()
    mailserver.loop.run_until_complete(mailserver.start_server())